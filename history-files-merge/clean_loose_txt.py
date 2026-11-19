"""Re-encode loose forum .txt files (GBK or UTF-16) to UTF-8 and strip maichun watermark garbage.

Usage: python clean_loose_txt.py <out dir> <file.txt> [...]   (originals are never modified)
Noise forms (PROCESSING_RULES 4.1): spam phrase + ASCII run; bare `www.maichun.org` followed by an
ASCII garbage run; a garbage run of 1-2 char tokens glued in front of the URL.
"""
import re
import sys
from pathlib import Path

from doc_to_txt import MIXED, strip_tail

SPAM = re.compile(r"(?:ＭＣ军团（招財進寶）\[关闭注册\]\s*)?军团,\s*招财进宝,?\s*(?:华人[信性]息网站第一)?[!-~  ]*")
SPAM2 = re.compile(r"[ＭＣ]*军团（招財進寶）\[关闭注册\][!-~  ]*")
BEFORE = re.compile(r"(?:(?<=[^\x00-\x7f])|^)[ ]?(?:[!-~]{1,2}[  ])*[!-~]{0,2}(?=www\.maichun\.org)", re.M)
AFTER = re.compile(r"www\.maichun\.org[!-~  ]*")


PREFIX = re.compile(r"^(?P<ws> *)(?P<run>(?:[!-~]{1,2} +)*[!-~]{1,2})(?=[^\x00-\x7f]| {2,})")
TAIL2 = re.compile(r"(?<=[^\x00-\x7f])(?P<run>[!-~]{1,2} [!-~]{1,2})$")


def _garbage(toks: list[str], need: int) -> bool:
    mixed = sum(bool(MIXED.match(t)) for t in toks)
    like = sum(bool(len(t) == 1 or not (t.isalpha() or t.isdigit())) for t in toks)
    return len(toks) >= need and mixed >= 1 and like >= need


TAILN = re.compile(r"(?:(?<=[^\x00-\x7f])|(?<= ))(?P<run>(?:[!-~]{1,2} )+[!-~]{1,2})$|(?<=[^\x00-\x7f])(?P<g>[!-~]{1,2})(?P<run2> (?:[!-~]{1,2} )*[!-~]{1,2})$")


PREFIX_NUM = re.compile(r"^ *(?P<run>(?:[!-~]{1,2} +)+)[!-~]?(?=\d{1,2}\.[^\x00-\x7f])")


def strip_edges(line: str) -> tuple[str, int]:
    n = 0
    m = PREFIX_NUM.match(line)
    if m:
        toks = m.group("run").split()
        if len(toks) >= 4 and all(len(t) == 1 or not (t.isalpha() or t.isdigit()) for t in toks):
            line, n = line[m.end():], n + 1
    m = TAILN.search(line)
    if m:
        toks = ((m.group("g") or "") + " " + (m.group("run2") or "")).split() if m.group("g") else m.group("run").split()
        like = [t for t in toks if len(t) == 1 or not (t.isalpha() or t.isdigit())]
        if len(toks) >= 5 and len(like) == len(toks) and any(not c.isalnum() for t in toks for c in t):
            line, n = line[: m.start()], n + 1
    m = PREFIX.match(line)
    toks0 = m.group("run").split() if m else []
    like0 = [t for t in toks0 if len(t) == 1 or not (t.isalpha() or t.isdigit())]
    if m and (_garbage(toks0, 3) or (len(toks0) >= 6 and len(like0) == len(toks0))):
        line, n = line[m.end():], n + 1
    m = TAIL2.search(line)
    if m:
        toks = m.group("run").split()
        if any(re.fullmatch(r"[^A-Za-z0-9]{1,2}", t) for t in toks) and any(MIXED.match(t) for t in toks):
            line, n = line[: m.start()], n + 1
    return line, n


def decode(b: bytes) -> str:
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16")
    if b[:3] == b"\xef\xbb\xbf":
        return b.decode("utf-8-sig")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("gb18030")


def clean(s: str) -> tuple[str, dict]:
    st = {}
    s = s.lstrip("﻿").replace(" ", "\n").replace(" ", "\n").replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\xa0", " ").replace("　", " ")
    s, st["spam"] = SPAM2.subn("", s)
    s, k = SPAM.subn("", s)
    st["spam"] += k
    s, st["before"] = BEFORE.subn("", s)
    s, st["after"] = AFTER.subn("", s)
    out, tails = [], 0
    for ln in s.split("\n"):
        new, hit = strip_tail(ln)
        tails += hit
        out.append(new)
    st["tail"] = tails
    out2, edges = [], 0
    for ln in out:
        new, hit = strip_edges(ln)
        edges += hit
        out2.append(new)
    st["edges"] = edges
    s = "\n".join(out2)
    s = re.sub(r"[ \t]+$", "", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"
    return s, st


def main() -> int:
    out = Path(sys.argv[1])
    for f in sys.argv[2:]:
        p = Path(f)
        s, st = clean(decode(p.read_bytes()))
        dst = out / p.name
        if dst.exists():
            print("EXISTS, skipped", dst)
            continue
        out.mkdir(parents=True, exist_ok=True)
        dst.write_text(s, encoding="utf-8")
        print(p.name, len(s), st, "leftover maichun:", s.count("maichun"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
