"""READ-ONLY: every page under <DD>/<set>/html links only to existing local images, and every image under
<DD>/<set>/html is linked by at least one page (anywhere under DD).

    python3 audit_html_links.py [DD] [--list N]

Pages: *.htm / *.html under any <set>/html folder (outside *_files/ folders, which are counted separately).
Links: <img src> (plus <a href> whose target has an image extension). Resolved relative to the page, html-unescaped,
NFC; then classified:
  ok            existing file whose header is an image (jpg/png/gif/bmp/webp)
  broken        target does not exist
  not-image     target exists but its header is not an image (html error page, 0 bytes, ...)
  percent       src is percent-encoded (resolves only after unquote) -> counted as broken unless the raw path exists
  remote        http(s): / // links (counted, not checked)
  data          data: URIs (counted)
  outside-html  ok target that lies outside every <set>/html folder (e.g. <set>/images/, another set) - listed
Images: files with an image extension or image header under <set>/html; orphan = linked by no page under DD.
Non-image, non-page files under html (CSV, manifest.csv, ...) are listed by type. Exit 1 when broken/not-image/orphan > 0.
"""
import collections
import html
import os
import re
import sys
import unicodedata
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hfm_config import DD as _DD  # noqa: E402

IMG_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
IMG = re.compile(r'<img\b[^>]*?\ssrc\s*=\s*(["\'])(.*?)\1', re.I | re.S)
AH = re.compile(r'<a\b[^>]*?\shref\s*=\s*(["\'])(.*?)\1', re.I | re.S)


def nfc(p):
    return unicodedata.normalize('NFC', os.path.normpath(p))


_hdr = {}


def is_image(p):
    if p not in _hdr:
        try:
            b = open(p, 'rb').read(12)
        except OSError:
            b = b''
        _hdr[p] = b.startswith(b'\xff\xd8\xff') or b.startswith(b'\x89PNG') or b.startswith(b'GIF8') or \
            b.startswith(b'BM') or (b[:4] == b'RIFF' and b[8:12] == b'WEBP')
    return _hdr[p]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    nlist = int(sys.argv[sys.argv.index('--list') + 1]) if '--list' in sys.argv else 15
    if '--list' in sys.argv:
        args.remove(str(nlist))
    DD = nfc(os.path.abspath(args[0] if args else _DD))
    html_roots = sorted(nfc(os.path.join(DD, s, 'html')) for s in os.listdir(DD)
                        if os.path.isdir(os.path.join(DD, s, 'html')))
    in_html = lambda p: next((r for r in html_roots if p.startswith(r + os.sep)), None)
    pages, imgs, other, files_pages = [], [], collections.Counter(), 0
    for R in html_roots:
        for d, _, fs in os.walk(R):
            for f in fs:
                p = nfc(os.path.join(d, f))
                low = f.lower()
                if f == '.DS_Store':
                    continue
                if low.endswith(('.htm', '.html')):
                    if '_files' in os.path.relpath(p, R).split(os.sep)[:-1] or re.search(r'_files(/|$)', os.path.relpath(d, R)):
                        files_pages += 1
                    else:
                        pages.append(p)
                elif low.endswith(IMG_EXT) or is_image(p):
                    imgs.append(p)
                else:
                    other[(os.path.relpath(R, DD).split(os.sep)[0], os.path.splitext(f)[1].lower() or f)] += 1
    # pages anywhere under DD can link html images (e.g. raw archive); collect their links too
    all_pages = set(pages)
    for d, _, fs in os.walk(DD):
        for f in fs:
            if f.lower().endswith(('.htm', '.html')):
                all_pages.add(nfc(os.path.join(d, f)))
    linked = set()
    cls = collections.Counter()
    per_set = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    outside = collections.Counter()
    for p in sorted(all_pages):
        audited = p in pages_set(pages)          # pages outside <set>/html only contribute links
        t = open(p, encoding='utf-8', errors='replace').read()
        refs = [m.group(2) for m in IMG.finditer(t)]
        refs += [m.group(2) for m in AH.finditer(t) if m.group(2).lower().split('?')[0].endswith(IMG_EXT)]
        s = os.path.relpath(p, DD).split(os.sep)[0]
        for raw in refs:
            v = html.unescape(raw).strip()
            if re.match(r'^(?:https?:)?//', v, re.I):
                c = 'remote'
            elif v.lower().startswith('data:'):
                c = 'data'
            elif re.match(r'^[a-z]+:', v, re.I) or v.startswith('#') or not v:
                c = 'other-scheme'
            else:
                q = nfc(os.path.join(os.path.dirname(p), v.split('#')[0].split('?')[0]))
                if os.path.isfile(q):
                    linked.add(q)
                    c = 'ok' if is_image(q) else 'not-image'
                    if c == 'ok' and audited and in_html(q) is None:
                        outside[(s, os.path.relpath(q, DD).split(os.sep)[0] + '/' + os.path.relpath(q, DD).split(os.sep)[1])] += 1
                else:
                    q2 = nfc(os.path.join(os.path.dirname(p), urllib.parse.unquote(v.split('#')[0].split('?')[0])))
                    if '%' in v and os.path.isfile(q2):
                        linked.add(q2)
                        c = 'percent'
                    else:
                        c = 'broken'
            if audited:
                cls[c] += 1
                per_set[s][c] += 1
                if c in ('broken', 'not-image', 'percent') and len(examples[c]) < nlist:
                    examples[c].append(f'{os.path.relpath(p, DD)}  ->  {raw}')
    orphans = [q for q in imgs if q not in linked]
    print(f'DD {DD}')
    print(f'html folders {len(html_roots)} | pages {len(pages)} (+{files_pages} inside _files folders, not audited) | '
          f'images under html {len(imgs)}')
    print(f'{"set":32} {"pages":>6} {"imgs":>7} {"links ok":>9} {"broken":>7} {"notimg":>7} {"pct":>5} {"remote":>7} {"orphan":>7}')
    op = collections.Counter(os.path.relpath(q, DD).split(os.sep)[0] for q in orphans)
    pc = collections.Counter(os.path.relpath(p, DD).split(os.sep)[0] for p in pages)
    ic = collections.Counter(os.path.relpath(q, DD).split(os.sep)[0] for q in imgs)
    for s in sorted(set(pc) | set(ic)):
        c = per_set[s]
        print(f'{s:32} {pc[s]:6} {ic[s]:7} {c["ok"]:9} {c["broken"]:7} {c["not-image"]:7} {c["percent"]:5} {c["remote"]:7} {op[s]:7}')
    print('TOTAL links', dict(cls), '| orphan images', len(orphans))
    for c, ex in examples.items():
        print(f'--- {c} (first {len(ex)})')
        for e in ex:
            print('   ', e)
    if orphans:
        print(f'--- orphan images (first {min(nlist, len(orphans))})')
        for q in orphans[:nlist]:
            print('   ', os.path.relpath(q, DD), os.path.getsize(q))
        byd = collections.Counter(os.path.relpath(os.path.dirname(q), DD) for q in orphans)
        print('    orphan folders:', byd.most_common(10))
    if outside:
        print('--- ok links that leave the html folders (page set, target top folder): count')
        for k, v in outside.most_common(20):
            print('   ', k, v)
    if other:
        print('--- other files under html:', dict(other))
    bad = cls['broken'] + cls['not-image'] + cls['percent'] + len(orphans)
    print('PROBLEMS', bad)
    sys.exit(1 if bad else 0)


_ps = None


def pages_set(pages):
    global _ps
    if _ps is None:
        _ps = set(pages)
    return _ps


if __name__ == '__main__':
    main()
