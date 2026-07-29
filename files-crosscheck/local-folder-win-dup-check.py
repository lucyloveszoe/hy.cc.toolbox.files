"""local-folder-win-dup-check.py — find exact-duplicate files (same byte
size) inside one real Windows folder, scanned directly from disk.

Unlike local-dup-match.py (which parses catalog text dumps), this script
walks the folder tree itself with pathlib, recursing into every
subfolder, and reads each file's actual size via ``Path.stat()``. No
catalog file is needed or expected.

Only one report is emitted into ``--output-dir``:

* exact.csv — records whose byte size is exactly equal (grouped)

Defaults
--------
* folder                : C:\\Temp\\self\\video
* skip system noise     : .DS_Store, Thumbs.db, desktop.ini, ._*
                          (toggle off with --include-system-files)
* skip zero-byte entries: yes (toggle off with --include-zero-bytes)

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
    load_records_from_filesystem,
    write_exact_csv,
)

DEFAULT_FOLDER = r"C:\Temp\self\video"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Find exact-duplicate files (same byte size) inside one real "
            "Windows folder, scanned directly from disk."
        )
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=DEFAULT_FOLDER,
        help=f"Folder to scan recursively (default: {DEFAULT_FOLDER})",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write exact.csv (default: .)",
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
    args = parser.parse_args(argv)

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"error: not a directory: {folder}", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir).expanduser().resolve()
    print(f"scan root  : {folder}")
    print(f"output dir : {out_dir}")

    records = load_records_from_filesystem(
        folder,
        side=folder.name,
        include_system=args.include_system_files,
        include_zero=args.include_zero_bytes,
    )
    if not records:
        print("no records loaded; nothing to do.")
        return 0

    print(f"records loaded: {len(records)} files")

    exact_groups = find_exact_duplicates(records, require_cross_side=False)
    exact_rows = write_exact_csv(exact_groups, out_dir / "exact.csv")
    print(
        f"exact dupes (same byte size): "
        f"{exact_rows} records in {len(exact_groups)} groups "
        f"-> {out_dir / 'exact.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
