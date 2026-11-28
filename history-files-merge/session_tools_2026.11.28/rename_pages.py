"""Rename report pages inside their folder and repoint every reference under DD (PROCESSING_LOGIC 7).

    python3 rename_pages.py <plan.tsv>                          dry run   (plan: old_path<TAB>new_name, no header)
    python3 rename_pages.py <plan.tsv> --go --backup-dir D      act (D new)

Clash check: the new name must not exist in the folder (NFC + lower case + no whitespace; APFS is case-insensitive).
References: CSV 'output' cells and html src/href under DD that resolve to an old path are rewritten relative to their
holder (html.escape, never percent-encoded). Rewritten files are backed up first. Checks: 0 old paths left, 0
references to old paths, missing CSV cells in DD unchanged."""
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


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def csv_rows(p):
    data = open(p, 'rb').read()
    text = data.decode('utf-8-sig')
    return data.startswith(b'\xef\xbb\xbf'), ('\r\n' if '\r\n' in text else '\n'), \
        list(csv.reader(io.StringIO(text, newline='')))


def scan(M, count_missing=False):
    edits, n_csv, n_html, missing = [], 0, 0, 0
    for d, _, fs in os.walk(DD):
        for f in fs:
            p = os.path.join(d, f)
            if f.endswith('.csv'):
                bom, eol, rows = csv_rows(p)
                if not rows or 'output' not in rows[0]:
                    continue
                oi, n = rows[0].index('output'), 0
                for r in rows[1:]:
                    if len(r) > oi and r[oi]:
                        q = nfc(os.path.join(d, r[oi]))
                        if q in M:
                            r[oi] = os.path.relpath(M[q], d)
                            n += 1
                        elif count_missing and not os.path.exists(q):
                            missing += 1
                if n:
                    buf = io.StringIO()
                    csv.writer(buf, lineterminator=eol).writerows(rows)
                    edits.append((p, (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')))
                    n_csv += n
            elif f.lower().endswith(('.html', '.htm')):
                t = open(p, encoding='utf-8', errors='surrogateescape').read()
                cnt = [0]

                def sub(m):
                    v = html.unescape(m.group(2))
                    if re.match(r'^[a-z]+:|^#|^//', v, re.I):
                        return m.group(0)
                    q = nfc(os.path.join(d, v.split('#')[0]))
                    if q not in M:
                        return m.group(0)
                    cnt[0] += 1
                    return m.group(1) + html.escape(os.path.relpath(M[q], d), quote=True) + m.group(3)
                t2 = REF.sub(sub, t)
                if cnt[0]:
                    edits.append((p, t2.encode('utf-8', errors='surrogateescape')))
                    n_html += cnt[0]
    return edits, n_csv, n_html, missing


def main():
    go = '--go' in sys.argv
    bdir = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
    M = {}
    for line in open(sys.argv[1], encoding='utf-8').read().splitlines():
        if not line.strip():
            continue
        old, new = line.split('\t')
        old = nfc(old)
        assert os.path.isfile(old), old
        d = os.path.dirname(old)
        others = {key(f) for f in os.listdir(d) if nfc(os.path.join(d, f)) != old} | {key(os.path.basename(v)) for v in M.values() if os.path.dirname(v) == d}
        if key(new) in others or '/' in new or len(new.encode()) > 240:
            print('  kept old name (clash / bad name):', os.path.relpath(old, DD), '->', new)
            continue
        M[old] = os.path.join(d, new)
    edits, n_csv, n_html, _ = scan(M)
    print(f'renames {len(M)} | csv cells {n_csv} | html refs {n_html} | files rewritten {len(edits)}')
    for o, n in M.items():
        print('  ', os.path.basename(o)[:70], '->', os.path.basename(n)[:70])
    if not go:
        print('dry run; add --go --backup-dir <new dir>')
        return
    _, _, _, before = scan({}, True)
    assert bdir and not os.path.exists(bdir)
    os.makedirs(bdir)
    for p, _ in edits:
        dst = os.path.join(bdir, os.path.relpath(p, DD))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
    with open(os.path.join(bdir, 'renamed_pages.tsv'), 'w', encoding='utf-8') as fh:
        fh.writelines(f'{os.path.relpath(o, DD)}\t{os.path.relpath(n, DD)}\n' for o, n in M.items())
    for p, data in edits:
        open(p, 'wb').write(data)
    for o, n in M.items():
        assert not os.path.exists(n), n
        os.rename(o, n)
    left = sum(os.path.exists(o) for o in M)
    e2, c2, h2, after = scan({o: o for o in M}, True)
    print(f'renamed; old paths left {left}; references to old paths {c2 + h2}; missing CSV cells before {before} after {after}')


if __name__ == '__main__':
    main()
