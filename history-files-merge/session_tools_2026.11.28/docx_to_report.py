"""A .docx with embedded pictures -> one single-column html report in layout A (PROCESSING_LOGIC 4.1 / 4.5).

    python3 docx_to_report.py <file.docx> <out root> <folder> [--title T]

Writes <out root>/reports/<folder>/<title>.html and <out root>/images/<folder>/p001_<media name> (pictures in
document order, links ../../images/<folder>/...). Text: every <w:p> in word/document.xml in order; <w:t> runs
joined, <w:tab/> / <w:br/> -> space / line break; maichun garbage runs, edit stamps and odd characters are cut with
clean_text_docs.spans (same rule as the raw-archive clean-up). Pictures: <a:blip r:embed> -> word/_rels relationship
-> word/media/*; header-sniffed (jpg/png/gif/bmp), others skipped and listed. Refuses to overwrite.
Title: --title, else the first text line (<= 60 chars). Prints counts (paragraphs, text chars, pictures, cut spans).
"""
import html
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'session_tools_2026.11.27'))
from clean_text_docs import spans, cut   # noqa: E402

SNIFF = ((b'\xff\xd8\xff', '.jpg'), (b'\x89PNG', '.png'), (b'GIF8', '.gif'), (b'BM', '.bmp'))
CSS = ('body{max-width:900px;margin:2em auto;font-family:sans-serif;line-height:1.6}img{max-width:100%}'
       'section{border-bottom:1px solid #ccc;padding-bottom:1em}')


def main():
    a = [x for x in sys.argv[1:]]
    title = None
    if '--title' in a:
        i = a.index('--title'); title = a[i + 1]; del a[i:i + 2]
    src, root, folder = a
    z = zipfile.ZipFile(src)
    doc = z.read('word/document.xml').decode('utf-8')
    rels = dict(re.findall(r'<Relationship [^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"',
                           z.read('word/_rels/document.xml.rels').decode('utf-8')))
    rels.update({k: v for v, k in re.findall(r'<Relationship [^>]*?Target="([^"]+)"[^>]*?Id="([^"]+)"',
                                              z.read('word/_rels/document.xml.rels').decode('utf-8'))})
    blocks, ncut, skipped, pics = [], 0, [], []
    for p in re.findall(r'<w:p[ >].*?</w:p>', doc, re.S):
        items = re.findall(r'<w:t(?:\s[^>]*)?>([^<]*)</w:t>|(<w:tab/>)|(<w:br/>)|<a:blip [^>]*r:embed="([^"]+)"', p)
        line = ''
        for t, tab, br, rid in items:
            if t: line += html.unescape(t)
            elif tab: line += ' '
            elif br: line += '\n'
            elif rid:
                if line.strip(): blocks.append(('t', line)); line = ''
                blocks.append(('i', rid))
        if line.strip() or not items:
            blocks.append(('t', line))
    out_blocks = []
    for kind, v in blocks:
        if kind == 't':
            sp = spans(v); ncut += len(sp)
            v = cut(v, sp).replace(' ', ' ').replace('　', ' ')
            v = '\n'.join(re.sub(r' {2,}', ' ', x).strip() for x in v.split('\n')).strip()
            out_blocks.append(('t', v))
        else:
            target = rels.get(v, '')
            name = 'word/' + target if not target.startswith('/') else target[1:]
            try:
                data = z.read(name)
            except KeyError:
                skipped.append(target); continue
            ext = next((e for m, e in SNIFF if data.startswith(m)), None)
            if not ext:
                skipped.append(target); continue
            fn = f'p001_{os.path.splitext(os.path.basename(target))[0]}{ext}'
            pics.append((fn, data)); out_blocks.append(('i', fn))
    if not title:
        title = next((v.split('\n')[0] for k, v in out_blocks if k == 't' and v),
                     os.path.splitext(os.path.basename(src))[0])[:60]
    title = re.sub(r'[/\\:]', '_', title).strip()
    rd, idir = os.path.join(root, 'reports', folder), os.path.join(root, 'images', folder)
    page = os.path.join(rd, title + '.html')
    assert not os.path.exists(page), page
    for fn, _ in pics:
        assert not os.path.exists(os.path.join(idir, fn)), fn
    os.makedirs(rd, exist_ok=True); os.makedirs(idir, exist_ok=True)
    for fn, data in pics:
        open(os.path.join(idir, fn), 'wb').write(data)
    body, blank = [], 0
    for k, v in out_blocks:
        if k == 'i':
            body.append(f'<img src="../../images/{html.escape(folder, quote=True)}/{html.escape(v, quote=True)}"><br>'); blank = 0
        elif v:
            body.append(html.escape(v, quote=True).replace('\n', '<br>\n') + '<br>'); blank = 0
        elif blank < 1:
            body.append('<br>'); blank += 1
    t = html.escape(title, quote=True)
    open(page, 'w', encoding='utf-8').write(
        f'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>{t}</title><style>{CSS}</style></head>'
        f'<body><h1>{t}</h1>\n<section><h3>Primary post — </h3>\n' + re.sub(r'(?:<br>\s*)+$', '', '\n'.join(body)) + '</section></body></html>\n')
    print(f'{page}: paragraphs {sum(k == "t" for k, _ in out_blocks)}, text chars '
          f'{sum(len(v) for k, v in out_blocks if k == "t")}, pictures {len(pics)}, cut spans {ncut}, skipped {skipped}')


if __name__ == '__main__':
    main()
