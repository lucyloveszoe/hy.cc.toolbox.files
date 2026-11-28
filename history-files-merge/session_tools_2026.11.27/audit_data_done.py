"""READ-ONLY audit of DD (PROCESSING_LOGIC 10), three buckets with their own rules.

    python3 -I audit_data_done.py [DD]          prints a report; exit code 0 = no problems, 1 = problems found

Changes nothing. Known by-design items are reported as INFO and not counted (hk9394's CSVs list only its newer pages;
page texts shared by separate collections).

html report sets  links (img src / a href) resolve, no remote images, well-formed (</html>, balanced <section>),
                  image files are real images with the right extension, no orphan images, every page / image listed
                  in the set's CSVs (where the set has CSVs), exact duplicate pages (visible text md5 + image SHA-256
                  sequence) inside a set and across sets
images-only       every image folder with a manifest (mc_2026.11.19/images-only + images_merged.manifest.csv, and any
                  <folder> + <folder>.manifest.csv with columns file, sha256): one row per file, SHA-256 matches,
                  unique names (NFC / lower case), no fake images, no html links it
raw archive       旅行记录: links of its html pages resolve
txt               UTF-8, manifest checks (no 1..N, first story at line 1, one blank line between stories, ranges, no
                  blank edge lines, chars), noise (watermark, garbage runs, U+FFFD, private-use, control, zero-width,
                  [image missing], html entities)
global            CSV 'output' cells that do not resolve; empty folders
"""
import collections
import csv
import hashlib
import html
import os
import re
import sys
import unicodedata

DD = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Downloads/data.done')
MC = os.path.join(DD, 'mc_2026.11.19')
IMG_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
nfc = lambda p: unicodedata.normalize('NFC', os.path.normpath(p))
_sha = {}


def sha(p):
    if p not in _sha:
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
        _sha[p] = h.hexdigest()
    return _sha[p]


def sniff(p):
    b = open(p, 'rb').read(8)
    return ('jpg' if b[:3] == b'\xff\xd8\xff' else 'png' if b[:4] == b'\x89PNG' else 'gif' if b[:4] == b'GIF8'
            else 'bmp' if b[:2] == b'BM' else None)


def outs(csvp):
    if not csvp or not os.path.exists(csvp):
        return None
    d = os.path.dirname(csvp)
    return {nfc(os.path.join(d, r['output'])) for r in csv.DictReader(open(csvp, encoding='utf-8-sig')) if r.get('output')}


def sets():
    S = []
    for g in ('locations', 'topics'):
        base = os.path.join(MC, 'html', g)
        for r in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            R = os.path.join(base, r)
            if os.path.isdir(R):
                S.append((f'mc/{g}/{r}', [os.path.join(R, 'reports')], [os.path.join(R, 'images')],
                          os.path.join(R, f'{r}_summary.csv'), os.path.join(R, f'{r}_images_manifest.csv')))
    R = os.path.join(MC, 'html', 'mcjt-total')
    if os.path.isdir(R):
        S.append(('mc/mcjt-total', [os.path.join(R, 'reports')], [os.path.join(R, 'images')],
                  os.path.join(R, 'mcjt-total_summary.csv'), os.path.join(R, 'mcjt-total_images_manifest.csv')))
    G = os.path.join(DD, 'gochina_2026.11.19', 'reports_merged')
    S.append(('gochina', [os.path.join(G, 'gochina')], [os.path.join(G, 'gochina', 'images')],
              os.path.join(G, 'gochina_summary.csv'), os.path.join(G, 'gochina_images_manifest.csv')))
    G = os.path.join(DD, '141_2026.11.25', 'html')  # layout since 2026-11-28 (was reports_merged/)
    if not os.path.isdir(G):
        G = os.path.join(DD, '141_2026.11.25', 'reports_merged')
    S.append(('141 (141 + 141-U)', [os.path.join(G, '141'), os.path.join(G, '141-U')],
              [os.path.join(G, '141', 'images'), os.path.join(G, '141-U', 'images')],
              os.path.join(G, '141_summary.csv'), os.path.join(G, '141_images_manifest.csv')))
    F = os.path.join(DD, 'FDZone_2026.11.27')
    S.append(('FDZone', [os.path.join(F, 'reports')], [os.path.join(F, 'images')],
              os.path.join(F, 'FDZone_summary.csv'), os.path.join(F, 'FDZone_images_manifest.csv')))
    H = os.path.join(DD, 'hk9394_2026.11.27')
    S.append(('hk9394 (CSVs list the 54 newer pages only)', [H], [os.path.join(H, 'images')],
              os.path.join(H, 'hk9394_summary.csv'), os.path.join(H, 'hk9394_images_manifest.csv')))
    T = os.path.join(DD, '2010_01+04+07.Reports')
    for s in sorted(os.listdir(T)) if os.path.isdir(T) else []:
        if os.path.isdir(os.path.join(T, s)):
            S.append((f'2010/{s}', [os.path.join(T, s)], [os.path.join(T, s, 'images')],
                      os.path.join(T, f'{s}_summary.csv'), os.path.join(T, f'{s}_images_manifest.csv')))
    return S


