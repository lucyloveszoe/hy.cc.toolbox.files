"""Clean Word .doc files: text-only -> txt, with pictures -> .docx (pictures embedded).

Usage: python doc_clean.py <file.doc> [...] [-o outputs] [--drop-carved STEM=N[,N]] [--no-compact STEM] [--ignore-pictures STEM]

  outputs/txt/<stem>.txt        no pictures
  outputs/reports/<stem>.docx   with pictures (textutil cannot write pictures into a legacy .doc,
                                so a real .docx is written with the standard library)

Picture test: Word INCLUDEPICTURE fields, or JPEG/PNG/GIF data carved from the binary
(carve_doc_images.py; catches pictures textutil does not expose). Noise removal is
doc_to_html.process (PROCESSING_RULES 4.1 variants 1-5, 4.3). Pictures are carved in file order and
paired with fields in order; a count mismatch stops that file unless --drop-carved lists the
1-based carved pictures to ignore. A file with carved pictures but no fields gets picture k after
paragraph k (position is a guess). Never overwrites; originals untouched.
"""
import argparse
import re
import struct
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from carve_doc_images import carve
import doc_to_html
from doc_to_html import FIELD_LEFT, MARK, process
from doc_ole_text import read_doc
from doc_to_txt import textutil

MAX_W_EMU = 5486400  # 6 inch
EMU = 9525  # per pixel
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
MIME = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif"}


def dims(ext: str, b: bytes) -> tuple[int, int]:
    try:
        if ext == "png":
            return struct.unpack(">II", b[16:24])
        if ext == "gif":
            return struct.unpack("<HH", b[6:10])
        i = 2
        while i + 9 < len(b) and b[i] == 0xFF:
            m = b[i + 1]
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    except struct.error:
        pass
    return 400, 300


def drawing(n: int, ext: str, data: bytes) -> str:
    w, h = dims(ext, data)
    cx, cy = w * EMU, h * EMU
    if cx > MAX_W_EMU:
        cx, cy = MAX_W_EMU, int(cy * MAX_W_EMU / cx)
    return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{n}" name="Picture {n}"/><a:graphic><a:graphicData '
            f'uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr>'
            f'<pic:cNvPr id="{n}" name="image{n}.{ext}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill>'
            f'<a:blip r:embed="rId{n + 1}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr>'
            f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
            f'</a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')


def run(t: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{escape(t)}</w:t></w:r>' if t else ""


def write_docx(out: Path, text: str, pics: list[tuple[str, bytes]], by_paragraph: bool) -> None:
    lines = text.rstrip("\n").split("\n")
    paras, used = [], 0
    if by_paragraph:  # no field marks: picture k after non-blank paragraph k
        k = 0
        for ln in lines:
            paras.append(run(ln))
            if ln.strip() and k < len(pics):
                k += 1
                paras.append(drawing(k, *pics[k - 1]))
                used += 1
        for k in range(used, len(pics)):  # leftover pictures at the end
            paras.append(drawing(k + 1, *pics[k]))
            used += 1
    else:
        for ln in lines:
            parts, pos = [], 0
            for m in MARK.finditer(ln):
                parts.append(run(ln[pos:m.start()]))
                n = int(m.group(1)) + 1
                parts.append(drawing(n, *pics[n - 1]))
                used += 1
                pos = m.end()
            parts.append(run(ln[pos:]))
            paras.append("".join(parts))
    assert used == len(pics), (used, len(pics))
    body = "".join(f"<w:p>{p}</w:p>" for p in paras)
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{body}'
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
           'w:left="1134" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/'
              'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
              'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
              + "".join(f'<Default Extension="{e}" ContentType="{m}"/>' for e, m in MIME.items())
              + '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
            'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
             'openxmlformats.org/package/2006/relationships">'
             + "".join(f'<Relationship Id="rId{k + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                       f'relationships/image" Target="media/image{k + 1}.{e}"/>' for k, (e, _) in enumerate(pics))
             + "</Relationships>")
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", drels)
        for k, (e, data) in enumerate(pics):
            z.writestr(f"word/media/image{k + 1}.{e}", data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("outputs"))
    ap.add_argument("--drop-carved", action="append", default=[], metavar="STEM=N[,N]")
    ap.add_argument("--ignore-pictures", action="append", default=[], metavar="STEM",
                    help="treat the pictures as decoration (e.g. forum smilies) and write a txt")
    ap.add_argument("--no-compact", action="append", default=[], metavar="STEM",
                    help="(STEM or *) skip the compact-garbage rule for this file (it removed real prices like 140/hr)")
    a = ap.parse_args()
    drop = {}
    for s in a.drop_carved:
        stem, _, ns = s.partition("=")
        drop[stem] = {int(x) for x in ns.split(",")}
    for f in a.files:
        try:  # own OLE reader: pictures paired 1:1 with their position (also inline pictures)
            raw, pics = read_doc(f)
            src = "ole"
        except Exception:  # not a Word 97+ file: textutil text + pictures carved in file order
            raw, pics, src = textutil(f, "txt"), list(carve(f.read_bytes())), "textutil"
        real_compact = doc_to_html.drop_compact
        if f.stem in a.no_compact or "*" in a.no_compact:
            doc_to_html.drop_compact = lambda t: (t, 0)
        try:
            text, urls, (spam, site, tail) = process(raw)
        finally:
            doc_to_html.drop_compact = real_compact
        dropped = sorted(drop.get(f.stem, ()))
        pics = [p for k, p in enumerate(pics, 1) if k not in dropped]
        tiny = bool(pics) and max(max(dims(e, b)) for e, b in pics) <= 100
        if f.stem in a.ignore_pictures or tiny:  # decoration only (smilies/icons) -> txt
            if tiny:
                print(f"  note: {f.name}: all {len(pics)} pictures are <=100 px, written as txt")
            pics, urls, text = [], [], MARK.sub("", text)
        if not pics and not urls:
            out = a.outdir / "txt" / (f.stem + ".txt")
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "x", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            kind = "txt"
        else:
            if urls and len(urls) != len(pics):
                print(f"STOP {f.name}: fields={len(urls)} carved={len(pics)} (use --drop-carved)")
                continue
            out = a.outdir / "reports" / (f.stem + ".docx")
            out.parent.mkdir(parents=True, exist_ok=True)
            write_docx(out, text, pics, by_paragraph=not urls)
            kind = "docx"
        left = len(FIELD_LEFT.findall(MARK.sub("", text)))
        print(f"{f.name}: {kind}/{src} missing={text.count('[image missing]')} fields={len(urls)} pics={len(pics)} dropped={dropped} "
              f"spam={spam} site={site} tail={tail} leftovers={left} chars={len(text)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
