"""Remove forum watermark + trailing garbage chars from Word .doc files.

Usage: python clean_doc_noise.py <file.doc> [...] [-o OUTDIR]
Reads .doc via macOS textutil, writes cleaned UTF-8 .txt (and .doc) to OUTDIR.
Originals are never modified.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

# Watermark, optionally followed by a run of 1-2 char ASCII tokens (the garbage),
# separated by spaces / nbsp. The run stops at a line break or any non-ASCII char.
WATERMARK = r"本帖来源\s*https?://www\.maichun\.org\s*买春堂版权所有"
TOKEN = r"[!-~]{1,2}"
SEP = r"[ \u00a0]"
NOISE = re.compile(rf"{WATERMARK}(?:{SEP}*{TOKEN}(?=(?:{SEP}|$|[\u2028\u2029\r\n\u3000])))*")
# Same garbage pattern with the watermark text already stripped by Word/copy-paste
LEFTOVER_URL = re.compile(r"本帖来源|买春堂版权所有|www\.maichun\.org", re.I)


def clean(text: str) -> tuple[str, int]:
    text, n = NOISE.subn("", text)
    return text, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("outputs"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    for f in args.files:
        raw = subprocess.run(
            ["textutil", "-convert", "txt", "-encoding", "UTF-8", "-stdout", str(f)],
            check=True, capture_output=True,
        ).stdout.decode("utf-8")
        cleaned, n = clean(raw)
        txt = args.outdir / (f.stem + ".txt")
        txt.write_text(cleaned, encoding="utf-8")
        subprocess.run(
            ["textutil", "-convert", "doc", "-encoding", "UTF-8", str(txt)], check=True
        )
        left = len(LEFTOVER_URL.findall(cleaned))
        print(f"{f.name}: removed {n} watermark blocks, {left} leftovers, "
              f"{len(raw)} -> {len(cleaned)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
