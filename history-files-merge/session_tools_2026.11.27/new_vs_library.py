"""READ-ONLY: compare the reports of new layout-A roots with each other and with every report page under DD.

    python3 new_vs_library.py <out.tsv> <new root> [<new root> ...]

Per new page: signature = md5(visible text without <head>/<h1>, lower case, whitespace-free) + tuple of image SHA-256
in order (PROCESSING_LOGIC 5.1). Candidates: any shared image SHA-256, or >= 3 shared sampled 8-grams (8-grams whose
hash % 8 == 0, content-defined so both sides sample the same grams). Each candidate is verified with the full
8-gram sets. Output row per new page (best candidate = highest text share, then most shared images):
  page, chars, imgs, class, match, match_chars, match_imgs, share_new_in_match, share_match_in_new,
  imgs_shared, imgs_only_new (>=5 KB), imgs_only_match
class: exact | same-images-tiny-diff (same image sequence, share >= 0.95 both ways) | subset (new adds no image >= 5 KB,
  share_new_in_match >= 0.90) | superset (match adds no image, share_match_in_new >= 0.90) | near (share >= 0.60
  either way) | new. Blank pages (no text and no image) -> class blank. Numbers rounded to 2 decimals.
"""
import collections
import hashlib
import html
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hfm_config import DD  # noqa: E402

IMG_SRC = re.compile(r'<img[^>]*?\ssrc="([^"]+)"', re.I)
_sha = {}


def sha(p):
    if p not in _sha:
        try:
            _sha[p] = (hashlib.sha256(open(p, 'rb').read()).hexdigest(), os.path.getsize(p))
        except OSError:
            _sha[p] = (None, 0)
    return _sha[p]


def page(p):
    t = open(p, encoding='utf-8', errors='replace').read()
    imgs = []
    for s in IMG_SRC.findall(t):
        v = html.unescape(s)
        if re.match(r'^(?:[a-z]+:|//)', v, re.I):
            continue
        h, size = sha(os.path.normpath(os.path.join(os.path.dirname(p), v)))
        if h:
            imgs.append((h, size))
    b = re.sub(r'(?is)<head.*?</head>|<h1.*?</h1>', '', t)
    b = re.sub(r'(?is)<h3>.*?</h3>', '', b)          # 'Primary post — author' headers made by the processor
    b = html.unescape(re.sub(r'<[^>]+>', '', b))
    b = re.sub(r'\[image missing\]', '', b)
    txt = re.sub(r'\s+', '', b).lower()
    return txt, imgs


def grams(txt):
    return {zlib.crc32(txt[i:i + 8].encode()) for i in range(max(0, len(txt) - 7))}


def main():
    out, roots = sys.argv[1], [os.path.abspath(r) for r in sys.argv[2:]]
    pages = {}
    lib_dirs = [DD] + roots
    for base in lib_dirs:
        for d, _, fs in os.walk(base):
            if '/txt' in d.replace(base, '') or '_files' in d:
                continue
            for f in fs:
                if f.lower().endswith(('.html', '.htm')):
                    p = os.path.join(d, f)
                    if p not in pages:
                        pages[p] = page(p)
    new = [p for p in pages if any(p.startswith(r + os.sep) for r in roots)]
    print('library+new pages', len(pages), 'new', len(new))
    by_img = collections.defaultdict(set)
    by_gram = collections.defaultdict(set)
    sig = collections.defaultdict(list)
    gcache = {}
    for p, (txt, imgs) in pages.items():
        for h, _ in imgs:
            by_img[h].add(p)
        g = grams(txt)
        gcache[p] = g
        for x in g:
            if x % 8 == 0:
                by_gram[x].add(p)
        sig[(hashlib.md5(txt.encode()).hexdigest(), tuple(h for h, _ in imgs))].append(p)
    rows = []
    for p in sorted(new):
        txt, imgs = pages[p]
        if not txt and not imgs:
            rows.append([p, 0, 0, 'blank'] + [''] * 8)
            continue
        s = (hashlib.md5(txt.encode()).hexdigest(), tuple(h for h, _ in imgs))
        ex = [q for q in sig[s] if q != p]
        cand = collections.Counter()
        for h, _ in imgs:
            for q in by_img[h]:
                cand[q] += 100
        for x in gcache[p]:
            if x % 8 == 0 and len(by_gram[x]) < 200:
                for q in by_gram[x]:
                    cand[q] += 1
        best = None
        for q, c in cand.items():
            if q == p or c < 3:
                continue
            g1, g2 = gcache[p], gcache[q]
            inter = len(g1 & g2)
            a = inter / len(g1) if g1 else (1.0 if not g2 else 0.0)
            b = inter / len(g2) if g2 else (1.0 if not g1 else 0.0)
            ni = {h for h, _ in imgs}
            mi = {h for h, _ in pages[q][1]}
            score = (max(a, b), len(ni & mi))
            if best is None or score > best[0]:
                best = (score, q, a, b, ni, mi)
        if ex:
            q = sorted(ex, key=lambda x: (not x.startswith(DD), x))[0]
            mi = {h for h, _ in pages[q][1]}
            rows.append([p, len(txt), len(imgs), 'exact', q, len(pages[q][0]), len(pages[q][1]), 1.0, 1.0, len(mi), 0, 0])
            continue
        if not best:
            rows.append([p, len(txt), len(imgs), 'new'] + [''] * 8)
            continue
        _, q, a, b, ni, mi = best
        big_only_new = {h for h, size in imgs if h not in mi and size >= 5000}
        only_match = mi - ni
        same_seq = [h for h, _ in imgs] == [h for h, _ in pages[q][1]]
        if same_seq and a >= 0.95 and b >= 0.95:
            cl = 'same-images-tiny-diff'
        elif not big_only_new and a >= 0.90:
            cl = 'subset'
        elif not only_match and b >= 0.90:
            cl = 'superset'
        elif max(a, b) >= 0.60:
            cl = 'near'
        else:
            cl = 'new'
        rows.append([p, len(txt), len(imgs), cl, q, len(pages[q][0]), len(pages[q][1]), round(a, 2), round(b, 2),
                     len(ni & mi), len(big_only_new), len(only_match)])
    with open(out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('page\tchars\timgs\tclass\tmatch\tmatch_chars\tmatch_imgs\tshare_new_in_match\tshare_match_in_new\t'
                 'imgs_shared\timgs_only_new\timgs_only_match\n')
        for r in rows:
            fh.write('\t'.join(str(x) for x in r) + '\n')
    c = collections.Counter(r[3] for r in rows)
    print(dict(c))
    where = collections.Counter((r[3], 'new-set' if r[4] and any(r[4].startswith(x) for x in roots) else
                                 (os.path.relpath(r[4], DD).split('/')[0] if r[4] else '-')) for r in rows)
    for k, v in sorted(where.items()):
        print('  ', k, v)


if __name__ == '__main__':
    main()