def page_files(dirs, recursive=False):
    out = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        if recursive:
            for dd, _, fs in os.walk(d):
                out += [os.path.join(dd, f) for f in fs if f.lower().endswith(('.html', '.htm'))]
        else:
            out += [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(('.html', '.htm'))]
    return out


def image_files(dirs):
    out = []
    for d in dirs:
        for dd, _, fs in os.walk(d):
            out += [os.path.join(dd, f) for f in fs if f != '.DS_Store' and not f.endswith('.csv')]   # per-report manifest.csv
    return out


REF = re.compile(r'<(img|a)\b[^>]*?\s(src|href)="([^"]*)"', re.I)


def scan_page(p):
    t = open(p, encoding='utf-8', errors='replace').read()
    links, broken, remote = [], 0, 0
    for tag, _, v in REF.findall(t):
        if not v or v.startswith('#'):
            continue
        if re.match(r'^[a-z]+:', v, re.I):
            remote += tag.lower() == 'img'
            continue
        q = nfc(os.path.join(os.path.dirname(p), html.unescape(v).split('#')[0]))
        if os.path.exists(q):
            links.append(q)
        else:
            broken += 1
    mal = not t.rstrip().endswith('</html>') or t.count('<section>') != t.count('</section>')
    body = re.sub(r'(?is)<head>.*?</head>|<h1.*?</h1>', '', t)
    vis = re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]+>', '', body)).lower())
    return links, broken, remote, mal, vis


def audit_html():
    print('=== html report sets')
    print(f'{"set":46} {"pages":>6} {"imgs":>6} {"broken":>6} {"remote":>6} {"malf":>5} {"orphan":>6} {"fake":>5}'
          f' {"no-sum":>6} {"no-man":>6} {"dupIn":>5}')
    sig_owner = collections.defaultdict(set)
    tot = collections.Counter()
    for name, pdirs, idirs, scsv, mcsv in sets():
        pages = page_files(pdirs)
        imgs = [nfc(x) for x in image_files(idirs)]
        linked, br, rem, mal = set(), 0, 0, 0
        sigs = collections.Counter()
        for p in pages:
            l, b, r, m, vis = scan_page(p)
            linked.update(l)
            br += b
            rem += r
            mal += m
            imgs_seq = tuple(sha(q) for q in l if q.lower().endswith(IMG_EXT) and os.path.isfile(q))
            s = hashlib.md5(vis.encode()).hexdigest() + '|' + ','.join(imgs_seq)
            sigs[s] += 1
            sig_owner[s].add(name.split(' ')[0])
        orphan = len(set(imgs) - linked)
        fake = sum(1 for q in imgs if sniff(q) is None or os.path.splitext(q)[1].lower().lstrip('.').replace('jpeg', 'jpg')
                   != sniff(q))
        so, mo = outs(scsv), outs(mcsv)
        nosum = len({nfc(p) for p in pages} - so) if so is not None else '-'
        noman = len(set(imgs) - mo) if mo is not None else '-'
        if not name.startswith('hk9394'):              # hk9394: CSVs cover the newer pages only (by design)
            tot['unlisted'] += (nosum if nosum != '-' else 0) + (noman if noman != '-' else 0)
        dup = sum(v - 1 for v in sigs.values() if v > 1)
        print(f'{name[:46]:46} {len(pages):6} {len(imgs):6} {br:6} {rem:6} {mal:5} {orphan:6} {fake:5} {nosum!s:>6} {noman!s:>6} {dup:5}')
        for k, v in (('pages', len(pages)), ('imgs', len(imgs)), ('broken', br), ('remote', rem), ('malformed', mal),
                     ('orphan', orphan), ('fake', fake), ('dup in set', dup)):
            tot[k] += v
    cross = sum(1 for s, o in sig_owner.items() if len(o) > 1)
    print('TOTAL', dict(tot))
    print(f'INFO page texts shared by 2+ separate collections: {cross}')
    return sum(tot[k] for k in ('broken', 'remote', 'malformed', 'orphan', 'fake', 'dup in set')) + tot['unlisted']


