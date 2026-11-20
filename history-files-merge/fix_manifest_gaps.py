"""Add manifest rows for images that exist in images/<folder>/ but are not listed in <folder>_images_manifest.csv.

Usage: python fix_manifest_gaps.py <root> [<root> ...] [--go]

Cause (PROCESSING_RULES 12.4): one picture used by two pages of the same thread is copied twice (p<NNN>_ prefix
= page index in the summary), but only one copy gets a manifest row. The new row is
  source_file = <_files folder used by that page's other rows, else <page stem>_files>/<original name>
  status      = copied: used by a saved post
  output      = images/<folder>/p<NNN>_<name>
Dry run unless --go. Keeps BOM and line ending, appends rows at the end, never edits existing rows.
"""
import csv
import os
import re
import sys
from pathlib import Path


def run(root: Path, go: bool) -> int:
    total = 0
    for mc in sorted(root.glob("*_images_manifest.csv")):
        folder = mc.name[: -len("_images_manifest.csv")]
        raw = mc.read_bytes()
        eol = "\r\n" if b"\r\n" in raw else "\n"
        with open(mc, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        head = rows[0]
        si, sti, oi = head.index("source_file"), head.index("status"), head.index("output")
        with open(root / f"{folder}_summary.csv", encoding="utf-8-sig", newline="") as fh:
            summ = list(csv.DictReader(fh))
        listed = {r[oi] for r in rows[1:] if len(r) > oi and r[oi]}
        page_dir = {}
        for r in rows[1:]:
            m = re.match(r".*/p(\d+)_", r[oi]) if len(r) > oi else None
            if m and "/" in r[si]:
                page_dir.setdefault(int(m.group(1)), r[si].rsplit("/", 1)[0])
        new = []
        for p in sorted((root / "images" / folder).iterdir()):
            out = f"images/{folder}/{p.name}"
            if out in listed:
                continue
            m = re.match(r"p(\d+)_(.*)$", p.name)
            if not m:
                print("  cannot map", p.name)
                continue
            n = int(m.group(1))
            d = page_dir.get(n) or os.path.splitext(summ[n - 1]["page"])[0] + "_files"
            row = [""] * len(head)
            row[si], row[sti], row[oi] = f"{d}/{m.group(2)}", "copied: used by a saved post", out
            new.append(row)
        print(f"{mc.name}: {len(new)} rows to add")
        total += len(new)
        if go and new:
            with open(mc, "w", encoding="utf-8-sig", newline="") as fh:
                csv.writer(fh, lineterminator=eol).writerows(rows + new)
    return total


if __name__ == "__main__":
    go = "--go" in sys.argv
    n = sum(run(Path(a), go) for a in sys.argv[1:] if a != "--go")
    print("TOTAL", n, "(written)" if go else "(dry run)")
