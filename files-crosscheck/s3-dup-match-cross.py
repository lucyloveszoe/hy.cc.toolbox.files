"""s3-dup-match-cross.py — cross-check file records between a Linux NAS
catalog folder and an S3 listing folder.

The Linux side uses the Linux NAS dump format::

    <size_in_bytes> bytes <full_posix_path>

The S3 side uses the AWS CLI / s3 ls format::

    YYYY-MM-DD HH:MM:SS  <size_in_bytes>  <relative_key>

Directory placeholder rows on the S3 side (key ending in ``/``, size 0)
are skipped automatically.

Two reports are emitted into ``--output-dir``:

* exact.csv     — same byte size, members on BOTH sides
* potential.csv — similar basename + different byte size, members on BOTH
                  sides

Defaults
--------
* linux folder          : C:\\tmp\\files-list\\linux.nas
* s3 folder             : C:\\tmp\\files-list\\win.s3
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
    parse_linux_catalog,
    parse_s3_catalog,
    write_exact_csv,
    write_potential_csv,
)

DEFAULT_LINUX_FOLDER = r"C:\tmp\files-list\linux.nas"
DEFAULT_S3_FOLDER = r"C:\tmp\files-list\win.s3"
DEFAULT_CATALOG_GLOB = "*.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check duplicate / near-duplicate file records between "
            "a Linux NAS catalog folder and an S3 listing folder. Only "
            "matches that span BOTH sides are reported."
        )
    )
    parser.add_argument(
        "linux_folder",
        nargs="?",
        default=DEFAULT_LINUX_FOLDER,
        help=f"Linux NAS catalog folder (default: {DEFAULT_LINUX_FOLDER})",
    )
    parser.add_argument(
        "s3_folder",
        nargs="?",
        default=DEFAULT_S3_FOLDER,
        help=f"S3 listing folder (default: {DEFAULT_S3_FOLDER})",
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

    linux_folder = Path(args.linux_folder).expanduser().resolve()
    s3_folder = Path(args.s3_folder).expanduser().resolve()
    for label, folder in (("linux", linux_folder), ("s3", s3_folder)):
        if not folder.is_dir():
            print(
                f"error: {label} folder is not a directory: {folder}",
                file=sys.stderr,
            )
            return 2
    if linux_folder == s3_folder:
        print(
            "error: linux folder and s3 folder must differ",
            file=sys.stderr,
        )
        return 2

    side_linux = linux_folder.name
    side_s3 = s3_folder.name
    if side_linux == side_s3:
        side_linux = f"{side_linux} (linux)"
        side_s3 = f"{side_s3} (s3)"

    out_dir = Path(args.output_dir).expanduser().resolve()
    print(f"linux folder : {linux_folder}  [side={side_linux}]")
    print(f"s3 folder    : {s3_folder}  [side={side_s3}]")
    print(f"catalog glob : {args.catalog_glob}")
    print(f"output dir   : {out_dir}")

    records_linux = load_records(
        linux_folder,
        args.catalog_glob,
        side=side_linux,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
        parse_fn=parse_linux_catalog,
    )
    records_s3 = load_records(
        s3_folder,
        args.catalog_glob,
        side=side_s3,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
        parse_fn=parse_s3_catalog,
    )
    if not records_linux or not records_s3:
        print(
            "one or both sides have no records; cross-check produces "
            "nothing."
        )
        return 0

    records = records_linux + records_s3
    print(
        f"records loaded: linux={len(records_linux)} "
        f"s3={len(records_s3)} total={len(records)}"
    )

    exact_groups = find_exact_duplicates(records, require_cross_side=True)
    exact_rows = write_exact_csv(exact_groups, out_dir / "exact.csv")
    print(
        f"exact dupes (same byte size, linux&s3): "
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
        f"potential dupes (similar name, different size, linux&s3): "
        f"{potential_rows} records in {len(potential_groups)} groups "
        f"-> {out_dir / 'potential.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