def audit_images_only():
    print('=== images-only')
    linked = set()
    for dd, _, fs in os.walk(DD):
        for f in fs:
            if f.lower().endswith(('.html', '.htm')):
                linked.update(scan_page(os.path.join(dd, f))[0])
    mcf = 'images-only' if os.path.isdir(os.path.join(MC, 'images-only')) else 'images'  # renamed back 2026-11-28
    pairs = [(f'mc_2026.11.19/{mcf}', os.path.join(MC, mcf), os.path.join(MC, 'images_merged.manifest.csv'))]
    for dd, ds, fs in os.walk(DD):
        for f in fs:
            if f.endswith('.manifest.csv') and f != 'images_merged.manifest.csv' and os.path.isdir(os.path.join(dd, f[:-13])):
                h = next(csv.reader(open(os.path.join(dd, f), encoding='utf-8-sig')), [])
                if 'file' in h and 'sha256' in h:
                    pairs.append((os.path.relpath(os.path.join(dd, f[:-13]), DD), os.path.join(dd, f[:-13]), os.path.join(dd, f)))
    problems = 0
    for label, folder, man in pairs:
        if not os.path.isdir(folder):
            continue
        files = sorted(os.path.relpath(os.path.join(d, f), folder) for d, _, fs in os.walk(folder) for f in fs if f != '.DS_Store')
        rows = list(csv.DictReader(open(man, encoding='utf-8-sig')))
        byname = {r['file']: r for r in rows}
        bad_sha = sum(1 for f in files if f in byname and sha(os.path.join(folder, f)) != byname[f]['sha256'])
        no_row = sum(1 for f in files if f not in byname)
        no_file = len(set(byname) - set(files))
        keys = collections.Counter(re.sub(r'\s+', '', unicodedata.normalize('NFC', f).lower()) for f in files)
        clash = sum(v - 1 for v in keys.values() if v > 1)
        fake = sum(1 for f in files if sniff(os.path.join(folder, f)) is None)
        dsha = collections.Counter(sha(os.path.join(folder, f)) for f in files)
        lk = sum(1 for f in files if nfc(os.path.join(folder, f)) in linked)
        print(f'{label}: files {len(files)} rows {len(rows)} | sha mismatch {bad_sha} | file without row {no_row} | '
              f'row without file {no_file} | name clashes {clash} | fake {fake} | duplicate sha '
              f'{sum(v - 1 for v in dsha.values() if v > 1)} | linked by html {lk}')
        problems += bad_sha + no_row + no_file + clash + fake + lk
    return problems


def audit_raw_archive():
    print('=== raw archive 旅行记录')
    T = os.path.join(DD, '旅行记录_2026.11.23')
    if not os.path.isdir(T):
        return 0
    pages = broken = 0
    for dd, _, fs in os.walk(T):
        if re.search(r'_files(/|$)', os.path.relpath(dd, T)):
            continue
        for f in fs:
            if f.lower().endswith(('.html', '.htm')):
                pages += 1
                broken += scan_page(os.path.join(dd, f))[1]
    print(f'pages {pages} | broken links {broken}')
    return broken


TXT_NOISE = {'watermark': r'本帖来源\s*https?://www\.maichun\.org|买春堂版权所有', 'fffd': '�',
             'private-use': '[-]', 'control': '[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',
             'zero-width': '[​-‏‪-‮⁠﻿]', '[image missing]': r'\[image missing\]',
             'html entity': r'&#\d+;|&#x[0-9a-f]+;|&nbsp;'}


def garbage_runs(t):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from clean_text_docs import RUN, jammerish
    n = 0
    for m in RUN.finditer(t):
        toks = m.group(0).split()
        punct = sum(bool(re.search(r'[^\w\s]', x)) for x in toks)
        if len(toks) >= 5 and sum(map(jammerish, toks)) >= 0.6 * len(toks) and punct >= 1 and len(set(toks)) > 2 \
                and not all(x in '-=*_.~' for x in toks):
            n += 1
    return n


