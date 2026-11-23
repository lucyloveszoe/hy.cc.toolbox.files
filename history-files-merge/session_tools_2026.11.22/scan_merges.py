#!/usr/bin/env python3 -I
"""Read-only scan of html/merges: exact + near duplicates inside merges, and exact vs topics/locations."""
import os, re, sys, html, hashlib, unicodedata, collections, json

BASE = '/Users/hany/Downloads/data.done/mc_2026.11.19/html'
OUT = os.path.dirname(os.path.abspath(__file__))
IMG = re.compile(r'<img[^>]*?src="([^"]+)"', re.I)

def norm(s):
    return re.sub(r'\s+', '', s).lower()

def load(path):
    t = open(path, encoding='utf-8', errors='replace').read()
    body = re.sub(r'(?is)<head>.*?</head>', '', t)
    body = re.sub(r'(?is)<h1[^>]*>.*?</h1>', '', body, count=1)
    srcs = [html.unescape(x) for x in IMG.findall(body)]
    text = norm(html.unescape(re.sub(r'<[^>]+>', '', body)))
    return text, srcs

def md5file(p, cache={}):
    if p not in cache:
        try:
            cache[p] = hashlib.md5(open(p, 'rb').read()).hexdigest()
        except OSError:
            cache[p] = 'MISSING'
    return cache[p]

def scan(group):
    rows = []
    g = os.path.join(BASE, group)
    for root in sorted(os.listdir(g)):
        rp = os.path.join(g, root, 'reports')
        if not os.path.isdir(rp):
            continue
        for fn in sorted(os.listdir(rp)):
            if not fn.endswith('.html'):
                continue
            p = os.path.join(rp, fn)
            text, srcs = load(p)
            seq = tuple(md5file(os.path.normpath(os.path.join(rp, s))) for s in srcs if not s.startswith(('http', 'data:')))
            rows.append(dict(group=group, root=root, file=fn, path=p, text=text, seq=seq,
                             key=hashlib.md5((text + '|' + ','.join(seq)).encode()).hexdigest()))
    return rows

def grams(t):
    return {t[i:i+8] for i in range(max(0, len(t) - 7))}

def main():
    m = scan('merges')
    lib = scan('topics') + scan('locations')
    print('merges', len(m), 'library', len(lib))
    # exact vs library
    libkeys = {r['key']: r for r in lib}
    ex_lib = [r for r in m if r['key'] in libkeys]
    print('exact vs library:', len(ex_lib))
    # exact inside merges
    groups = collections.defaultdict(list)
    for r in m:
        groups[r['key']].append(r)
    dg = {k: v for k, v in groups.items() if len(v) > 1}
    print('exact groups inside merges:', len(dg), 'extra copies:', sum(len(v) - 1 for v in dg.values()))
    with open(os.path.join(OUT, 'scan_exact_internal.tsv'), 'w', encoding='utf-8') as f:
        for k, v in dg.items():
            for r in v:
                f.write(f"{k}\t{r['root']}\t{r['file']}\t{len(r['text'])}\t{len(r['seq'])}\n")
    # near inside merges (>=300 chars; jaccard>0.7 and containment>0.8), non-exact only
    cand = [r for r in m if len(r['text']) >= 300]
    G = [grams(r['text']) for r in cand]
    inv = collections.defaultdict(list)
    for i, g in enumerate(G):
        for x in list(g)[::7]:
            inv[x].append(i)
    pairs = set()
    for i, g in enumerate(G):
        c = collections.Counter()
        for x in list(g)[::7]:
            for j in inv[x]:
                if j > i:
                    c[j] += 1
        for j, n in c.items():
            if n >= 5:
                pairs.add((i, j))
    near = []
    for i, j in pairs:
        a, b = cand[i], cand[j]
        if a['key'] == b['key']:
            continue
        inter = len(G[i] & G[j])
        jac = inter / len(G[i] | G[j])
        cont = inter / min(len(G[i]), len(G[j]))
        if jac > 0.7 and cont > 0.8:
            ia, ib = set(a['seq']), set(b['seq'])
            near.append((a, b, jac, cont, len(ia & ib), len(ia - ib), len(ib - ia)))
    print('near pairs inside merges:', len(near))
    with open(os.path.join(OUT, 'scan_near_internal.tsv'), 'w', encoding='utf-8') as f:
        f.write('rootA\tfileA\tcharsA\timgsA\trootB\tfileB\tcharsB\timgsB\tjaccard\tcontain\tcommon\tonlyA\tonlyB\n')
        for a, b, jac, cont, c, oa, ob in near:
            f.write(f"{a['root']}\t{a['file']}\t{len(a['text'])}\t{len(set(a['seq']))}\t{b['root']}\t{b['file']}\t{len(b['text'])}\t{len(set(b['seq']))}\t{jac:.2f}\t{cont:.2f}\t{c}\t{oa}\t{ob}\n")
    cls = collections.Counter()
    for a, b, jac, cont, c, oa, ob in near:
        cls['A subset of B' if oa == 0 and ob > 0 else 'B subset of A' if ob == 0 and oa > 0 else 'same images' if oa == 0 and ob == 0 else 'mixed'] += 1
    print(dict(cls))

main()
