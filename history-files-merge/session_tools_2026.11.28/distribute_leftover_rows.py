"""Empty a staging root's CSVs into the library roots once all its pages are gone (PROCESSING_LOGIC 7: never delete rows).

    python3 distribute_leftover_rows.py <html dir> <unrouted root> <staging root> [<staging root> ...]            dry run
    python3 distribute_leftover_rows.py <html dir> <unrouted root> <staging root> ... --go --backup-dir D         act

<html dir> = DD/mc_2026.11.19/html; roots are paths relative to it (e.g. mcjt-total, 2010_mc).
A library root = folder holding <name>_summary.csv. Per staging root R (no pages left in R/reports):
  summary row with output  -> the root whose folder contains the output (page in another root after a de-dup)
  summary row blank        -> <unrouted root>
  manifest row with output -> the root whose folder contains the output image
  manifest row blank       -> the root its page's summary row went to (source_file stem before '_files/' == page stem),
                              else <unrouted root>
'output' is rewritten relative to the target CSV; rows padded to the target header (source columns must exist there,
'note' is added to a summary header when missing). Target CSVs keep BOM/EOL. --go backs up every target CSV and moves
the emptied staging root (CSVs + empty folders) into D; checks 0 unresolved outputs among the moved rows."""
import csv
import io
import os
import re
import shutil
import sys
import unicodedata


def nfc(p):
    return unicodedata.normalize('NFC', os.path.normpath(p))


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def load(p):
    data = open(p, 'rb').read()
    text = data.decode('utf-8-sig')
    return data.startswith(b'\xef\xbb\xbf'), ('\r\n' if '\r\n' in text else '\n'), \
        list(csv.reader(io.StringIO(text, newline='')))


def dump(p, bom, eol, rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator=eol).writerows(rows)
    open(p, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8'))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    go = '--go' in sys.argv
    bdir = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
    if bdir:
        args.remove(bdir)
    H, unrouted, staging = nfc(os.path.abspath(args[0])), args[1], args[2:]
    roots = {}
    for d, _, fs in os.walk(H):
        n = os.path.basename(d)
        if f'{n}_summary.csv' in fs:
            roots[nfc(d)] = n
    stag = {nfc(os.path.join(H, s)) for s in staging}

    def root_of(q):
        best = None
        for r in roots:
            if (q.startswith(r + os.sep)) and r not in stag and (best is None or len(r) > len(best)):
                best = r
        if best is None:            # layout-B set outside <html dir>: <base>/<set>/… with <base>/<set>_summary.csv
            d = os.path.dirname(q)
            while d != os.path.dirname(d):
                if os.path.isfile(os.path.join(os.path.dirname(d), os.path.basename(d) + '_summary.csv')):
                    best = d
                    csvdir[d] = os.path.dirname(d)
                    roots[d] = os.path.basename(d)
                    break
                d = os.path.dirname(d)
        return best
    csvdir = {}                     # root -> folder holding its CSVs (layout B: the parent)
    U = nfc(os.path.join(H, unrouted))
    assert U in roots, U
    add = {}                        # (target root, kind) -> list of dict rows
    hdrs = {}
    for s in staging:
        R = nfc(os.path.join(H, s))
        n = roots[R]
        left = [f for f in os.listdir(os.path.join(R, 'reports')) if f.lower().endswith('.html')]
        assert not left, f'{s} still has pages: {left[:3]}'
        stem_target = {}
        for kind in ('summary', 'images_manifest'):
            _, _, rows = load(os.path.join(R, f'{n}_{kind}.csv'))
            h = rows[0]
            hdrs[(R, kind)] = h
            for r in rows[1:]:
                d = dict(zip(h, r + [''] * (len(h) - len(r))))
                if d['output']:
                    q = nfc(os.path.join(R, d['output']))
                    T = root_of(q)
                    assert T and os.path.exists(q), (s, d['output'])
                    d['output'] = q            # absolute for now
                else:
                    T = U
                    if kind == 'images_manifest' and '_files/' in d.get('source_file', ''):
                        T = stem_target.get(key(d['source_file'].split('_files/')[0]), U)
                if kind == 'summary':
                    stem_target[key(os.path.splitext(d['page'])[0])] = T
                add.setdefault((T, kind), []).append(d)
    for (T, kind), ds in sorted(add.items()):
        print(f'  {os.path.relpath(T, H)[-40:]:40} {kind:16} rows {len(ds):5} (blank output {sum(not d["output"] for d in ds)})')
    print('rows total', sum(len(v) for v in add.values()))
    if not go:
        print('dry run; add --go --backup-dir <new dir>')
        return
    assert bdir and not os.path.exists(bdir)
    os.makedirs(os.path.join(bdir, 'target_csv'))
    bad = 0
    for (T, kind), ds in sorted(add.items()):
        C = csvdir.get(T, T)
        tp = os.path.join(C, f'{roots[T]}_{kind}.csv')
        shutil.copy2(tp, os.path.join(bdir, 'target_csv', os.path.relpath(tp, os.path.dirname(H)).replace('/', '__')))
        bom, eol, rows = load(tp)
        h = rows[0]
        if kind == 'summary' and 'note' not in h:
            h.append('note')
            for r in rows[1:]:
                r.append('')
        for d in ds:
            extra = {c for c, v in d.items() if v and c not in h}
            assert not extra, (tp, extra)
            if d['output']:
                d['output'] = os.path.relpath(d['output'], C)
                bad += not os.path.exists(os.path.join(C, d['output']))
            rows.append([d.get(c, '') for c in h])
        dump(tp, bom, eol, rows)
    for s in staging:
        shutil.move(os.path.join(H, s), os.path.join(bdir, 'staging_' + s))
    print(f'written; staging roots moved to {bdir}; unresolved outputs among moved rows {bad}')


if __name__ == '__main__':
    main()
