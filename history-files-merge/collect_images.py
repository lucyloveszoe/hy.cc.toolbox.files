"""Collect images from extracted saved-web-page folders into outputs/images/<folder>/.

Usage: python collect_images.py <source_folder> [...] [-o OUTDIR]
For each source folder (e.g. inputs/.../crazy) all jpg/jpeg/png/gif/bmp files under
its *_files sub-folders are COPIED (originals untouched) into OUTDIR/images/<folder name>/.
Names are  p<NN>_<original name>  (NN = page index in sorted order) so identical file
names from different pages never overwrite each other. A manifest.csv maps every
new name back to its source path. Thumbs.db and non-image files are skipped.
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}


def collect(src: Path, outdir: Path, sub: str = "images.only") -> int:
    dest = outdir / sub / src.name
    dest.mkdir(parents=True, exist_ok=True)
    pages = sorted(p for p in src.iterdir() if p.is_dir())
    rows = []
    for i, page in enumerate(pages, 1):
        imgs = sorted(f for f in page.rglob("*") if f.is_file() and f.suffix.lower() in IMG_EXT)
        for f in imgs:
            new = f"p{i:02d}_{f.name}"
            shutil.copy2(f, dest / new)
            rows.append((new, str(f.relative_to(src))))
    with open(dest / "manifest.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["image", "source"])
        w.writerows(rows)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("outputs"))
    ap.add_argument("--sub", default="images.only", help="sub-folder of outdir (images.only | images)")
    a = ap.parse_args()
    for s in a.folders:
        n = collect(s, a.outdir, a.sub)
        print(f"{s.name}: {n} images -> {a.outdir / a.sub / s.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
