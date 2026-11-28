"""Move the contents of one folder into an existing folder (merge), optionally move extra files (e.g. the set's
CSVs) into another folder, and fix every relative path that crosses the moved files (PROCESSING_LOGIC 6.1.7).

    python3 merge_folder_into.py <src dir> <dst dir> [--file <path> <new dir>]... [--go --backup-dir D]

Merge rule: an entry of <src> that does not exist in <dst> is moved with one os.rename; a folder that exists on both
sides is merged recursively. Any name clash with a file (NFC + lower case + no whitespace, APFS is case-insensitive)
aborts before anything is moved. .DS_Store is skipped (left in <src>).
References: every CSV 'output' cell and every html src/href under DD (and CSVs under ~/Downloads/images-only) whose
holder or target is moved: resolved against the old layout, written relative to the holder's new folder (html:
html.escape, never percent-encoded). References that did not resolve before are left and counted.
--go: backs up every changed file, moves, writes the files, then re-checks that every rewritten reference resolves.
After the move <src> is removed when only .DS_Store / empty folders are left."""
import csv
import html
import io
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hfm_config import DD, DL  # noqa: E402

REF = re.compile(r'(<(?:img|a)\b[^>]*?\s(?:src|href)=")([^"]+)(")', re.I)
nfc = lambda p: unicodedata.normalize('NFC', os.path.normpath(p))
key = lambda s: ''.join(unicodedata.normalize('NFC', s).lower().split())


def parse(argv):
    a = list(argv)
    go = '--go' in a
    bdir = a[a.index('--backup-dir') + 1] if '--backup-dir' in a else None
    files = []
    while '--file' in a:
        i = a.index('--file')
        files.append((nfc(os.path.abspath(a[i + 1])), nfc(os.path.abspath(a[i + 2]))))
        del a[i:i + 3]
    pos = [x for i, x in enumerate(a) if not x.startswith('--') and (i == 0 or a[i - 1] != '--backup-dir')]
    return nfc(os.path.abspath(pos[0])), nfc(os.path.abspath(pos[1])), files, go, bdir


def plan_moves(src, dst):
    """List (old, new) renames; abort on any clash."""
    moves, clashes = [], []
    have = {key(x): x for x in os.listdir(dst)}
    for e in sorted(os.listdir(src)):
        if e == '.DS_Store':
            continue
        o, n = os.path.join(src, e), os.path.join(dst, e)
        if key(e) in have:
            t = os.path.join(dst, have[key(e)])
            if os.path.isdir(o) and os.path.isdir(t) and have[key(e)] == e:
                m, c = plan_moves(o, t)
                moves += m
                clashes += c
            else:
                clashes.append(o)
        else:
            moves.append((o, n))
    return moves, clashes


def main():
    src, dst, files, go, bdir = parse(sys.argv[1:])
    assert os.path.isdir(src) and os.path.isdir(dst) and not (dst + os.sep).startswith(src + os.sep)
    moves, clashes = plan_moves(src, dst)
    for f, nd in files:
        assert os.path.isfile(f) and os.path.isdir(nd), f
        t = os.path.join(nd, os.path.basename(f))
        if key(os.path.basename(f)) in {key(x) for x in os.listdir(nd)}:
            clashes.append(f)
        moves.append((f, t))
    if clashes:
        print('CLASHES, nothing done:')
        for c in clashes:
            print('  ', c)
        sys.exit(1)

    def remap(p):
        for o, n in moves:
            if p == o or p.startswith(o + os.sep):
                return n + p[len(o):]
        return p
    moved = lambda p: remap(p) != p

    edits, stats, checks = [], {'csv cells': 0, 'html refs': 0, 'unresolved before (left)': 0}, []
    roots = [DD] + ([os.path.join(DL, 'images-only')] if os.path.isdir(os.path.join(DL, 'images-only')) else [])
    for root in roots:
        for d, _, fs in os.walk(root):
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
                        if not (moved(p) or moved(q)):
                            continue
                        if not os.path.exists(q):
                            stats['unresolved before (left)'] += 1
                            continue
                        nv = os.path.relpath(remap(q), dn_new)
                        checks.append(os.path.join(dn_new, nv))
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
                        if not (moved(p) or moved(q)) or not os.path.exists(q):
                            return m.group(0)
                        nv = os.path.relpath(remap(q), dn_new)
                        checks.append(os.path.join(dn_new, nv))
                        if nv == v:
                            return m.group(0)
                        cnt[0] += 1
                        return m.group(1) + html.escape(nv, quote=True) + m.group(3)
                    t2 = REF.sub(sub, t)
                    if cnt[0]:
                        edits.append((p, t2.encode('utf-8', errors='surrogateescape')))
                        stats['html refs'] += cnt[0]
    print('moves', len(moves), '|', stats, '| files to rewrite', len(edits))
    for p, _ in edits[:30]:
        print('  ', os.path.relpath(p, DD))
    if not go:
        print('dry run; add --go --backup-dir <new dir>')
        return
    assert bdir and not os.path.exists(bdir)
    os.makedirs(bdir)
    for i, (p, _) in enumerate(edits):
        shutil.copy2(p, os.path.join(bdir, f'{i:03d}_' + os.path.basename(p)))
    for o, n in moves:
        assert not os.path.exists(n), n
        os.rename(o, n)
    for p, data in edits:
        open(remap(p), 'wb').write(data)
    bad = [c for c in checks if not os.path.exists(c)]
    left = [os.path.join(d, f) for d, _, fs in os.walk(src) for f in fs if f != '.DS_Store']
    if not left:
        shutil.rmtree(src)  # only .DS_Store / empty folders left
    print('moved', len(moves), '| files rewritten', len(edits), '| references not resolving after:', len(bad),
          '| src removed' if not left else f'| {len(left)} files left in src', '| backups in', bdir)


if __name__ == '__main__':
    main()
