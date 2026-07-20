"""local-dup-match-v2.py — three-tier duplicate scan inside one folder of
Linux-format catalog dumps (``<size> bytes <path>`` lines).

Used for both the "local" and "nas" folders under
``C:\\tmp\\files-list2`` (run it twice, once per folder — same script,
different ``folder`` argument and ``--prefix``).

Three reports are emitted into ``--output-dir``, all mutually exclusive
(a record appears in exactly one of them):

* ``<prefix>-exact.csv``     — same byte size AND fuzzy-matched name
* ``<prefix>-almost.csv``    — same byte size only
* ``<prefix>-potential.csv`` — fuzzy-matched name only, size differs

See dup_common_v2.find_tiered_duplicates() for the exact waterfall rule.

Defaults
--------
* folder                : C:\\tmp\\files-list2\\local
* output dir            : C:\\tmp\\files-list2\\outputs
* prefix                : folder's own name (e.g. "local", "nas")
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
import sys
from pathlib import Path

from dup_common import load_records, normalize_name
from dup_common_v2 import find_tiered_duplicates, write_tier_csv

DEFAULT_ROOT = r"C:\tmp\files-list2"
DEFAULT_FOLDER = str(Path(DEFAULT_ROOT) / "local")
DEFAULT_OUTPUT_DIR = str(Path(DEFAULT_ROOT) / "outputs")
DEFAULT_CATALOG_GLOB = "*.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Three-tier (exact/almost/potential) duplicate scan inside "
            "one folder of Linux-format catalog dumps."
        )
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=DEFAULT_FOLDER,
        help=f"Folder containing catalog files (default: {DEFAULT_FOLDER})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write reports (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Output filename prefix (default: the folder's own name)",
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

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"error: not a directory: {folder}", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir).expanduser().resolve()
    prefix = args.prefix or folder.name
    print(f"scan root    : {folder}")
    print(f"catalog glob : {args.catalog_glob}")
    print(f"output dir   : {out_dir}")
    print(f"prefix       : {prefix}")

    records = load_records(
        folder,
        args.catalog_glob,
        side=folder.name,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
    )
    if not records:
        print("no records loaded; nothing to do.")
        return 0

    sources = {r.source for r in records}
    print(f"records loaded: {len(records)} from {len(sources)} catalog(s)")

    exact_groups, almost_groups, potential_groups = find_tiered_duplicates(
        records, require_cross_side=False, enable_fuzzy=args.fuzzy
    )

    exact_rows = write_tier_csv(
        exact_groups,
        out_dir / f"{prefix}-exact.csv",
        group_sort_key=lambda g: -g[0].size,
    )
    print(
        f"exact (same size + name): {exact_rows} records in "
        f"{len(exact_groups)} groups -> {out_dir / f'{prefix}-exact.csv'}"
    )

    almost_rows = write_tier_csv(
        almost_groups,
        out_dir / f"{prefix}-almost.csv",
        group_sort_key=lambda g: -g[0].size,
    )
    print(
        f"almost (same size only): {almost_rows} records in "
        f"{len(almost_groups)} groups -> {out_dir / f'{prefix}-almost.csv'}"
    )

    potential_rows = write_tier_csv(
        potential_groups,
        out_dir / f"{prefix}-potential.csv",
        group_sort_key=lambda g: normalize_name(g[0].name),
    )
    print(
        f"potential (similar name only): {potential_rows} records in "
        f"{len(potential_groups)} groups -> "
        f"{out_dir / f'{prefix}-potential.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
