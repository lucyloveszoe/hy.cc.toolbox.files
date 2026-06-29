"""local-dup-match-cross.py — find duplicate / near-duplicate file records
ACROSS two folders of NAS-style catalog dumps.

Both folders contain line-oriented catalog files whose lines look like::

    <size_in_bytes> bytes <full_posix_path>

Encoding is auto-detected per file (UTF-16 LE/BE, UTF-8-BOM, plain UTF-8).

Two reports are emitted into ``--output-dir``:

* exact.csv     — same byte size, members span both folders
* potential.csv — similar basename + different byte size, members span both
                  folders

Only groups whose members appear on **both** sides are kept. Single-folder
dupes are intentionally suppressed — use local-dup-match.py for that.

Defaults
--------
* folder A              : C:\\tmp\\files-list\\linux.nas
* folder B              : C:\\tmp\\files-list\\linux.mac
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

from dup_common import (
    find_exact_duplicates,
    find_potential_duplicates,
    load_records,
    write_exact_csv,
    write_potential_csv,
)

DEFAULT_FOLDER_A = r"C:\tmp\files-list\linux.nas"
DEFAULT_FOLDER_B = r"C:\tmp\files-list\linux.mac"
DEFAULT_CATALOG_GLOB = "*.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check duplicate / near-duplicate file records between "
            "two folders of '<bytes> bytes <path>' catalog dumps. Only "
            "matches that span BOTH folders are reported."
        )
    )
    parser.add_argument(
        "folder_a",
        nargs="?",
        default=DEFAULT_FOLDER_A,
        help=f"First catalog folder (default: {DEFAULT_FOLDER_A})",
    )
    parser.add_argument(
        "folder_b",
        nargs="?",
        default=DEFAULT_FOLDER_B,
        help=f"Second catalog folder (default: {DEFAULT_FOLDER_B})",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write exact.csv / potential.csv (default: .)",
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
            "Enable O(n^2) fuzzy clustering for 'potential' singletons "
            "(SequenceMatcher >= 0.85); slow on large catalogs"
        ),
    )
    args = parser.parse_args(argv)

    folder_a = Path(args.folder_a).expanduser().resolve()
    folder_b = Path(args.folder_b).expanduser().resolve()
    for label, folder in (("A", folder_a), ("B", folder_b)):
        if not folder.is_dir():
            print(
                f"error: folder {label} is not a directory: {folder}",
                file=sys.stderr,
            )
            return 2
    if folder_a == folder_b:
        print(
            "error: folder A and folder B must differ; use "
            "local-dup-match.py for single-folder analysis",
            file=sys.stderr,
        )
        return 2

    side_a = folder_a.name
    side_b = folder_b.name
    if side_a == side_b:
        side_a = f"{side_a} (A)"
        side_b = f"{side_b} (B)"

    out_dir = Path(args.output_dir).expanduser().resolve()
    print(f"folder A     : {folder_a}  [side={side_a}]")
    print(f"folder B     : {folder_b}  [side={side_b}]")
    print(f"catalog glob : {args.catalog_glob}")
    print(f"output dir   : {out_dir}")

    records_a = load_records(
        folder_a,
        args.catalog_glob,
        side=side_a,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
    )
    records_b = load_records(
        folder_b,
        args.catalog_glob,
        side=side_b,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
    )
    if not records_a or not records_b:
        print(
            "one or both sides have no records; cross-check produces "
            "nothing."
        )
        return 0

    records = records_a + records_b
    print(
        f"records loaded: A={len(records_a)} B={len(records_b)} "
        f"total={len(records)}"
    )

    exact_groups = find_exact_duplicates(records, require_cross_side=True)
    exact_rows = write_exact_csv(exact_groups, out_dir / "exact.csv")
    print(
        f"exact dupes (same byte size, A&B): "
        f"{exact_rows} records in {len(exact_groups)} groups "
        f"-> {out_dir / 'exact.csv'}"
    )

    potential_groups = find_potential_duplicates(
        records,
        require_cross_side=True,
        require_cross_source=False,
        enable_fuzzy=args.fuzzy,
    )
    potential_rows = write_potential_csv(
        potential_groups, out_dir / "potential.csv"
    )
    print(
        f"potential dupes (similar name, different size, A&B): "
        f"{potential_rows} records in {len(potential_groups)} groups "
        f"-> {out_dir / 'potential.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
