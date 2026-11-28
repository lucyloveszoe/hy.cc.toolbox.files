"""Put the unreferenced photos of new layout-A roots into the flat images folder and repoint their manifest rows.

    python3 imgonly_into_flat.py <plan.json> <flat dir> <flat manifest.csv> [--go]

plan.json: list of {path, root, sha, bytes, w, h, kind} for every file in <root>/images.only (kind: new | dup-in-batch |
ui | in-library | in-new-report). Rules (PROCESSING_LOGIC 4.3, 5.2):
  new, not an ad banner (aspect >= 5:1)  -> copied to <flat dir>/<page title>_<original name> (board footer, 'x_' and
                                            leading 【新提醒】 dropped; clash -> '<root>__' prefix) + manifest row
  dup-in-batch / in-library / in-new-report -> the row points to the existing copy (same SHA-256)
  ui (<= 150 px or < 8 KB) / ad banner / fake -> blank output + ' [output file no longer in data.done: …]'
  in-library / in-new-report (plan key 'existing') -> the row points to that file
  loose image (source_file without '_files/') -> '<parent folder or root>__<name>'
Every <root>/<root>_images_manifest.csv row whose output is in images.only is rewritten (relative to its CSV).
"""
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import unicodedata

FOOTER = re.compile(r'\s*-\s*◎『.*$')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strip_name_footers import peel  # noqa: E402  board footers / heads (2026-11-28)


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def load_csv(p):
    data = open(p, 'rb').read()
    bom = data.startswith(b'\xef\xbb\xbf')
    text = data.decode('utf-8-sig')
    eol = '\r\n' if '\r\n' in text else '\n'
    rows = list(csv.reader(io.StringIO(text, newline='')))

    def dump(rs):
        buf = io.StringIO()
        csv.writer(buf, lineterminator=eol).writerows(rs)
        return (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')
    return rows, dump


def main():
    plan_p, flat, flat_man = sys.argv[1:4]
    go = '--go' in sys.argv
    plan = json.load(open(plan_p, encoding='utf-8'))
    by_path = {os.path.normpath(x['path']): x for x in plan}
    taken = {key(f) for f in os.listdir(flat)}
    roots = sorted({os.path.dirname(os.path.dirname(os.path.dirname(x['path']))) for x in plan})
    new_files = {}            # sha -> flat path
    man_rows = []
    edits = []
    stats = {}
    for root in roots:
        name = os.path.basename(root)
        mp = os.path.join(root, f'{name}_images_manifest.csv')
        rows, dump = load_csv(mp)
        h = rows[0]
        si, oi, st = h.index('source_file'), h.index('output'), h.index('status')
        for r in rows[1:]:
            if len(r) <= oi or not r[oi].startswith('images.only/'):
                continue
            p = os.path.normpath(os.path.join(root, r[oi]))
            x = by_path.get(p)
            if x is None:
                sys.exit(f'not in plan: {p}')
            kind = x['kind']
            if kind in ('new', 'dup-in-batch') and x['w'] >= 5 * x['h']:   # also batch repeats (fix 2026-11-28)
                kind = 'ad'
            stats[kind] = stats.get(kind, 0) + 1
            if kind in ('ui', 'ad', 'fake'):
                r[oi] = ''
                why = {'ui': 'forum UI image (<=150 px or <8 KB), not kept', 'ad': 'ad banner, not kept',
                       'fake': 'not an image (fake file), not kept'}[kind]
                r[st] += f' [output file no longer in data.done: {why}]'
                continue
            if kind == 'dup-in-batch':
                kind = 'new'          # same picture as another new file; whichever row comes first creates it
            if kind in ('in-library', 'in-new-report'):
                r[oi] = os.path.relpath(x['existing'], root)
                continue
            if kind == 'new' and x['sha'] not in new_files:
                page, sep, orig = r[si].partition('_files/')
                if sep:
                    title = peel(FOOTER.sub('', os.path.basename(page)).strip())
                    while title.startswith('【新提醒】'):
                        title = peel(title[len('【新提醒】'):].lstrip())
                    nm = f'{title}_{os.path.basename(orig)}'
                else:            # loose image of the zip (no page): '<parent folder or root>__<name>'
                    par = os.path.basename(os.path.dirname(r[si])) or name
                    nm = f'{par}__{os.path.basename(r[si])}'
                if key(nm) in taken:
                    nm = f'{name}__{nm}'
                assert key(nm) not in taken and len(nm.encode()) < 240, nm
                taken.add(key(nm))
                new_files[x['sha']] = os.path.join(flat, nm)
                man_rows.append([nm, x['sha'], str(x['bytes']), '1', f'{name}/{r[si]}'])
                if go:
                    shutil.copy2(p, new_files[x['sha']])
            elif kind == 'new':
                for m in man_rows:
                    if m[1] == x['sha']:
                        m[3] = str(int(m[3]) + 1)
                        m[4] += f' | {name}/{r[si]}'
            else:
                sys.exit(f'kind {kind} needs a library path lookup (not expected here): {p}')
            target = new_files[x['sha']]
            r[oi] = os.path.relpath(target, root)
        edits.append((mp, dump(rows)))
    print('rows by kind', stats, '| new flat files', len(new_files))
    for m in man_rows:
        print('  ', m[0][:80], m[2], 'copies', m[3])
    if not go:
        print('dry run; add --go')
        return
    if not os.path.exists(flat_man):     # new flat folder: start the manifest (images_merged format, BOM + LF)
        open(flat_man, 'wb').write(b'\xef\xbb\xbfno,file,sha256,bytes,copies_merged,original_paths\n')
    rows, dump = load_csv(flat_man)
    last = int(rows[-1][0]) if len(rows) > 1 else 0
    for i, m in enumerate(man_rows, 1):
        rows.append([str(last + i)] + m)
    open(flat_man, 'wb').write(dump(rows))
    for mp, data in edits:
        open(mp, 'wb').write(data)
    bad = [p for s, p in new_files.items() if hashlib.sha256(open(p, 'rb').read()).hexdigest() != s]
    print('copied', len(new_files), 'sha mismatches', len(bad), '| manifest rows appended', len(man_rows))


if __name__ == '__main__':
    main()
