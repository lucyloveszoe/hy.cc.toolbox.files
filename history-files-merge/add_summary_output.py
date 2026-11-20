"""Add the `output` column to <folder>_summary.csv files written by process_html_posts.py.

Usage: python add_summary_output.py <root> [<root> ...]

For every `<folder>_summary.csv` directly under <root>:
  html page        -> reports/<folder>/<page without .htm>.html
  txt page         -> txt/<folder>/<page without .htm>.txt
  unsupported      -> empty
Paths are relative to <root> (the CSV folder). Keeps BOM and line ending; never changes other columns.
A row whose target file does not exist gets an empty output. Re-running is a no-op.
"""
import csv
import os
import sys
from pathlib import Path


def fix(csv_path: Path) -> tuple[int, int]:
    root = csv_path.parent
    folder = csv_path.name[: -len("_summary.csv")]
    raw = csv_path.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    head = rows[0]
    if "output" in head:
        return 0, 0
    head.append("output")
    n = miss = 0
    for r in rows[1:]:
        page, mode = r[0], r[1]
        stem = os.path.splitext(page)[0]
        out = ""
        if mode == "html":
            out = f"reports/{folder}/{stem}.html"
        elif mode == "txt":
            out = f"txt/{folder}/{stem}.txt"
        if out and not (root / out).exists():
            out, miss = "", miss + 1
        n += bool(out)
        r.append(out)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, lineterminator=eol).writerows(rows)
    return n, miss


def main() -> int:
    for r in sys.argv[1:]:
        for p in sorted(Path(r).glob("*_summary.csv")):
            n, miss = fix(p)
            print(f"{p}: output set for {n} rows, {miss} targets missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
