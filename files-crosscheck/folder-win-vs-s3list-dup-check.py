"""folder-win-vs-s3list-dup-check.py — cross-check file records between a
real Windows folder (scanned directly from disk) and a single S3 listing
file (AWS CLI / s3 ls format).

The Windows side has no catalog format — it is scanned the same way as
local-folder-win-dup-check.py (``Path.rglob`` + ``Path.stat()``).

The S3 side is a single catalog file (not a folder of catalogs) using the
AWS CLI / s3 ls format::

    YYYY-MM-DD HH:MM:SS  <size_in_bytes>  <relative_key>

Directory placeholder rows on the S3 side (key ending in ``/``, size 0)
are skipped automatically.

Two reports are emitted into ``--output-dir``:

* exact.csv     — same byte size, members on BOTH sides
* potential.csv — similar basename + different byte size, members on BOTH
                  sides

Defaults
--------
* windows folder        : C:\\Temp\\self\\video
* s3 listing file       : C:\\tmp\\files-list\\win.s3\\s3.vids.txt
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
    load_records_from_catalog_file,
    load_records_from_filesystem,
    parse_s3_catalog,
    write_exact_csv,
    write_potential_csv,
)

DEFAULT_WIN_FOLDER = r"C:\Temp\self\video"
DEFAULT_S3_FILE = r"C:\tmp\files-list\win.s3\s3.vids.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check duplicate / near-duplicate file records between "
            "a real Windows folder (scanned directly) and a single S3 "
            "listing file. Only matches that span BOTH sides are "
            "reported."
        )
    )
    parser.add_argument(
        "windows_folder",
        nargs="?",
        default=DEFAULT_WIN_FOLDER,
        help=f"Windows folder to scan recursively (default: {DEFAULT_WIN_FOLDER})",
    )
    parser.add_argument(
        "s3_file",
        nargs="?",
        default=DEFAULT_S3_FILE,
        help=f"S3 listing file (default: {DEFAULT_S3_FILE})",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write exact.csv / potential.csv (default: .)",
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

    windows_folder = Path(args.windows_folder).expanduser().resolve()
    if not windows_folder.is_dir():
        print(
            f"error: windows folder is not a directory: {windows_folder}",
            file=sys.stderr,
        )
        return 2

    s3_file = Path(args.s3_file).expanduser().resolve()
    if not s3_file.is_file():
        print(
            f"error: s3 listing is not a file: {s3_file}",
            file=sys.stderr,
        )
        return 2

    side_win = windows_folder.name
    side_s3 = s3_file.parent.name
    if side_win == side_s3:
        side_win = f"{side_win} (win)"
        side_s3 = f"{side_s3} (s3)"

    out_dir = Path(args.output_dir).expanduser().resolve()
    print(f"windows folder : {windows_folder}  [side={side_win}]")
    print(f"s3 file        : {s3_file}  [side={side_s3}]")
    print(f"output dir     : {out_dir}")

    records_win = load_records_from_filesystem(
        windows_folder,
        side=side_win,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
    )
    records_s3 = load_records_from_catalog_file(
        s3_file,
        side=side_s3,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
        parse_fn=parse_s3_catalog,
    )
    if not records_win or not records_s3:
        print(
            "one or both sides have no records; cross-check produces "
            "nothing."
        )
        return 0

    records = records_win + records_s3
    print(
        f"records loaded: windows={len(records_win)} "
        f"s3={len(records_s3)} total={len(records)}"
    )

    exact_groups = find_exact_duplicates(records, require_cross_side=True)
    exact_rows = write_exact_csv(exact_groups, out_dir / "exact.csv")
    print(
        f"exact dupes (same byte size, windows&s3): "
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
        f"potential dupes (similar name, different size, windows&s3): "
        f"{potential_rows} records in {len(potential_groups)} groups "
        f"-> {out_dir / 'potential.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
