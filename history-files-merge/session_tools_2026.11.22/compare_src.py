#!/usr/bin/env python3
"""Read-only: compare the content of the 2018.06.18 source folder (+ its zips, extracted in the scratchpad) against
data.frozen/Reports.series-2026.11.17 by bytes (sha256, size+type), by cleaned text (8-gram share) and by image hash.
Run from the project folder with the venv python (imports clean_doc_noise / doc_to_txt from there)."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import PROJ, DD, DL
import os, re, sys, csv, zipfile, hashlib, subprocess, collections, unicodedata, concurrent.futures as cf
sys.path.insert(0, PROJ)
import clean_doc_noise, doc_to_txt

SRC = (DL+'/data/2018.06.18_report_word_doc_txt_imgs')
TGT = (DL+'/data.frozen/Reports.series-2026.11.17')
DONE = DD
SP = os.path.dirname(os.path.abspath(__file__))
ZIPS = SP + '/src_zips'
OUT = SP + '/compare_src.tsv'
MOD = 4  # sample 1/4 of the n-grams on both sides (same rule), 8-grams

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

def ftype(p):
    with open(p, 'rb') as f: h = f.read(8)
    if h.startswith(b'\xd0\xcf\x11\xe0'): return 'ole-doc'
    if h.startswith(b'PK'):
        try:
            n = zipfile.ZipFile(p).namelist()
            return 'docx' if any(x.startswith('word/') for x in n) else 'zip'
        except Exception: return 'zip?'
    if h.startswith(b'%PDF'): return 'pdf'
    if h.startswith(b'\xff\xd8\xff'): return 'jpg'
    if h.startswith(b'\x89PNG'): return 'png'
    if h.startswith(b'GIF8'): return 'gif'
    if h.startswith(b'MZ'): return 'exe'
    if h.startswith(b'{\\rtf'): return 'rtf'
    return 'text/other'

def decode(b):
    if b.startswith(b'\xff\xfe') or b.startswith(b'\xfe\xff'): return b.decode('utf-16', 'replace')
    if b.startswith(b'\xef\xbb\xbf'): b = b[3:]
    try: return b.decode('utf-8')
    except UnicodeDecodeError: return b.decode('gb18030', 'replace')

FIELD = re.compile(r'INCLUDEPICTURE\s+"[^"]*"[^\n]*|HYPERLINK\s+"[^"]*"(?:\s*\\t\s*"_blank")?')
def textof(p, t):
    if t in ('ole-doc', 'docx', 'rtf') or p.lower().endswith(('.htm', '.html')):
        r = subprocess.run(['textutil', '-convert', 'txt', '-encoding', 'UTF-8', '-stdout', p], capture_output=True, timeout=120)
        s = r.stdout.decode('utf-8', 'replace')
    elif t == 'text/other': s = decode(open(p, 'rb').read())
    else: return None
    s = FIELD.sub('', s)
    s, _ = clean_doc_noise.clean(s)
    s, _ = doc_to_txt.drop_garbage(s)
    s = unicodedata.normalize('NFKC', s)
    return re.sub(r'\s+', '', s).lower()

def grams(s):
    out = []
    for i in range(len(s) - 7):
        g = hash(s[i:i + 8])
        if g % MOD == 0: out.append(g)
    return out

def walk(base):
    for dp, dn, fs in os.walk(base):
        dn[:] = sorted(dn)
        for f in sorted(fs):
            if f == '.DS_Store' or f.startswith('~$'): continue
            yield os.path.join(dp, f)

# ---------------- target corpus ----------------
tfiles = list(walk(TGT))
tinfo = {}
for p in tfiles:
    tinfo[p] = dict(size=os.path.getsize(p), type=ftype(p), sha=sha(p))
print('target files', len(tfiles), collections.Counter(v['type'] for v in tinfo.values()), flush=True)
t_by_sha = collections.defaultdict(list); t_by_sizetype = collections.defaultdict(list)
for p, v in tinfo.items():
    t_by_sha[v['sha']].append(p); t_by_sizetype[(v['size'], v['type'])].append(p)
# target text (txt library files; docx; csv manifests are not content)
ttext = {}
for p, v in tinfo.items():
    if p.lower().endswith('.csv'): continue
    s = textof(p, v['type'])
    if s: ttext[p] = s
print('target text units', len(ttext), 'chars', sum(len(s) for s in ttext.values()), flush=True)
gram_file = {}
fid = {}
for i, (p, s) in enumerate(sorted(ttext.items())):
    fid[i] = p
    for g in grams(s): gram_file.setdefault(g, i)
whole = {}
for p, s in ttext.items(): whole[hashlib.md5(s.encode()).hexdigest()] = p
# stories inside txt library files (manifest ranges) for exact story match
stories = {}
for p in ttext:
    if p.endswith('.txt'):
        mp = p[:-4] + '.manifest.csv'
        if os.path.exists(mp):
            lines = open(p, encoding='utf-8').read().split('\n')
            for r in csv.DictReader(open(mp, encoding='utf-8-sig')):
                try: s, e = int(r.get('start_line')), int(r.get('end_line'))
                except Exception: continue
                seg = re.sub(r'\s+', '', unicodedata.normalize('NFKC', '\n'.join(lines[s - 1:e]))).lower()
                stories[hashlib.md5(seg.encode()).hexdigest()] = p
print('target stories', len(stories), flush=True)
# target embedded images
timg = {}
for p, v in tinfo.items():
    if v['type'] == 'docx':
        z = zipfile.ZipFile(p)
        for n in z.namelist():
            if n.startswith('word/media/'):
                timg.setdefault(hashlib.sha256(z.read(n)).hexdigest(), p)
print('target embedded images', len(timg), flush=True)
# data.done image hashes (informational)
dimg = {}
for dp, _, fs in os.walk(DONE):
    for f in fs:
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
            dimg[sha(os.path.join(dp, f))] = 1
print('data.done image hashes', len(dimg), flush=True)

# ---------------- source ----------------
def origin(p):
    if p.startswith(ZIPS): return 'zip:' + os.path.relpath(p, ZIPS).split('/')[0]
    rel = os.path.relpath(p, SRC); return rel.split('/')[0] if '/' in rel else '(top)'
sfiles = [p for p in walk(SRC) if not p.endswith('.zip')] + list(walk(ZIPS))
print('source files', len(sfiles), flush=True)
ASSET = ('.php', '.js', '.css')

def one(p):
    ext = os.path.splitext(p)[1].lower()
    r = dict(path=p, origin=origin(p), ext=ext, size=os.path.getsize(p), type=ftype(p))
    r['sha'] = sha(p)
    r['byte_match'] = os.path.relpath(t_by_sha[r['sha']][0], TGT) if r['sha'] in t_by_sha else ''
    st = t_by_sizetype.get((r['size'], r['type']), [])
    r['size_type_cand'] = len(st) if not r['byte_match'] else 0
    r['img_in_target_docx'] = ''; r['img_in_done'] = ''
    r['chars'] = ''; r['share'] = ''; r['best'] = ''; r['bucket'] = ''
    if ext in ASSET: r['bucket'] = 'web asset (not content)'; return r
    if r['type'] in ('jpg', 'png', 'gif'):
        r['img_in_target_docx'] = 'yes' if r['sha'] in timg else 'no'; r['img_in_done'] = 'yes' if r['sha'] in dimg else 'no'
        r['bucket'] = 'image: in target docx' if r['sha'] in timg else ('image: only in data.done' if r['sha'] in dimg else 'image: not found'); return r
    if r['type'] in ('pdf', 'exe', 'zip', 'zip?'):
        r['bucket'] = ('byte-identical' if r['byte_match'] else f'{r["type"]}: no text compare'); return r
    try: s = textof(p, r['type'])
    except Exception as e: r['bucket'] = 'text extract failed'; return r
    if s is None: r['bucket'] = 'not compared'; return r
    r['chars'] = len(s)
    if len(s) < 200: r['bucket'] = 'too short (<200 chars)'; return r
    md = hashlib.md5(s.encode()).hexdigest()
    if md in whole: r['share'] = '1.00'; r['best'] = os.path.relpath(whole[md], TGT); r['bucket'] = 'same text (whole file)'; return r
    if md in stories: r['share'] = '1.00'; r['best'] = os.path.relpath(stories[md], TGT); r['bucket'] = 'same text (a story)'; return r
    g = grams(s)
    if not g: r['bucket'] = 'too short (<200 chars)'; return r
    hit = collections.Counter(); n = 0
    for x in g:
        f = gram_file.get(x)
        if f is not None: n += 1; hit[f] += 1
    sh = n / len(g); r['share'] = f'{sh:.2f}'
    if hit: r['best'] = os.path.relpath(fid[hit.most_common(1)[0][0]], TGT)
    r['bucket'] = 'text >=0.90 in target' if sh >= 0.90 else ('text 0.50-0.90 in target' if sh >= 0.5 else 'text <0.50 (new)')
    return r

with cf.ThreadPoolExecutor(max_workers=6) as ex:
    rows = list(ex.map(one, sfiles))
cols = ['origin', 'path', 'ext', 'type', 'size', 'sha', 'byte_match', 'size_type_cand', 'img_in_target_docx', 'img_in_done', 'chars', 'share', 'best', 'bucket']
with open(OUT, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, delimiter='\t'); w.writerow(cols)
    for r in rows: w.writerow([r[c] for c in cols])
print('rows', len(rows))
tot = collections.Counter(r['bucket'] for r in rows); print(dict(tot))
by = collections.defaultdict(collections.Counter)
for r in rows: by[r['origin']][r['bucket']] += 1
for o, c in sorted(by.items()): print(o, sum(c.values()), dict(c))
print('byte-identical to a target file (any name):', sum(1 for r in rows if r['byte_match']))
print('same size+type as a target file but different bytes:', sum(1 for r in rows if r['size_type_cand']))
