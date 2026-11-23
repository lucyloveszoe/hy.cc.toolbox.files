#!/usr/bin/env python3
"""Read-only: compare data.done/至2014年旅行记录 (text, images) against the rest of data.done:
txt library (mc txt/topics, gochina txt_merged), html report text (mc html + gochina reports_merged), and all images.
Run from the project folder with the venv python."""
import os, re, sys, csv, html, hashlib, subprocess, collections, unicodedata, concurrent.futures as cf
sys.path.insert(0, '/Users/hany/Documents/cc.self/hy.cc.toolbox.files/history-files-merge')
import clean_doc_noise, doc_to_txt

DONE = '/Users/hany/Downloads/data.done'
FOLD = DONE + '/至2014年旅行记录'
SP = os.path.dirname(os.path.abspath(__file__))
OUT = SP + '/compare_done.tsv'
MOD = 4

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

def decode(b):
    if b.startswith(b'\xff\xfe') or b.startswith(b'\xfe\xff'): return b.decode('utf-16', 'replace')
    if b.startswith(b'\xef\xbb\xbf'): b = b[3:]
    try: return b.decode('utf-8')
    except UnicodeDecodeError: return b.decode('gb18030', 'replace')

FIELD = re.compile(r'INCLUDEPICTURE\s+"[^"]*"[^\n]*|HYPERLINK\s+"[^"]*"(?:\s*\\t\s*"_blank")?')
def norm(s):
    s = FIELD.sub('', s)
    s, _ = clean_doc_noise.clean(s)
    s, _ = doc_to_txt.drop_garbage(s)
    s = unicodedata.normalize('NFKC', s)
    return re.sub(r'\s+', '', s).lower()

def textof(p):
    low = p.lower()
    if low.endswith(('.doc', '.docx', '.rtf', '.htm', '.html')):
        r = subprocess.run(['textutil', '-convert', 'txt', '-encoding', 'UTF-8', '-stdout', p], capture_output=True, timeout=120)
        return norm(r.stdout.decode('utf-8', 'replace'))
    if low.endswith('.txt'): return norm(decode(open(p, 'rb').read()))
    return None

def htmltext(p):
    t = open(p, encoding='utf-8', errors='replace').read()
    t = re.sub(r'(?is)<head>.*?</head>|<script.*?</script>|<style.*?</style>', '', t)
    return norm(html.unescape(re.sub(r'<[^>]+>', ' ', t)))

def grams(s):
    out = []
    for i in range(len(s) - 7):
        g = hash(s[i:i + 8])
        if g % MOD == 0: out.append(g)
    return out

IMGX = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
# ---------- target corpus: everything in data.done except the folder ----------
tfiles = []; imgs = {}
for dp, dn, fs in os.walk(DONE):
    if dp == FOLD or dp.startswith(FOLD + '/'): dn[:] = []; continue
    for f in fs:
        p = os.path.join(dp, f); low = f.lower()
        if low.endswith(IMGX): imgs.setdefault(sha(p), os.path.relpath(p, DONE))
        elif low.endswith('.txt') or (low.endswith('.html') and '/reports' in dp): tfiles.append(p)
print('target text/html files', len(tfiles), '| target images', len(imgs), flush=True)
fid = {}; gram_file = {}; whole = {}; stories = {}
for i, p in enumerate(sorted(tfiles)):
    fid[i] = os.path.relpath(p, DONE)
    s = htmltext(p) if p.endswith('.html') else norm(decode(open(p, 'rb').read()))
    if not s: continue
    for g in grams(s): gram_file.setdefault(g, i)
    whole[hashlib.md5(s.encode()).hexdigest()] = i
    if p.endswith('.txt'):
        mp = p[:-4] + '.manifest.csv'
        if os.path.exists(mp):
            lines = decode(open(p, 'rb').read()).split('\n')
            for r in csv.DictReader(open(mp, encoding='utf-8-sig')):
                try: a, b = int(r.get('start_line')), int(r.get('end_line'))
                except Exception: continue
                stories[hashlib.md5(norm('\n'.join(lines[a - 1:b])).encode()).hexdigest()] = i
print('gram index', len(gram_file), 'whole', len(whole), 'stories', len(stories), flush=True)

# ---------- source: the moved folder ----------
sfiles = []
for dp, dn, fs in os.walk(FOLD):
    for f in sorted(fs):
        if f != '.DS_Store': sfiles.append(os.path.join(dp, f))
ASSET = ('.php', '.js', '.css')
def one(p):
    ext = os.path.splitext(p)[1].lower()
    r = dict(path=os.path.relpath(p, DONE), ext=ext, size=os.path.getsize(p), chars='', share='', best='', bucket='')
    if ext in ASSET: r['bucket'] = 'web asset (not content)'; return r
    if ext in IMGX:
        h = sha(p); r['best'] = imgs.get(h, '')
        r['bucket'] = 'image: already in data.done' if h in imgs else 'image: new'; return r
    if ext in ('.htm', '.html'): r['bucket'] = 'saved page (compared as text)'
    try: s = textof(p)
    except Exception: r['bucket'] = 'text extract failed'; return r
    if s is None: r['bucket'] = 'other: not compared (' + ext + ')'; return r
    r['chars'] = len(s)
    if len(s) < 200: r['bucket'] = 'too short (<200 chars)'; return r
    md = hashlib.md5(s.encode()).hexdigest()
    if md in whole: r['share'] = '1.00'; r['best'] = fid[whole[md]]; r['bucket'] = 'same text (whole file/page)'; return r
    if md in stories: r['share'] = '1.00'; r['best'] = fid[stories[md]]; r['bucket'] = 'same text (a story)'; return r
    g = grams(s)
    if not g: r['bucket'] = 'too short (<200 chars)'; return r
    hit = collections.Counter(); n = 0
    for x in g:
        f = gram_file.get(x)
        if f is not None: n += 1; hit[f] += 1
    sh = n / len(g); r['share'] = f'{sh:.2f}'
    if hit: r['best'] = fid[hit.most_common(1)[0][0]]
    r['bucket'] = 'text >=0.90 in data.done' if sh >= 0.90 else ('text 0.50-0.90 in data.done' if sh >= 0.5 else 'text <0.50 (new)')
    return r

with cf.ThreadPoolExecutor(max_workers=6) as ex:
    rows = list(ex.map(one, sfiles))
cols = ['path', 'ext', 'size', 'chars', 'share', 'best', 'bucket']
with open(OUT, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, delimiter='\t'); w.writerow(cols)
    for r in rows: w.writerow([r[c] for c in cols])
print('rows', len(rows))
for k, v in collections.Counter(r['bucket'] for r in rows).most_common(): print(f'  {v:5} {k}')
by = collections.defaultdict(collections.Counter)
for r in rows: by[r['path'].split('/')[1]][r['bucket']] += 1
for o, c in sorted(by.items()): print(o, sum(c.values()), dict(c))
print('DONE')
