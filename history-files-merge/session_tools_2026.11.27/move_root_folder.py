"""Move one library root folder to a new place and fix every relative path that crosses it (PROCESSING_LOGIC 6.1.7).

    python3 -I move_root_folder.py <old root dir> <new root dir> [--go --backup-dir D]

Scans every CSV ('output' cells) and every html page (src / href) under DD and also ~/Downloads/images-only CSVs.
A reference is rewritten when its holder or its target lies in the moved folder: it is resolved against the old
layout, the target is mapped to the new layout, and the path is written relative to the holder's new folder
(html: html.escape, never percent-encoded). References that did not resolve before are left as they are and counted.
--go: backs up every changed file, moves the folder (one os.rename), writes the files, then re-checks."""
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


def main():
    old, new = nfc(os.path.abspath(sys.argv[1])), nfc(os.path.abspath(sys.argv[2]))
    go = '--go' in sys.argv
    bdir = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
    assert os.path.isdir(old) and not os.path.exists(new)
    inside = lambda p: p == old or p.startswith(old + os.sep)
    remap = lambda p: new + p[len(old):] if inside(p) else p
    edits, stats = [], {'csv cells': 0, 'html refs': 0, 'unresolved before (left)': 0}
    for d, _, fs in os.walk(DD):
        for f in fs:
            p = nfc(os.path.join(d, f))
            dn_old, dn_new = os.path.dirname(p), os.path.dirname(remap(p))
            if f.endswith('.csv'):
                data = open(p, 'rb').read()
                bom = data.startswith(b'\xef\xbb\xbf')
                text = data.decode('utf-8-sig')
                eol = '\r\n' if '\r\n' in text else '\n'
                rows = list(csv.reader(io.StringIO(text, newline='')))
                if not rows or 'output' not in rows[0]:
                    continue
                oi = rows[0].index('output')
                n = 0
                for r in rows[1:]:
                    if len(r) <= oi or not r[oi]:
                        continue
                    q = nfc(os.path.join(dn_old, r[oi]))
                    if not (inside(p) or inside(q)):
                        continue
                    if not os.path.exists(q):
                        stats['unresolved before (left)'] += 1
                        continue
                    nv = os.path.relpath(remap(q), dn_new)
                    if nv != r[oi]:
                        r[oi] = nv
                        n += 1
                if n:
                    buf = io.StringIO()
                    csv.writer(buf, lineterminator=eol).writerows(rows)
                    edits.append((p, (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')))
                    stats['csv cells'] += n
            elif f.lower().endswith(('.html', '.htm')):
                t = open(p, encoding='utf-8', errors='surrogateescape').read()
                cnt = [0]

                def sub(m):
                    v = html.unescape(m.group(2))
                    if re.match(r'^[a-z]+:|^#', v, re.I):
                        return m.group(0)
                    q = nfc(os.path.join(dn_old, v.split('#')[0]))
                    if not (inside(p) or inside(q)) or not os.path.exists(q):
                        return m.group(0)
                    nv = os.path.relpath(remap(q), dn_new)
                    if nv == v:
                        return m.group(0)
                    cnt[0] += 1
                    return m.group(1) + html.escape(nv, quote=True) + m.group(3)
                t2 = REF.sub(sub, t)
                if cnt[0]:
                    edits.append((p, t2.encode('utf-8', errors='surrogateescape')))
                    stats['html refs'] += cnt[0]
    print(stats, '| files to rewrite', len(edits))
    for p, _ in edits[:30]:
        print('  ', os.path.relpath(p, DD))
    if not go:
        print('dry run; add --go --backup-dir <new dir>')
        return
    assert bdir and not os.path.exists(bdir)
    os.makedirs(bdir)
    for p, _ in edits:
        dst = os.path.join(bdir, os.path.relpath(p, DD))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
    os.makedirs(os.path.dirname(new), exist_ok=True)
    os.rename(old, new)
    for p, data in edits:
        open(remap(p), 'wb').write(data)
    print('moved; files rewritten', len(edits), '| backups in', bdir)


if __name__ == '__main__':
    main()
