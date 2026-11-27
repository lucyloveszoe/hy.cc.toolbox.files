#!/usr/bin/env python3 -I
"""Quarantine exact duplicate reports in html/merges (vs library and inside merges). Dry run unless --go.
usage: quar_exact.py [--go] ; quar_exact.py check"""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD, DL
import os, re, sys, html, csv, shutil, hashlib, unicodedata, collections

DATA = DD
BASE = DATA + '/mc_2026.11.19/html'
QUAR = (DL+'/quarantine.merges.2026.11.22')
IMG = re.compile(r'<img[^>]*?src="([^"]+)"', re.I)
TAG_STATUS = ' [output file no longer in data.done]'
nfc = lambda s: unicodedata.normalize('NFC', s)
canon = lambda p: nfc(os.path.normpath(p))

def md5file(p, c={}):
    if p not in c:
        try: c[p] = hashlib.md5(open(p, 'rb').read()).hexdigest()
        except OSError: c[p] = 'MISSING'
    return c[p]

def load(path):
    t = open(path, encoding='utf-8', errors='replace').read()
    body = re.sub(r'(?is)<head>.*?</head>', '', t)
    body = re.sub(r'(?is)<h1[^>]*>.*?</h1>', '', body, count=1)
    srcs = [html.unescape(x) for x in IMG.findall(body)]
    text = re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]+>', '', body))).lower()
    return text, [s for s in srcs if not s.startswith(('http', 'data:'))]

def scan(group):
    rows = []
    g = os.path.join(BASE, group)
    for root in sorted(os.listdir(g)):
        rp = os.path.join(g, root, 'reports')
        if not os.path.isdir(rp): continue
        for fn in sorted(os.listdir(rp)):
            if not fn.endswith('.html'): continue
            p = os.path.join(rp, fn)
            text, srcs = load(p)
            imgs = [canon(os.path.join(rp, s)) for s in srcs]
            seq = tuple(md5file(i) for i in imgs)
            rows.append(dict(group=group, root=root, file=fn, path=p, imgs=imgs, seq=seq,
                             key=hashlib.md5((text + '|' + ','.join(seq)).encode()).hexdigest()))
    return rows

def all_csvs():
    for d, _, fs in os.walk(DATA):
        for f in fs:
            if f.lower().endswith('.csv'): yield os.path.join(d, f)

def read_csv(p):
    raw = open(p, 'rb').read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    eol = '\r\n' if b'\r\n' in raw else '\n'
    rows = list(csv.reader(raw.decode('utf-8-sig').splitlines(True) if False else __import__('io').StringIO(raw.decode('utf-8-sig'), newline='')))
    return rows, bom, eol

def write_csv(p, rows, bom, eol):
    with open(p, 'w', encoding='utf-8-sig' if bom else 'utf-8', newline='') as f:
        csv.writer(f, lineterminator=eol).writerows(rows)

def check():
    bad_links = orph = 0
    for grp in ('merges', 'topics', 'locations'):
        for r in scan(grp): pass
    linked = set(); n = 0
    for grp in ('merges', 'topics', 'locations'):
        for r in scan(grp):
            for i in r['imgs']:
                n += 1
                if not os.path.exists(i): bad_links += 1
                linked.add(i)
    for grp in ('merges', 'topics', 'locations'):
        for root in os.listdir(os.path.join(BASE, grp)):
            d = os.path.join(BASE, grp, root, 'images')
            for dp, _, fs in os.walk(d):
                for f in fs:
                    if f in ('.DS_Store', 'manifest.csv'): continue
                    if canon(os.path.join(dp, f)) not in linked: orph += 1
    miss = tot = 0
    for p in all_csvs():
        rows, _, _ = read_csv(p)
        if not rows or 'output' not in rows[0]: continue
        k = rows[0].index('output')
        for r in rows[1:]:
            if len(r) > k and r[k]:
                tot += 1
                if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(p), r[k]))): miss += 1
    print(f'links {n}, broken {bad_links}, orphans {orph}, csv outputs {tot}, missing {miss}')

