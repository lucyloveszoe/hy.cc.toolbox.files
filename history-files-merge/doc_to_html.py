"""Word .doc files with linked pictures -> cleaned HTML report in outputs/reports.

Usage: python doc_to_html.py <file.doc> [...] [-o outputs/reports] [--overwrite]

Pictures are Word INCLUDEPICTURE fields. Word keeps the picture data inside the .doc (textutil
does not show it), so the pictures are carved from the binary (carve_doc_images.py) into
outputs/images/<stem>/NNN.<ext> and linked relatively from the report, in field order. If the
carved count differs from the field count, the report falls back to the remote URLs (dead hosts,
usually not viewable). Noise removed:
  1. spam phrases `军团,招财进宝,华人性息网站第一` / `ＭＣ军团（招財進寶）[关闭注册]` + garbage run
  2. `bbs.maichun.org` / maichun watermark + the garbage run after it
  3. line-tail garbage: spaced tokens (doc_to_txt.strip_tail) and compact runs (strip_compact)
  4. HYPERLINK field codes, private-use / control chars
Never overwrites existing files unless --overwrite. Originals untouched.
"""
import argparse
import html
import re
import sys
from pathlib import Path

from clean_doc_noise import NOISE
from carve_doc_images import carve
from doc_to_txt import drop_garbage, norm, textutil

RUN = r"[!-~  ]*"  # ASCII garbage run; stops at line break or non-ASCII
# spam phrases (also truncated or split by line breaks) + the garbage run that follows
SPAM_RE = re.compile(r"军团,\s*招财进宝,?\s*(?:华人性息网站第一)?" + RUN)
SPAM2_RE = re.compile(r"ＭＣ军团（招財進寶）\[关闭注册\]" + RUN)
# compact garbage (no spaces between tokens) at the end of a line / whole line
TAIL_RE = re.compile(r"(?:(?<=[^\x00-\x7f]) ?|^)([!-~](?:[!-~ ]*[!-~])?)$")


def strip_compact(line: str) -> tuple[str, bool]:
    m = TAIL_RE.search(line)
    if not m:
        return line, False
    run = m.group(1)
    link = ""
    if "http" in run:  # garbage directly followed by a visible link text: keep the link
        i = run.index("http")
        run, link = run[:i], run[i:]
    keep = ""
    k = re.match(r"\d{1,3}(?=[A-Za-z])", run)  # real leading number, e.g. `100V2z.M3A$`
    if k:
        keep, run = k.group(), run[k.end():]
    special = sum(not c.isalnum() and c != " " for c in run)
    if (len(run) >= 8 and special >= 3 and re.search("[a-z]", run) and re.search("[A-Z0-9]", run)
            and not re.search("[a-z]{3,}", run) and not run.startswith(("http", "www"))):
        return line[: m.start()] + keep + link, True
    return line, False


def drop_compact(t: str) -> tuple[str, int]:
    out, n = [], 0
    for ln in t.split("\n"):
        new, hit = strip_compact(ln)
        n += hit
        out.append(new.rstrip())
    return "\n".join(out), n
SITE_RE = re.compile(r"(?:https?://)?(?:www\.|bbs\.)?maichun\.org" + RUN, re.I)
PIC_RE = re.compile(r'INCLUDEPICTURE\s+"([^"]+)"[^\n  ]*?MERGEFORMAT(?:INET)?')
LINK_RE = re.compile(r'\s*HYPERLINK\s+"[^"]*"(?:\s*\\\w\s+"[^"]*")*\s*')
MARK = re.compile("⟦(\\d+)⟧")
FIELD_LEFT = re.compile(r"INCLUDEPICTURE|MERGEFORMAT|HYPERLINK|maichun|买春堂|本帖来源|招财进宝|关闭注册")

CSS = ("body{max-width:900px;margin:2em auto;font:16px/1.7 sans-serif;padding:0 1em}"
       "img{max-width:100%;display:block;margin:.6em 0}p{margin:.3em 0}")


def process(raw: str):
    urls = []

    def pic(m):
        urls.append(m.group(1))
        return f"⟦{len(urls) - 1}⟧"

    t = PIC_RE.sub(pic, raw)
    t = LINK_RE.sub("", t)
    t, n1 = SPAM_RE.subn("", t)
    t, n1b = SPAM2_RE.subn("", t)
    n1 += n1b
    t, n0 = NOISE.subn("", t)
    t, n2 = SITE_RE.subn("", t)
    t = norm(t)
    t, n3 = drop_garbage(t)
    t, n4 = drop_compact(t)
    return norm(t), urls, (n1, n2 + n0, n3 + n4)


def render(title: str, text: str, urls: list[str]) -> str:
    # urls: image sources (relative local paths, or remote URLs as fallback)
    body = []
    for ln in text.split("\n"):
        if not ln.strip():
            continue
        parts, pos = [], 0
        for m in MARK.finditer(ln):
            parts.append(html.escape(ln[pos:m.start()]))
            parts.append(f'<img src="{html.escape(urls[int(m.group(1))], quote=True)}" '
                         f'alt="image" loading="lazy">')
            pos = m.end()
        parts.append(html.escape(ln[pos:]))
        body.append("<p>" + "".join(parts).strip() + "</p>")
    return (f'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("outputs/reports"))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--images", type=Path, default=None, help="image root (default: <outdir>/../images)")
    a = ap.parse_args()
    img_root = a.images or a.outdir.parent / "images"
    a.outdir.mkdir(parents=True, exist_ok=True)
    for f in a.files:
        out = a.outdir / (f.stem + ".html")
        if out.exists() and not a.overwrite:
            print(f"SKIP (exists): {out.name}")
            continue
        text, urls, (spam, site, tail) = process(textutil(f, "txt"))
        pics = list(carve(f.read_bytes()))
        srcs, mode = urls, "remote"
        if len(pics) == len(urls):
            d = img_root / f.stem
            d.mkdir(parents=True, exist_ok=True)
            srcs, rows = [], ["image,original_url"]
            for k, ((ext, data), u) in enumerate(zip(pics, urls), 1):
                name = f"{k:03d}.{ext}"
                if not (d / name).exists() or a.overwrite:
                    (d / name).write_bytes(data)
                srcs.append(f"../images/{f.stem}/{name}")
                rows.append(f"{name},{u}")
            (d / "manifest.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
            mode = "local"
        shown = MARK.sub("", text)
        left = len(FIELD_LEFT.findall(shown))
        out.write_text(render(f.stem, text, srcs), encoding="utf-8")
        print(f"{f.name}: images={len(urls)} carved={len(pics)} {mode} spam={spam} site={site} tail={tail} leftovers={left}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
