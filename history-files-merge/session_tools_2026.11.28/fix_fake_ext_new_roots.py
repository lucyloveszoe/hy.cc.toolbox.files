"""Fake-image sniff + wrong-extension fix for new layout-A roots, BEFORE de-dup (PROCESSING_LOGIC 4.1, 2026-11-28 lesson).

    python3 -I fix_fake_ext_new_roots.py <out base> [--go --quarantine Q]

For every file under <out base>/<root>/{images,images.only}/:
  * header is not jpg/png/gif/bmp (0 bytes, HTML error page) -> FAKE: links in the root's report pages become
    '[image missing]', the file moves to Q (+ Q/not_images.tsv), the manifest 'output' cell is blanked and
    ' [output file no longer in data.done: not an image]' appended to 'status'.
  * header type differs from the extension -> renamed to the sniffed extension (clash -> stop), every <img src>
    in the root's pages and every 'output' cell of the root's CSVs that names it are rewritten.
Dry run lists the actions. Pages whose last picture was a fake are listed (they should become txt; done by hand).
"""
import csv, html, os, re, shutil, sys

base = sys.argv[1]
go = '--go' in sys.argv
Q = sys.argv[sys.argv.index('--quarantine') + 1] if '--quarantine' in sys.argv else None
if go and (not Q or os.path.exists(Q)):
    sys.exit('--go needs a new --quarantine dir')


def sniff(p):
    h = open(p, 'rb').read(8)
    return ('.jpg' if h[:3] == b'\xff\xd8\xff' else '.png' if h[:4] == b'\x89PNG' else
            '.gif' if h[:4] == b'GIF8' else '.bmp' if h[:2] == b'BM' else '')


for root in sorted(os.listdir(base)):
    R = os.path.join(base, root)
    if not os.path.isdir(R):
        continue
    acts = []  # (kind, old abs, new abs or None)
    for sub in ('images', 'images.only'):
        for d, _, fs in os.walk(os.path.join(R, sub)):
            for f in fs:
                if f == '.DS_Store':
                    continue
                p = os.path.join(d, f)
                k, e = sniff(p), os.path.splitext(f)[1].lower()
                if not k:
                    acts.append(('fake', p, None))
                elif k != e and not (k == '.jpg' and e == '.jpeg'):
                    n = os.path.splitext(p)[0] + k
                    if os.path.exists(n) or any(a[2] and a[2].lower() == n.lower() for a in acts):
                        sys.exit(f'clash: {n}')
                    acts.append(('ext', p, n))
    if not acts:
        continue
    amap = {a[1]: a for a in acts}
    pages = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(R, 'reports')) for f in fs if f.endswith('.html')]
    emptied = []
    for pg in pages:
        s = open(pg, encoding='utf-8').read()
        def rep(m):
            src = html.unescape(m.group(1))
            a = amap.get(os.path.normpath(os.path.join(os.path.dirname(pg), src)))
            if not a:
                return m.group(0)
            if a[0] == 'fake':
                return '<br>[image missing]<br>'
            return '<img src="%s">' % html.escape(os.path.relpath(a[2], os.path.dirname(pg)), quote=True)
        t = re.sub(r'<img src="([^"]*)">', rep, s)
        if t != s:
            left = len(re.findall(r'<img src=', t))
            print(f'  page {os.path.relpath(pg, base)}: {len(re.findall("<img src=", s))} -> {left} pictures')
            if left == 0:
                emptied.append(pg)
            if go:
                open(pg, 'w', encoding='utf-8').write(t)
    for c in [os.path.join(R, f) for f in os.listdir(R) if f.endswith('.csv')]:
        raw = open(c, 'rb').read()
        bom = raw.startswith(b'\xef\xbb\xbf')
        eol = '\r\n' if b'\r\n' in raw else '\n'
        rows = list(csv.reader(open(c, encoding='utf-8-sig', newline='')))
        hd = rows[0]
        if 'output' not in hd:
            continue
        oi, si = hd.index('output'), (hd.index('status') if 'status' in hd else None)
        ch = 0
        for r in rows[1:]:
            if not r[oi]:
                continue
            a = amap.get(os.path.normpath(os.path.join(R, r[oi])))
            if not a:
                continue
            ch += 1
            if a[0] == 'fake':
                r[oi] = ''
                if si is not None:
                    r[si] += ' [output file no longer in data.done: not an image]'
            else:
                r[oi] = os.path.relpath(a[2], R)
        print(f'  csv {os.path.basename(c)}: {ch} cells')
        if go and ch:
            with open(c, 'w', encoding='utf-8-sig' if bom else 'utf-8', newline='') as fh:
                csv.writer(fh, lineterminator=eol).writerows(rows)
    for k, p, n in acts:
        print(f'{root}: {k} {os.path.relpath(p, base)}' + (f' -> {os.path.basename(n)}' if n else ''))
        if go:
            if k == 'fake':
                dst = os.path.join(Q, os.path.relpath(p, base))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(p, dst)
                with open(os.path.join(Q, 'not_images.tsv'), 'a', encoding='utf-8') as fh:
                    fh.write(f'{os.path.relpath(p, base)}\t{os.path.getsize(dst)} bytes\n')
            else:
                os.rename(p, n)
    for pg in emptied:
        print(f'  NO PICTURE LEFT (-> txt by hand): {os.path.relpath(pg, base)}')
print('GO done' if go else 'dry run')
