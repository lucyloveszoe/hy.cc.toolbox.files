"""Give pictures whose bytes are another format the right extension (PROCESSING_LOGIC 4.1 'ext_fix'); dry run by default.

    python3 -I fix_image_ext.py [DD] [--go --backup-dir D]

Every file under DD with an image extension is header-sniffed (jpg / png / gif / bmp). A mismatch (PNG data in a .jpg)
is renamed to <stem>.<real ext>; a name already taken (NFC + lower case, APFS is case-insensitive) gets '_<n>'.
Repointed in the same run: every html <img src> / <a href> under DD that resolves to the file (written html.escape'd,
never percent-encoded), every CSV 'output' cell that resolves to it, and 'file' cells of images_merged-style manifests.
Rewritten pages / CSVs are backed up first; afterwards 0 old paths and 0 references to them must remain."""
import csv
import html
import io
import os
import re
import shutil
import sys
import unicodedata

args = [a for a in sys.argv[1:] if not a.startswith('--')]
GO = '--go' in sys.argv
B = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
if B in args:
    args.remove(B)
DD = args[0] if args else os.path.expanduser('~/Downloads/data.done')
nfc = lambda p: unicodedata.normalize('NFC', os.path.normpath(p))
key = lambda s: re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())
EXT = {'.jpg': 'jpg', '.jpeg': 'jpg', '.png': 'png', '.gif': 'gif', '.bmp': 'bmp'}
REF = re.compile(r'(<(?:img|a)\b[^>]*?\s(?:src|href)=")([^"]+)(")', re.I)


def sniff(p):
    b = open(p, 'rb').read(8)
    return ('jpg' if b[:3] == b'\xff\xd8\xff' else 'png' if b[:4] == b'\x89PNG' else 'gif' if b[:4] == b'GIF8'
            else 'bmp' if b[:2] == b'BM' else None)


ren = {}
for d, _, fs in os.walk(DD):
    taken = {key(f) for f in fs}
    for f in sorted(fs):
        st, ext = os.path.splitext(f)
        if ext.lower() not in EXT:
            continue
        real = sniff(os.path.join(d, f))
        if real is None or real == EXT[ext.lower()]:
            continue
        nm, i = f'{st}.{real}', 1
        while key(nm) in taken:
            nm, i = f'{st}_{i}.{real}', i + 1
        taken.add(key(nm))
        ren[nfc(os.path.join(d, f))] = os.path.join(d, nm)
print('files to rename', len(ren))
for o, n in ren.items():
    print('  ', os.path.relpath(o, DD)[:80], '->', os.path.basename(n))
edits = []
for d, _, fs in os.walk(DD):
    for f in fs:
        p = os.path.join(d, f)
        if f.lower().endswith(('.html', '.htm')):
            t = open(p, encoding='utf-8', errors='surrogateescape').read()
            n = [0]

            def sub(m):
                v = html.unescape(m.group(2))
                if re.match(r'^[a-z]+:', v, re.I):
                    return m.group(0)
                q = nfc(os.path.join(d, v))
                if q in ren:
                    n[0] += 1
                    return m.group(1) + html.escape(os.path.relpath(ren[q], d), quote=True) + m.group(3)
                return m.group(0)
            t2 = REF.sub(sub, t)
            if n[0]:
                edits.append((p, t2.encode('utf-8', errors='surrogateescape'), n[0]))
        elif f.endswith('.csv'):
            data = open(p, 'rb').read()
            bom = data.startswith(b'\xef\xbb\xbf')
            text = data.decode('utf-8-sig')
            eol = '\r\n' if '\r\n' in text else '\n'
            rows = list(csv.reader(io.StringIO(text, newline='')))
            if not rows:
                continue
            h = rows[0]
            cols = [(h.index('output'), d)] if 'output' in h else []
            if 'file' in h and 'sha256' in h:
                base = next((os.path.join(d, x) for x in ('images-only', 'images') if os.path.isdir(os.path.join(d, x))), d)
                cols.append((h.index('file'), base))
            n = 0
            for r in rows[1:]:
                for ci, base in cols:
                    if ci < len(r) and r[ci]:
                        q = nfc(os.path.join(base, r[ci]))
                        if q in ren:
                            r[ci] = os.path.relpath(ren[q], base)
                            n += 1
            if n:
                buf = io.StringIO()
                csv.writer(buf, lineterminator=eol).writerows(rows)
                edits.append((p, (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8'), n))
print('files to rewrite', len(edits), '| references', sum(e[2] for e in edits))
for p, _, n in edits:
    print('  ', n, os.path.relpath(p, DD)[:90])
if not GO:
    print('dry run; add --go --backup-dir <new dir>')
    sys.exit()
assert B and not os.path.exists(B)
os.makedirs(B)
for p, _, _ in edits:
    dst = os.path.join(B, os.path.relpath(p, DD))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(p, dst)
for o, n in ren.items():
    assert not os.path.exists(n), n
    os.rename(o, n)
for p, data, _ in edits:
    open(p, 'wb').write(data)
left = sum(os.path.exists(o) and not os.path.exists(n) for o, n in ren.items())
print('renamed', len(ren), '| files rewritten', len(edits), '| old paths left', left)
