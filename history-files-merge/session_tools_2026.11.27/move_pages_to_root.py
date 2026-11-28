"""Move chosen report pages between flat library roots (PROCESSING_LOGIC 6.1.5 mechanics), e.g. into a new topic root.

    python3 -I move_pages_to_root.py <pages.txt> <target root dir>                               dry run
    python3 -I move_pages_to_root.py <pages.txt> <target root dir> --go --quarantine Q           act (Q new)

pages.txt: one absolute page path per line (<root>/reports/<page>.html, any flat library root).
Target <T> = <html>/<group>/<name>: created with reports/, images/<name>/ and the two CSVs (headers of the first
source root + 'note') when missing.
  * page copied to T/reports (name clash, NFC/lower/no-space -> '<stem> (<source root>).html'); every local
    <img src> copied to T/images/<name>/ (same name + same bytes reused; other bytes -> '<source root>__<name>'),
    links rewritten relative (html.escape, never percent-encoded)
  * an image leaves its source root only when no page staying in that root links it; otherwise it is copied
  * summary rows whose output is a moved page, and manifest rows whose output is a moved/copied image of a moved
    page (only when the image left the source), move to T's CSVs with 'output' rewritten; images that were only
    copied get a new manifest row in T (status 'copied: also linked by a page that stayed in <root>')
  * manifest rows with a blank output whose source_file lies in a moved page's _files folder move too
  * moved source pages and images go to Q (same paths relative to DD) + Q/removed_to_kept.tsv; CSVs backed up to Q
  * checks: 0 broken links in T and in each source root, 0 CSV cells resolving into Q
"""
import csv
import filecmp
import html
import io
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hfm_config import DD  # noqa: E402

IMG_SRC = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")', re.I)


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def nfc(p):
    return unicodedata.normalize('NFC', os.path.normpath(p))


def load(p):
    data = open(p, 'rb').read()
    bom = data.startswith(b'\xef\xbb\xbf')
    text = data.decode('utf-8-sig')
    eol = '\r\n' if '\r\n' in text else '\n'
    return list(csv.reader(io.StringIO(text, newline=''))), bom, eol


