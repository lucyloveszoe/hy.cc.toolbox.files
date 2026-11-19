"""Text-only .doc files -> cleaned txt in outputs/txt (PROCESSING_RULES 3.A, 4.1, 4.3).

Usage: python doc_to_txt.py <file.doc> [...] [-o outputs/txt] [--overwrite]

A file counts as "with images" if textutil's HTML has <img>, or the text contains a Word
INCLUDEPICTURE field (picture linked by URL, not embedded). Such files are skipped and
listed; only text-only files get a txt. Existing txt files are never overwritten unless
--overwrite is given. Originals are never modified.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

from clean_doc_noise import LEFTOVER_URL, clean

LS, PS, NBSP = " ", " ", " "

# Garbage without the watermark: line tail (or whole line) of >=3 space-separated 1-2 char
# ASCII tokens with >=1 alnum+punct mixed token and >=3 garbage-like tokens
# (e.g. `0 s5 j" r* ` y- E2 p7 l3`). The first token may be glued to preceding CJK text.
# Plain runs like `KJ BJ DL ML` or `16 -- 28` have no mixed token and stay.
TOK = re.compile(r"^[!-~]{1,2}$")
MIXED = re.compile(r"^(?=.*[A-Za-z0-9])(?=.*[^A-Za-z0-9])[!-~]{2}$")
PUNCT_ONLY = re.compile(r"^[^A-Za-z0-9]{1,2}$")
GLUED = re.compile(r"(?<=[^\x00-\x7f])([!-~]{1,2})$")
PRIVATE = re.compile("[-]")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def strip_tail(line: str) -> tuple[str, bool]:
    # split into words and separators (space / ideographic space), work from the end
    pieces = re.split(r"([ \u3000])", line)
    pieces = [p for p in pieces if p != ""]  # word, sep, word, sep, ...
    i = len(pieces)
    while i > 0 and (pieces[i - 1] in (" ", "\u3000") or TOK.match(pieces[i - 1])):
        i -= 1
    # pieces[i:] are the tail; make sure it starts with a word, not a separator
    while i < len(pieces) and pieces[i] in (" ", "\u3000"):
        i += 1
    toks = [p for p in pieces[i:] if p not in (" ", "\u3000") and p]
    head = "".join(pieces[:i]).rstrip(" \u3000")
    m = GLUED.search(head)
    if m:
        toks = [m.group(1)] + toks
        head = head[: m.start()]
    mixed = sum(bool(MIXED.match(t)) for t in toks)
    like = sum(bool(len(t) == 1 or not (t.isalpha() or t.isdigit())) for t in toks)
    if len(toks) >= 3 and mixed >= 1 and like >= 3:
        return head.rstrip(" \u3000"), True
    return line, False


def drop_garbage(t: str) -> tuple[str, int]:
    out, n = [], 0
    for ln in t.split("\n"):
        new, hit = strip_tail(ln)
        n += hit
        out.append(new)
    return "\n".join(out), n


def norm(t: str) -> str:
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace(LS, "\n").replace(PS, "\n")
    t = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), t)
    t = t.replace(NBSP, " ")
    t = PRIVATE.sub("", t)  # Word bullet symbols
    t = CTRL.sub("", t)
    t = re.sub(r" {2,}", " ", t)
    t = re.sub(r"[ \t]+$", "", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


def textutil(f: Path, fmt: str) -> str:
    return subprocess.run(
        ["textutil", "-convert", fmt, "-encoding", "UTF-8", "-stdout", str(f)],
        check=True, capture_output=True,
    ).stdout.decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("outputs/txt"))
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    a.outdir.mkdir(parents=True, exist_ok=True)
    for f in a.files:
        raw = textutil(f, "txt")
        imgs = len(re.findall(r"<img", textutil(f, "html"), re.I)) + len(
            re.findall(r"INCLUDEPICTURE", raw))
        if imgs:
            print(f"SKIP (has {imgs} images): {f.name}")
            continue
        out = a.outdir / (f.stem + ".txt")
        if out.exists() and not a.overwrite:
            print(f"SKIP (exists): {out.name}")
            continue
        c, n = clean(raw)
        c, g = drop_garbage(norm(c))
        c = norm(c)
        out.write_text(c, encoding="utf-8")
        print(f"{f.name}: blocks={n} garbage_lines={g} leftovers={len(LEFTOVER_URL.findall(c))} "
              f"{len(raw)} -> {len(c)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
