"""cross-dup-match-v2.py — three-tier duplicate scan ACROSS two folders of
Linux-format catalog dumps (``<size> bytes <path>`` lines).

Defaults to comparing the "local" and "nas" folders under
``C:\\tmp\\files-list2``, producing ``loc2nas-exact.csv`` /
``loc2nas-almost.csv`` / ``loc2nas-potential.csv``.

Same three tiers as local-dup-match-v2.py, but every group is required to
span BOTH folders — single-folder dupes are suppressed (use
local-dup-match-v2.py for that).

Defaults
--------
* folder A              : C:\\tmp\\files-list2\\local
* folder B              : C:\\tmp\\files-list2\\nas
* output dir            : C:\\tmp\\files-list2\\outputs
* prefix                : loc2nas
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
DEFAULT_FOLDER_A = str(Path(DEFAULT_ROOT) / "local")
DEFAULT_FOLDER_B = str(Path(DEFAULT_ROOT) / "nas")
DEFAULT_OUTPUT_DIR = str(Path(DEFAULT_ROOT) / "outputs")
DEFAULT_PREFIX = "loc2nas"
DEFAULT_CATALOG_GLOB = "*.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Three-tier (exact/almost/potential) duplicate scan between "
            "two folders of Linux-format catalog dumps. Only matches "
            "that span BOTH folders are reported."
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
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write reports (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Output filename prefix (default: {DEFAULT_PREFIX})",
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
            "local-dup-match-v2.py for single-folder analysis",
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
    print(f"prefix       : {args.prefix}")

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

    exact_groups, almost_groups, potential_groups = find_tiered_duplicates(
        records, require_cross_side=True, enable_fuzzy=args.fuzzy
    )

    prefix = args.prefix
    exact_rows = write_tier_csv(
        exact_groups,
        out_dir / f"{prefix}-exact.csv",
        group_sort_key=lambda g: -g[0].size,
    )
    print(
        f"exact (same size + name, A&B): {exact_rows} records in "
        f"{len(exact_groups)} groups -> {out_dir / f'{prefix}-exact.csv'}"
    )

    almost_rows = write_tier_csv(
        almost_groups,
        out_dir / f"{prefix}-almost.csv",
        group_sort_key=lambda g: -g[0].size,
    )
    print(
        f"almost (same size only, A&B): {almost_rows} records in "
        f"{len(almost_groups)} groups -> {out_dir / f'{prefix}-almost.csv'}"
    )

    potential_rows = write_tier_csv(
        potential_groups,
        out_dir / f"{prefix}-potential.csv",
        group_sort_key=lambda g: normalize_name(g[0].name),
    )
    print(
        f"potential (similar name only, A&B): {potential_rows} records in "
        f"{len(potential_groups)} groups -> "
        f"{out_dir / f'{prefix}-potential.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