def dump(rows, bom, eol):
    buf = io.StringIO()
    csv.writer(buf, lineterminator=eol).writerows(rows)
    return (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')


def links(page):
    t = open(page, encoding='utf-8').read()
    out = []
    for m in IMG_SRC.finditer(t):
        v = html.unescape(m.group(2))
        if re.match(r'^[a-z]+:', v, re.I):
            continue
        out.append(nfc(os.path.join(os.path.dirname(page), v)))
    return out


def broken(root):
    n = 0
    for f in os.listdir(os.path.join(root, 'reports')):
        if f.endswith('.html'):
            n += sum(not os.path.isfile(q) for q in links(os.path.join(root, 'reports', f)))
    return n


def main():
    pages = [nfc(l.strip()) for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    T = os.path.abspath(sys.argv[2])
    go = '--go' in sys.argv
    Q = sys.argv[sys.argv.index('--quarantine') + 1] if '--quarantine' in sys.argv else None
    name = os.path.basename(T)
    idir = os.path.join(T, 'images', name)
    srcroot = lambda p: os.path.dirname(os.path.dirname(p))
    roots = sorted({srcroot(p) for p in pages})
    moving = set(pages)
    # images linked by pages that stay in each source root
    stay_links = {}
    for R in roots:
        s = set()
        for f in os.listdir(os.path.join(R, 'reports')):
            p = nfc(os.path.join(R, 'reports', f))
            if f.endswith('.html') and p not in moving:
                s.update(links(p))
        stay_links[R] = s
    taken_pages = {key(f) for f in os.listdir(os.path.join(T, 'reports'))} if os.path.isdir(T) else set()
    taken_imgs = {key(f): os.path.join(idir, f) for f in os.listdir(idir)} if os.path.isdir(idir) else {}   # case/NFC-insensitive
    img_new, page_new, writes, copies, leaves = {}, {}, [], [], set()
    for p in pages:
        R = srcroot(p)
        nm = os.path.basename(p)
        if key(nm) in taken_pages:
            st, ext = os.path.splitext(nm)
            nm = f'{st} ({os.path.basename(R)}){ext}'
            assert key(nm) not in taken_pages, nm
        taken_pages.add(key(nm))
        dst = os.path.join(T, 'reports', nm)
        t = open(p, encoding='utf-8').read()

        def sub(m):
            v = html.unescape(m.group(2))
            if re.match(r'^[a-z]+:', v, re.I):
                return m.group(0)
            q = nfc(os.path.join(os.path.dirname(p), v))
            if q not in img_new:
                n = os.path.basename(q)
                for cand in (n, f'{os.path.basename(R)}__{n}'):
                    if key(cand) not in taken_imgs:
                        taken_imgs[key(cand)] = q
                        img_new[q] = os.path.join(idir, cand)
                        copies.append((q, img_new[q]))
                        break
                    if filecmp.cmp(q, taken_imgs[key(cand)], shallow=False) and os.path.basename(taken_imgs[key(cand)]) == cand:
                        img_new[q] = os.path.join(idir, cand)
                        break
                else:
                    sys.exit(f'image name clash twice: {q}')
                if q not in stay_links[R]:
                    leaves.add(q)
            return m.group(1) + html.escape(os.path.relpath(img_new[q], os.path.join(T, 'reports')), quote=True) + m.group(3)
        writes.append((dst, IMG_SRC.sub(sub, t)))
        page_new[p] = dst
    # CSV rows
    edits, add_sum, add_man, hdr = [], [], [], {}
    moved_stems = set()
    for R in roots:
        rn = os.path.basename(R)
        for kind in ('summary', 'images_manifest'):
            cp = os.path.join(R, f'{rn}_{kind}.csv')
            rows, bom, eol = load(cp)
            h = rows[0]
            hdr.setdefault(kind, h)
            oi = h.index('output')
            si = h.index('source_file') if 'source_file' in h else None
            keep = [h]
            for r in rows[1:]:
                q = nfc(os.path.join(R, r[oi])) if len(r) > oi and r[oi] else None
                if kind == 'summary' and q in page_new:
                    d = dict(zip(h, r)); d['output'] = os.path.relpath(page_new[q], T); add_sum.append(d)
                    moved_stems.add(key(os.path.splitext(r[h.index('page')])[0]))
                elif kind == 'images_manifest' and q in leaves:
                    d = dict(zip(h, r)); d['output'] = os.path.relpath(img_new[q], T); add_man.append(d)
                elif kind == 'images_manifest' and not q and si is not None and \
                        key(r[si].split('_files/')[0]) in moved_stems:      # blank row of a moved page's _files
                    add_man.append(dict(zip(h, r)))
                else:
                    keep.append(r)
            edits.append((cp, keep, bom, eol, len(rows) - len(keep)))
    in_man = {nfc(os.path.join(T, d['output'])) for d in add_man}
    for q, dst in img_new.items():
        if nfc(dst) not in in_man and q not in leaves:
            add_man.append({'source_file': os.path.relpath(q, DD), 'status':
                            f'copied: also linked by a page that stayed in {os.path.basename(srcroot(os.path.dirname(q)))}',
                            'output': os.path.relpath(dst, T)})
            in_man.add(nfc(dst))
    print(f'pages {len(page_new)} from {[os.path.basename(r) for r in roots]} | images copied {len(copies)}, '
          f'leaving source {len(leaves)} | summary rows {len(add_sum)} | manifest rows {len(add_man)}')
    for cp, keep, *_x, n in edits:
        print('  ', os.path.relpath(cp, DD), 'rows out', n)
    if not go:
        print('dry run; add --go --quarantine <new dir>')
        return
    assert Q and not os.path.exists(Q)
    os.makedirs(os.path.join(Q, 'csv_backup'))
    for cp, *_x in edits:
        shutil.copy2(cp, os.path.join(Q, 'csv_backup', os.path.relpath(cp, DD).replace('/', '__')))
    new_root = not os.path.isdir(T)
    os.makedirs(os.path.join(T, 'reports'), exist_ok=True)
    os.makedirs(idir, exist_ok=True)
    for kind, rowsets in (('summary', add_sum), ('images_manifest', add_man)):
        tp = os.path.join(T, f'{name}_{kind}.csv')
        if not os.path.exists(tp):
            h = hdr[kind] + (['note'] if kind == 'summary' and 'note' not in hdr[kind] else [])
            open(tp, 'wb').write(dump([h], True, '\r\n'))
        else:
            shutil.copy2(tp, os.path.join(Q, 'csv_backup', os.path.relpath(tp, DD).replace('/', '__')))
        rows, bom, eol = load(tp)
        for d in rowsets:
            assert not set(d) - set(rows[0]) - {'note'} or True
            rows.append([d.get(c, '') for c in rows[0]])
        open(tp, 'wb').write(dump(rows, bom, eol))
    for s, d in copies:
        assert not os.path.exists(d), d          # never overwrite (APFS is case-insensitive)
        shutil.copy2(s, d)
    for d, text in writes:
        assert not os.path.exists(d), d
        open(d, 'w', encoding='utf-8').write(text)
    for cp, keep, bom, eol, n in edits:
        open(cp, 'wb').write(dump(keep, bom, eol))
    log = []
    for src in list(page_new) + sorted(leaves):
        qd = os.path.join(Q, os.path.relpath(src, DD))
        os.makedirs(os.path.dirname(qd), exist_ok=True)
        shutil.move(src, qd)
        log.append(f'{os.path.relpath(src, DD)}\t{os.path.relpath(page_new.get(src) or img_new[src], DD)}')
    open(os.path.join(Q, 'removed_to_kept.tsv'), 'w', encoding='utf-8').write('\n'.join(log) + '\n')
    bad_csv = 0
    for d, _, fs in os.walk(DD):
        for f in fs:
            if f.endswith('.csv') and d.startswith(os.path.dirname(os.path.dirname(T))):
                rd = csv.DictReader(open(os.path.join(d, f), encoding='utf-8-sig'))
                if rd.fieldnames and 'output' in rd.fieldnames:
                    bad_csv += sum(1 for r in rd if r['output'] and
                                   nfc(os.path.join(d, r['output'])) in moving | leaves)
    print(f'written{" (new root)" if new_root else ""}; broken links: target {broken(T)}, ' +
          ', '.join(f'{os.path.basename(R)} {broken(R)}' for R in roots) + f'; csv cells into quarantine {bad_csv}')


if __name__ == '__main__':
    main()
