"""local-dup-match.py — find duplicate / near-duplicate file records
inside one folder of NAS-style catalog dumps.

Each catalog file in the input folder is line-oriented text where every
line has the shape::

    <size_in_bytes> bytes <full_posix_path>

For example::

    468068018 bytes /Volumes/YuData/Korea.50G/.../episode01.mp4

Encoding is auto-detected per file (UTF-16 LE/BE, UTF-8-BOM, plain UTF-8).

Two reports are emitted into ``--output-dir``:

* exact.csv     — records whose byte size is exactly equal (grouped)
* potential.csv — records whose byte size differs but whose basenames are
                  similar (partial match), grouped by normalized name

Defaults
--------
* folder                : C:\\tmp\\files-list\\linux.nas
* catalog file glob     : *.txt
* skip system noise     : .DS_Store, Thumbs.db, desktop.ini, ._*
                          (toggle off with --include-system-files)
* skip zero-byte entries: yes (toggle off with --include-zero-bytes)
* potential groups      : same-source pairs allowed
                          (tighten with --cross-source-only)
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

DEFAULT_FOLDER = r"C:\tmp\files-list\linux.nas"
DEFAULT_CATALOG_GLOB = "*.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Find duplicate / near-duplicate file records inside one "
            "folder of '<bytes> bytes <path>' catalog dumps."
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
        "--cross-source-only",
        action="store_true",
        help=(
            "Require 'potential' groups to span >= 2 distinct catalog "
            "sources (default: allow same-source groups too)"
        ),
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

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"error: not a directory: {folder}", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir).expanduser().resolve()
    print(f"scan root    : {folder}")
    print(f"catalog glob : {args.catalog_glob}")
    print(f"output dir   : {out_dir}")

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
    print(
        f"records loaded: {len(records)} from {len(sources)} catalog(s)"
    )

    exact_groups = find_exact_duplicates(records, require_cross_side=False)
    exact_rows = write_exact_csv(exact_groups, out_dir / "exact.csv")
    print(
        f"exact dupes (same byte size): "
        f"{exact_rows} records in {len(exact_groups)} groups "
        f"-> {out_dir / 'exact.csv'}"
    )

    potential_groups = find_potential_duplicates(
        records,
        require_cross_side=False,
        require_cross_source=args.cross_source_only,
        enable_fuzzy=args.fuzzy,
    )
    potential_rows = write_potential_csv(
        potential_groups, out_dir / "potential.csv"
    )
    print(
        f"potential dupes (similar name, different size): "
        f"{potential_rows} records in {len(potential_groups)} groups "
        f"-> {out_dir / 'potential.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
