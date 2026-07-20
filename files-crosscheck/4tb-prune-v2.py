"""4tb-prune-v2.py — cross-check "local" against "4tb" catalog folders for
EXACT duplicates only (same byte size AND fuzzy-matched name — the exact
tier from dup_common_v2.find_tiered_duplicates), then remove each matched
entry's line from its catalog file in the "4tb" folder, keeping the
matching line in "local"'s catalog file untouched.

This never touches real files — it only rewrites lines inside the "4tb"
side's ``.txt`` catalog dumps (Linux format: ``<size> bytes <path>``),
on the theory that anything already safe on "local" is redundant on the
4TB drive's inventory. A ``.bak`` copy of each modified catalog file is
written alongside it before its first rewrite in a run.

Two things land in ``--output-dir``:

* ``<prefix>-pruned.csv`` — audit trail: every exact-duplicate record,
  tagged ``kept`` (local side, untouched) or ``removed`` (4tb side, line
  deleted from its catalog file)
* the 4tb catalog ``.txt`` files themselves, rewritten in place (plus
  their ``.bak`` backups)

Defaults
--------
* local folder          : C:\\tmp\\files-list2\\local
* 4tb folder            : C:\\tmp\\files-list2\\4tb
* output dir            : C:\\tmp\\files-list2\\outputs
* prefix                : loc2tb
* catalog file glob     : *.txt
* skip system noise     : yes (toggle off with --include-system-files)
* skip zero-byte entries: yes (toggle off with --include-zero-bytes)
* fuzzy name clustering : disabled (enable with --fuzzy)

Workspace rules
---------------
* All string comparisons are lowercase + whitespace stripped.
* CSV files are written with a UTF-8 BOM so Excel renders CJK correctly.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from dup_common import _open_for_write, load_records, normalize_name
from dup_common_v2 import find_tiered_duplicates, remove_catalog_entries

DEFAULT_ROOT = r"C:\tmp\files-list2"
DEFAULT_LOCAL_FOLDER = str(Path(DEFAULT_ROOT) / "local")
DEFAULT_4TB_FOLDER = str(Path(DEFAULT_ROOT) / "4tb")
DEFAULT_OUTPUT_DIR = str(Path(DEFAULT_ROOT) / "outputs")
DEFAULT_PREFIX = "loc2tb"
DEFAULT_CATALOG_GLOB = "*.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Find exact duplicates (same size + fuzzy-matched name) "
            "between 'local' and '4tb' catalog folders, then delete "
            "each matched entry's line from its '4tb' catalog file "
            "(local's line is kept)."
        )
    )
    parser.add_argument(
        "local_folder",
        nargs="?",
        default=DEFAULT_LOCAL_FOLDER,
        help=f"Local catalog folder (default: {DEFAULT_LOCAL_FOLDER})",
    )
    parser.add_argument(
        "tb4_folder",
        nargs="?",
        default=DEFAULT_4TB_FOLDER,
        help=f"4TB catalog folder (default: {DEFAULT_4TB_FOLDER})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write the audit report (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Audit report filename prefix (default: {DEFAULT_PREFIX})",
    )
    parser.add_argument(
        "--catalog-glob",
        default=DEFAULT_CATALOG_GLOB,
        help=f"Catalog file glob (default: {DEFAULT_CATALOG_GLOB})",
    )
    parser.add_argument(
        "--include-system-files",
        action="store_true",
        help="Keep .DS_Store / Thumbs.db / desktop.ini / ._* records",
    )
    parser.add_argument(
        "--include-zero-bytes",
        action="store_true",
        help="Keep 0-byte file records",
    )
    parser.add_argument(
        "--fuzzy",
        action="store_true",
        help=(
            "Enable O(n^2) fuzzy name clustering for records that don't "
            "share a normalized name exactly (SequenceMatcher >= 0.85); "
            "slow on large catalogs"
        ),
    )
    args = parser.parse_args(argv)

    local_folder = Path(args.local_folder).expanduser().resolve()
    tb4_folder = Path(args.tb4_folder).expanduser().resolve()
    for label, folder in (("local", local_folder), ("4tb", tb4_folder)):
        if not folder.is_dir():
            print(
                f"error: {label} folder is not a directory: {folder}",
                file=sys.stderr,
            )
            return 2
    if local_folder == tb4_folder:
        print("error: local folder and 4tb folder must differ", file=sys.stderr)
        return 2

    side_local = "local"
    side_4tb = "4tb"

    out_dir = Path(args.output_dir).expanduser().resolve()
    print(f"local folder : {local_folder}")
    print(f"4tb folder   : {tb4_folder}")
    print(f"catalog glob : {args.catalog_glob}")
    print(f"output dir   : {out_dir}")

    records_local = load_records(
        local_folder,
        args.catalog_glob,
        side=side_local,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
    )
    records_4tb = load_records(
        tb4_folder,
        args.catalog_glob,
        side=side_4tb,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
    )
    if not records_local or not records_4tb:
        print("one or both sides have no records; nothing to prune.")
        return 0

    records = records_local + records_4tb
    print(
        f"records loaded: local={len(records_local)} "
        f"4tb={len(records_4tb)} total={len(records)}"
    )

    exact_groups, _almost, _potential = find_tiered_duplicates(
        records, require_cross_side=True, enable_fuzzy=args.fuzzy
    )
    print(f"exact duplicate groups (local & 4tb): {len(exact_groups)}")

    # side_4tb members to delete, grouped by their catalog file
    targets_by_file: dict[Path, set[tuple[int, str]]] = defaultdict(set)
    audit_rows: list[tuple[int, int, str, str, str, str, str, str]] = []

    for gid, members in enumerate(
        sorted(exact_groups, key=lambda g: -g[0].size), start=1
    ):
        for r in sorted(members, key=lambda r: (r.side, r.source, r.path)):
            action = "kept" if r.side == side_local else "removed"
            audit_rows.append(
                (
                    gid,
                    r.size,
                    normalize_name(r.name),
                    action,
                    r.side,
                    r.source,
                    r.name,
                    r.path,
                )
            )
            if r.side == side_4tb:
                catalog_file = tb4_folder / r.source
                targets_by_file[catalog_file].add((r.size, r.path))

    total_removed = 0
    for catalog_file, targets in targets_by_file.items():
        removed = remove_catalog_entries(catalog_file, targets)
        total_removed += removed
        print(f"  {catalog_file.name}: removed {removed} line(s)")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{args.prefix}-pruned.csv"
    with _open_for_write(report_path) as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "group_id",
                "size_bytes",
                "normalized_name",
                "action",
                "side",
                "source",
                "file_name",
                "file_path",
            ]
        )
        writer.writerows(audit_rows)

    print(
        f"pruned {total_removed} line(s) across {len(targets_by_file)} "
        f"4tb catalog file(s); audit report -> {report_path}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