def main(go):
    m = scan('merges'); lib = scan('topics') + scan('locations')
    libkeys = {}
    for r in lib: libkeys.setdefault(r['key'], r)
    groups = collections.defaultdict(list)
    for r in m: groups[r['key']].append(r)
    root_order = {n: i for i, n in enumerate(sorted(os.listdir(BASE + '/merges')))}
    removed = []  # (report, kept_path, kind)
    for k, v in groups.items():
        if k in libkeys:
            for r in v: removed.append((r, libkeys[k]['path'], 'LIB'))
        elif len(v) > 1:
            v = sorted(v, key=lambda r: (-len(set(r['seq'])), -len(r['file']), root_order[r['root']], r['path']))
            for r in v[1:]: removed.append((r, v[0]['path'], 'INTERNAL'))
    rem_paths = {canon(r['path']) for r, _, _ in removed}
    print('to quarantine:', len(removed), 'LIB', sum(1 for x in removed if x[2] == 'LIB'), 'INTERNAL', sum(1 for x in removed if x[2] == 'INTERNAL'))
    # image link map over every report that stays
    stay_links = collections.defaultdict(set); stay_md5 = set()
    for r in m + lib:
        if canon(r['path']) in rem_paths: continue
        for i, h in zip(r['imgs'], r['seq']):
            stay_links[i].add(r['path']); stay_md5.add(h)
    move_imgs = set()
    for r, _, _ in removed:
        for i in r['imgs']:
            if i not in stay_links and os.path.exists(i): move_imgs.add(i)
    no_copy = [i for i in move_imgs if md5file(i) not in stay_md5]
    print('exclusive images to move:', len(move_imgs), 'without byte-identical stay copy:', len(no_copy))
    assert not no_copy
    # CSV plan
    move_files = {canon(r['path']): kept for r, kept, _ in removed}
    csv_changes = {}; nrow = 0
    for p in all_csvs():
        rows, bom, eol = read_csv(p)
        if not rows or 'output' not in rows[0]: continue
        h = rows[0]; k = h.index('output'); dirn = os.path.dirname(p)
        hit = []
        for ri, r in enumerate(rows[1:], 1):
            if len(r) > k and r[k]:
                t = canon(os.path.join(dirn, r[k]))
                if t in move_files or t in move_imgs: hit.append((ri, t))
        if hit: csv_changes[p] = (rows, bom, eol, hit); nrow += len(hit)
    print('csv files touched:', len(csv_changes), 'rows to blank:', nrow)
    if not go: print('DRY RUN'); return
    assert not os.path.exists(QUAR)
    os.makedirs(QUAR + '/files'); os.makedirs(QUAR + '/bak_csv')
    # backups of csv
    for p in csv_changes:
        dst = QUAR + '/bak_csv/' + os.path.relpath(p, DATA); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(p, dst)
    with open(QUAR + '/removed_to_kept.tsv', 'w', encoding='utf-8') as f:
        f.write('kind\tremoved\tkept\n')
        for r, kept, kind in removed: f.write(f"{kind}\t{os.path.relpath(r['path'], BASE)}\t{os.path.relpath(kept, BASE)}\n")
    with open(QUAR + '/images_moved.txt', 'w', encoding='utf-8') as f:
        for i in sorted(move_imgs): f.write(os.path.relpath(i, BASE) + '\n')
    # CSV rewrite
    for p, (rows, bom, eol, hit) in csv_changes.items():
        h = rows[0]; k = h.index('output')
        manifest = 'status' in h
        if not manifest and 'note' not in h:
            h.append('note')
            for r in rows[1:]: r.append('')
        for ri, t in hit:
            r = rows[ri]
            if manifest:
                s = h.index('status'); r[s] = (r[s] if len(r) > s else '') + TAG_STATUS
            else:
                kept = move_files.get(t)
                n = h.index('note')
                while len(r) <= n: r.append('')
                r[n] = f"[duplicate of {os.path.basename(kept)}; moved to quarantine]" if kept else '[output file no longer in data.done]'
            r[k] = ''
        write_csv(p, rows, bom, eol)
    # move files
    for pth in list(rem_paths) + sorted(move_imgs):
        dst = QUAR + '/files/' + os.path.relpath(pth, BASE); os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(pth, dst)
    print('DONE; quarantine at', QUAR)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'check': check()
    else: main('--go' in sys.argv)
