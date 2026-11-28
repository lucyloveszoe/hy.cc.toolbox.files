"""Turn flat layout-B sets (<base>/<set>/*.html, <base>/<set>/images/<set>/*, <base>/<set>_summary.csv,
<base>/<set>_images_manifest.csv) into flat library roots (<H>/<prefix><set>/reports/*.html,
<H>/<prefix><set>/images/<prefix><set>/*, <H>/<prefix><set>/<prefix><set>_summary.csv / _images_manifest.csv),
fixing every relative path that crosses a moved file (PROCESSING_LOGIC 6.1.7 / 7).

    python3 restage_flat_set.py <base> <H> <prefix> <set> [<set> ...]                      dry run
    python3 restage_flat_set.py <base> <H> <prefix> <set> [<set> ...] --go --backup-dir D   act (D new)

Scans every CSV ('output' cells) and every html page (img/a src|href) under DD. A reference is rewritten when its
holder or its target is a moved file: resolved against the old layout, target mapped, written relative to the
holder's new folder (html: html.escape, never percent-encoded). References that did not resolve before are left and
counted. Any file of a set folder outside the two expected kinds stops the run. --go backs up every rewritten
file (old relative path under D), moves the files (os.rename, assert target absent), writes, removes the emptied
set folders, then re-checks: 0 broken links in the new roots, 0 CSV cells under DD that do not resolve (vs before)."""
import csv
import html
import io
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hfm_config import DD  # noqa: E402

REF = re.compile(r'(<(?:img|a)\b[^>]*?\s(?:src|href)=")([^"]+)(")', re.I)


def nfc(p):
    return unicodedata.normalize('NFC', os.path.normpath(p))


def key(p):
    return re.sub(r'\s+', '', nfc(p).lower())


def csv_rows(p):
    data = open(p, 'rb').read()
    text = data.decode('utf-8-sig')
    return data.startswith(b'\xef\xbb\xbf'), ('\r\n' if '\r\n' in text else '\n'), \
        list(csv.reader(io.StringIO(text, newline='')))


def missing_cells():
    n = 0
    for d, _, fs in os.walk(DD):
        for f in fs:
            if f.endswith('.csv'):
                _, _, rows = csv_rows(os.path.join(d, f))
                if rows and 'output' in rows[0]:
                    oi = rows[0].index('output')
                    n += sum(1 for r in rows[1:] if len(r) > oi and r[oi] and not os.path.exists(os.path.join(d, r[oi])))
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    go = '--go' in sys.argv
    bdir = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
    if bdir:
        args.remove(bdir)
    base, H, prefix, sets = nfc(os.path.abspath(args[0])), nfc(os.path.abspath(args[1])), args[2], args[3:]
    M = {}
    for s in sets:
        R = os.path.join(H, prefix + s)
        assert not os.path.exists(R), R
        sd, idir = os.path.join(base, s), os.path.join(base, s, 'images', s)
        for d, ds, fs in os.walk(sd):
            for f in fs:
                p = nfc(os.path.join(d, f))
                if f == '.DS_Store':
                    continue
                if os.path.dirname(p) == nfc(sd) and f.lower().endswith('.html'):
                    M[p] = os.path.join(R, 'reports', f)
                elif os.path.dirname(p) == nfc(idir):
                    M[p] = os.path.join(R, 'images', prefix + s, f)
                else:
                    sys.exit(f'unexpected file in set folder: {p}')
        for k in ('summary', 'images_manifest'):
            M[nfc(os.path.join(base, f'{s}_{k}.csv'))] = os.path.join(R, f'{prefix}{s}_{k}.csv')
    tk = {}
    for v in M.values():
        assert key(v) not in tk, v
        tk[key(v)] = v
    remap = lambda p: M.get(p, p)
    edits, stats = [], {'csv cells': 0, 'html refs': 0, 'unresolved before (left)': 0}
    for d, _, fs in os.walk(DD):
        for f in fs:
            p = nfc(os.path.join(d, f))
            dn_old, dn_new = os.path.dirname(p), os.path.dirname(remap(p))
            if f.endswith('.csv'):
                bom, eol, rows = csv_rows(p)
                if not rows or 'output' not in rows[0]:
                    continue
                oi = rows[0].index('output')
                n = 0
                for r in rows[1:]:
                    if len(r) <= oi or not r[oi]:
                        continue
                    q = nfc(os.path.join(dn_old, r[oi]))
                    if not (p in M or q in M):
                        continue
                    if not os.path.exists(q):
                        stats['unresolved before (left)'] += 1
                        continue
                    nv = os.path.relpath(remap(q), dn_new)
                    if nv != r[oi]:
                        r[oi] = nv
                        n += 1
                if n or p in M:
                    buf = io.StringIO()
                    csv.writer(buf, lineterminator=eol).writerows(rows)
                    edits.append((p, (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')))
                    stats['csv cells'] += n
            elif f.lower().endswith(('.html', '.htm')):
                t = open(p, encoding='utf-8', errors='surrogateescape').read()
                cnt = [0]

                def sub(m):
                    v = html.unescape(m.group(2))
                    if re.match(r'^[a-z]+:|^#|^//', v, re.I):
                        return m.group(0)
                    q = nfc(os.path.join(dn_old, v.split('#')[0]))
                    if not (p in M or q in M):
                        return m.group(0)
                    if not os.path.exists(q):
                        stats['unresolved before (left)'] += 1
                        return m.group(0)
                    nv = os.path.relpath(remap(q), dn_new)
                    if nv == v:
                        return m.group(0)
                    cnt[0] += 1
                    return m.group(1) + html.escape(nv, quote=True) + m.group(3)
                t2 = REF.sub(sub, t)
                if cnt[0] or p in M:
                    edits.append((p, t2.encode('utf-8', errors='surrogateescape')))
                    stats['html refs'] += cnt[0]
    outside = [p for p, _ in edits if p not in M]
    print('files moved', len(M), '|', stats, '| files rewritten', len(edits), '(outside the sets', len(outside), ')')
    for p in outside[:20]:
        print('   outside:', os.path.relpath(p, DD))
    if not go:
        print('dry run; add --go --backup-dir <new dir>')
        return
    before = missing_cells()
    assert bdir and not os.path.exists(bdir)
    for p, _ in edits:
        dst = os.path.join(bdir, os.path.relpath(p, DD))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
    data = dict(edits)
    for old, new in M.items():
        assert not os.path.exists(new), new
        os.makedirs(os.path.dirname(new), exist_ok=True)
        os.rename(old, new)
    for p, d in data.items():
        open(remap(p), 'wb').write(d)
    for s in sets:
        sd = os.path.join(base, s)
        for d, ds, fs in sorted(os.walk(sd), key=lambda x: -len(x[0])):
            if fs == ['.DS_Store']:
                os.remove(os.path.join(d, '.DS_Store'))
            os.rmdir(d)
    broken = 0
    for s in sets:
        rd = os.path.join(H, prefix + s, 'reports')
        for f in os.listdir(rd):
            t = open(os.path.join(rd, f), encoding='utf-8', errors='replace').read()
            for _, v, _ in REF.findall(t):
                v = html.unescape(v)
                if not re.match(r'^[a-z]+:|^#|^//', v, re.I):
                    broken += not os.path.exists(os.path.join(rd, v.split('#')[0]))
    print(f'moved; rewritten {len(edits)}; backups in {bdir}; broken links in new roots {broken}; '
          f'missing CSV cells in DD before {before} after {missing_cells()}')


if __name__ == '__main__':
    main()