def check_manifest(txt, man):
    L = open(txt, encoding='utf-8').read().split('\n')
    rows = list(csv.DictReader(open(man, encoding='utf-8-sig')))
    errs = []
    prev = 0
    for i, r in enumerate(rows, 1):
        s, e, c = int(r['start_line']), int(r['end_line']), int(r['chars'])
        if int(r['no']) != i:
            errs.append('no')
        if i == 1 and s != 1:
            errs.append('first')
        if i > 1 and s != prev + 2:
            errs.append('gap')
        if not (1 <= s <= e <= len(L)) or not L[s - 1].strip() or not L[e - 1].strip():
            errs.append('range/edge')
        elif c != len('\n'.join(L[s - 1:e])):
            errs.append('chars')
        prev = e
    inside = set()
    for r in rows:
        inside.update(range(int(r['start_line']), int(r['end_line']) + 1))
    outside = sum(1 for i, l in enumerate(L, 1) if l.strip() and i not in inside)   # non-blank lines in no story
    return rows, collections.Counter(errs), outside, 0


def audit_txt():
    print('=== txt')
    pairs = []
    T = os.path.join(MC, 'txt', 'topics')
    for f in sorted(os.listdir(T)):
        if f.endswith('.txt'):
            pairs.append((f'mc topics/{f}', os.path.join(T, f), os.path.join(T, f[:-4] + '.manifest.csv')))
    for label, d in (('141', '141_2026.11.25'), ('FDZone', 'FDZone_2026.11.27'), ('hk9394', 'hk9394_2026.11.27'),
                     ('gochina', 'gochina_2026.11.19')):
        p = os.path.join(DD, d, 'txt_merged.txt')
        if not os.path.exists(p):  # 141 since 2026-11-28: txt/txt_merged.txt
            p = os.path.join(DD, d, 'txt', 'txt_merged.txt')
        if os.path.exists(p):
            pairs.append((f'{label}/txt_merged.txt', p, p[:-4] + '.manifest.csv'))
    tot = collections.Counter()
    bad = []
    for label, p, m in pairs:
        b = open(p, 'rb').read()
        try:
            t = b.decode('utf-8')
        except UnicodeDecodeError:
            bad.append((label, 'not utf-8'))
            continue
        noise = {k: len(re.findall(v, t)) for k, v in TXT_NOISE.items()}
        noise['garbage run'] = garbage_runs(t)
        if b.startswith(b'\xef\xbb\xbf'):
            noise['bom'] = 1
        if b'\r' in b:
            noise['crlf'] = 1
        for k, v in noise.items():
            tot[k] += v
        if os.path.exists(m):
            rows, errs, outside, _ = check_manifest(p, m)
            tot['stories'] += len(rows)
            if errs or outside:
                bad.append((label, dict(errs), f'non-blank lines outside any story: {outside}'))
        else:
            tot['files without manifest'] += 1
            bad.append((label, 'no manifest'))
        if any(v for v in noise.values()):
            bad.append((label, {k: v for k, v in noise.items() if v}))
    print(f'files {len(pairs)} | stories (manifest rows) {tot["stories"]} | noise totals '
          f'{ {k: v for k, v in tot.items() if k not in ("stories",) and v} }')
    for x in bad[:30]:
        print('  ', x)
    return len(bad)


def audit_global():
    print('=== global')
    miss = 0
    for dd, _, fs in os.walk(DD):
        for f in fs:
            if not f.endswith('.csv'):
                continue
            p = os.path.join(dd, f)
            rd = csv.DictReader(open(p, encoding='utf-8-sig'))
            if not rd.fieldnames:
                continue
            if f == 'images_merged.manifest.csv' and 'file' in rd.fieldnames:
                base = next((os.path.join(dd, x) for x in ('images-only', 'images') if os.path.isdir(os.path.join(dd, x))), dd)
                miss += sum(1 for r in rd if r['file'] and not os.path.exists(os.path.join(base, r['file'])))
            elif 'output' in rd.fieldnames:
                miss += sum(1 for r in rd if r['output'] and not os.path.exists(os.path.join(dd, r['output'])))
    empty = [os.path.relpath(dd, DD) for dd, ds, fs in os.walk(DD) if not ds and not [f for f in fs if f != '.DS_Store']]
    print(f'CSV output cells that do not resolve: {miss} | empty folders: {len(empty)} {empty[:6]}')
    return miss + len(empty)


if __name__ == '__main__':
    print(f'audit of {DD} (read-only)')
    p = {'global': audit_global(), 'html': audit_html(), 'images-only': audit_images_only(),
         'raw archive': audit_raw_archive(), 'txt': audit_txt()}
    print('=== PROBLEMS', sum(p.values()), p)
    sys.exit(1 if sum(p.values()) else 0)
