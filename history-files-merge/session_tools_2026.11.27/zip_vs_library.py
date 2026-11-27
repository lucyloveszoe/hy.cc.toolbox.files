"""READ-ONLY: which pages / loose images of each zip are already in the library (PROCESSING_LOGIC 2).

    python3 -I zip_vs_library.py <project dir> <inputs dir> <data.done>

A page counts as found when any tail of its zip path (or its base name) equals a summary "page" value anywhere under
data.done (lower case, whitespace-free, NFC). Names are decoded with extract_zip.fixname. Pages inside *_files/ and
non-page assets are not counted. Run it before extracting: zips that are fully found were processed already."""
import sys, os, zipfile, csv, unicodedata, re, collections
sys.path.insert(0, os.path.join(sys.argv[1], 'session_tools_2026.11.19'))
from extract_zip import fixname
INP, DD = sys.argv[2], sys.argv[3]
k = lambda s: re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())
pages_full, pages_base = set(), set()
img_manifest = set()
for d, _, fs in os.walk(DD):
    for f in fs:
        if not f.endswith('.csv'): continue
        p = os.path.join(d, f)
        rd = csv.DictReader(open(p, encoding='utf-8-sig', newline=''))
        if not rd.fieldnames: continue
        col = 'page' if 'page' in rd.fieldnames else ('source_file' if 'source_file' in rd.fieldnames else None)
        if not col: continue
        for r in rd:
            v = (r.get(col) or '').replace('\\', '/')
            if not v: continue
            (pages_full if col == 'page' else img_manifest).add(k(v))
            if col == 'page': pages_base.add(k(os.path.basename(v)))
            else: img_manifest.add(k(os.path.basename(v)))
seen = {}
for z in sorted(os.listdir(INP)):
    if not z.endswith('.zip'): continue
    zf = zipfile.ZipFile(os.path.join(INP, z))
    c = collections.Counter(); found = collections.Counter()
    for info in zf.infolist():
        n = fixname(info)
        if n.endswith('/'): continue
        b = os.path.basename(n); ext = os.path.splitext(b)[1].lower()
        if '_files/' in n.lower() or 'thumbs.db' in b.lower() or b.startswith('.') or '__macosx' in n.lower(): 
            if ext in ('.jpg','.jpeg','.png','.gif','.bmp') and '_files/' not in n.lower(): pass
            else: continue
        if ext in ('.htm', '.html'): kind = 'page'
        elif ext in ('.jpg','.jpeg','.png','.gif','.bmp'): kind = 'img'
        elif ext in ('.doc','.docx','.txt','.pdf','.rtf'): kind = 'doc'
        else: kind = 'other'
        c[kind] += 1
        if kind == 'page':
            parts = n.split('/')
            hit = any(k('/'.join(parts[i:])) in pages_full for i in range(len(parts))) or k(b) in pages_base
            found[kind] += hit
        elif kind == 'img':
            parts = n.split('/')
            found[kind] += any(k('/'.join(parts[i:])) in img_manifest for i in range(len(parts)))
        elif kind == 'doc':
            found[kind] += any(k(b) in x for x in ()) 
    tops = collections.Counter(fixname(i).split('/')[0] for i in zf.infolist())
    print(f"{z:24} pages {c['page']:5} found {found['page']:5} | imgs(loose) {c['img']:5} found {found['img']:5} | doc {c['doc']:3} other {c['other']:4} | top: {', '.join(t for t,_ in tops.most_common(3))[:60]}")
