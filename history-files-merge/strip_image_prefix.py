"""Rename images (or, with --kind html|all, html pages): drop the leading segment up to and including a marker (default '__x_'), then drop leading
heads such as '【新提醒】'; repoint every HTML <img src>/<a href> and every CSV cell that points to a renamed file.

    python3 strip_image_prefix.py [root ...]                       dry run (default root: DD)
    python3 strip_image_prefix.py [root ...] --go --backup-dir D   act; D must not exist yet
    python3 strip_image_prefix.py --kind html [root ...]           same rule for .html/.htm file names

  e.g. 'Great_Redarmy_B__x_【新提醒】abc.jpg' -> 'abc.jpg'

Rules
  * marker: first occurrence; everything before it and the marker itself are removed. Names without the marker
    only get the head strip (so a bare '【新提醒】x.jpg' becomes 'x.jpg').
  * heads ('--head', repeatable, default 【新提醒】) are removed repeatedly from the start, then leading spaces.
  * a new name that is empty / only an extension / over 240 bytes keeps the old name (listed).
  * clash (same folder, NFC + lower case + no whitespace, against untouched files too): every clashing renamed
    member becomes '<part before marker>__<new name>'; still clashing -> old name kept (listed).
  * HTML: src/href values (html-unescaped, percent-decoded for matching) that resolve to a renamed file are
    rewritten as html.escape(relpath, quote=True), never percent-encoded.
  * CSV: a cell that resolves (relative to the CSV's folder) to a renamed file is rewritten with the same
    relative style; a bare file name (no '/') is rewritten when the file sits in the CSV's folder or its
    'images/' sub-folder (images_merged.manifest.csv 'file' column). Provenance columns (source paths that do
    not resolve) are left alone. BOM, EOL, column order kept; a CSV that does not round-trip byte-identically
    through the csv module is not touched and is listed.
  * --go: every rewritten HTML/CSV is copied to the backup dir first; renamed_images.tsv (old -> new) is
    written there. Afterwards: old paths gone, new paths exist with the same size, 0 references to old paths.
"""
import argparse
import csv
import html
import io
import os
import re
import shutil
import sys
import unicodedata
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hfm_config import DD  # noqa: E402

IMG_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff')
HTML_EXT = ('.html', '.htm')
KINDS = {'images': IMG_EXT, 'html': HTML_EXT, 'all': IMG_EXT + HTML_EXT}
ATTR = re.compile(r'''(\b(?:src|href)\s*=\s*)(["'])(.*?)\2''', re.I | re.S)


def nfc(s):
    return unicodedata.normalize('NFC', s)


def key(s):
    return re.sub(r'\s+', '', nfc(s).lower())


def strip_name(name, marker, heads):
    prefix = ''
    i = name.find(marker) if marker else -1
    if i >= 0:
        prefix, name = name[:i], name[i + len(marker):]
    changed = True
    while changed:
        changed = False
        for h in heads:
            if name.startswith(h):
                name = name[len(h):].lstrip()
                changed = True
    return prefix, name


def plan(roots, marker, heads, exts=IMG_EXT):
    renames, kept = {}, []                       # abs old -> abs new
    for root in roots:
        for d, _, fs in os.walk(root):
            cand = {}
            for f in fs:
                if not f.lower().endswith(exts):
                    continue
                prefix, new = strip_name(f, marker, heads)
                if new == f:
                    continue
                stem = os.path.splitext(new)[0]
                if not stem.strip() or len(new.encode()) > 240:
                    kept.append((os.path.join(d, f), 'empty-or-too-long'))
                    continue
                cand[f] = (prefix, new)
            if not cand:
                continue
            final = {f: cand[f][1] if f in cand else f for f in fs}

            def clashes():
                c = {}
                for f, n in final.items():
                    c.setdefault(key(n), []).append(f)
                return {f for v in c.values() if len(v) > 1 for f in v}
            for f in clashes():
                if f in cand and cand[f][0]:
                    final[f] = cand[f][0] + '__' + cand[f][1]
            for f in clashes():
                if f in cand:
                    final[f] = f
                    kept.append((os.path.join(d, f), 'clash'))
            for f in cand:
                if final[f] != f:
                    renames[nfc(os.path.join(d, f))] = os.path.join(d, final[f])
    return renames, kept


def resolve(base, val):
    return nfc(os.path.normpath(os.path.join(base, val)))


def fix_html(text, hdir, renames):
    n = 0

    def sub(m):
        nonlocal n
        raw = m.group(3)
        v = html.unescape(raw).strip()
        if not v or re.match(r'^(?:[a-z][a-z0-9+.-]*:|//|#)', v, re.I):
            return m.group(0)
        for cand in (v, unquote(v)):
            p = resolve(hdir, cand)
            if p in renames:
                n += 1
                rel = os.path.relpath(renames[p], hdir)
                return m.group(1) + m.group(2) + html.escape(rel, quote=True) + m.group(2)
        return m.group(0)
    return ATTR.sub(sub, text), n


def fix_csv(data, cdir, renames):
    bom = data.startswith(b'\xef\xbb\xbf')
    text = data.decode('utf-8-sig')
    eol = '\r\n' if '\r\n' in text else '\n'
    rows = list(csv.reader(io.StringIO(text, newline='')))

    def dump(rs):
        buf = io.StringIO()
        csv.writer(buf, lineterminator=eol).writerows(rs)
        return (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')
    if dump(rows) != data:
        return None, 0
    n = 0
    for r in rows:
        for i, cell in enumerate(r):
            v = cell.strip()
            if not v:
                continue
            if '/' in v or '\\' in v:
                p = resolve(cdir, v)
                if p in renames:
                    r[i] = os.path.relpath(renames[p], cdir)
                    n += 1
            else:
                for sub in ('', 'images'):
                    p = nfc(os.path.normpath(os.path.join(cdir, sub, v)))
                    if p in renames:
                        r[i] = os.path.basename(renames[p])
                        n += 1
                        break
    return (dump(rows) if n else data), n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('roots', nargs='*', help='folders whose images are renamed (default: DD)')
    ap.add_argument('--refs-root', default=DD, help='folder scanned for HTML/CSV references (default: DD)')
    ap.add_argument('--marker', default='__x_')
    ap.add_argument('--head', action='append', help='leading string to drop (repeatable; default 【新提醒】)')
    ap.add_argument('--kind', choices=sorted(KINDS), default='images',
                    help='which files are renamed: images (default), html pages, or all')
    ap.add_argument('--go', action='store_true')
    ap.add_argument('--backup-dir')
    a = ap.parse_args()
    roots = [os.path.abspath(r) for r in (a.roots or [DD])]
    heads = a.head or ['【新提醒】']
    for r in roots + [a.refs_root]:
        if not os.path.isdir(r):
            raise FileNotFoundError(r)
    if a.go and (not a.backup_dir or os.path.exists(a.backup_dir)):
        sys.exit('--go needs --backup-dir that does not exist yet')

    renames, kept = plan(roots, a.marker, heads, KINDS[a.kind])
    print(f'{a.kind} files to rename: {len(renames)}; kept old name: {len(kept)}')
    for p, why in kept[:20]:
        print(f'  kept ({why}): {os.path.relpath(p, a.refs_root)}')
    fall = [(o, n) for o, n in renames.items() if '__' in os.path.basename(n)
            and os.path.basename(n).split('__', 1)[0] == os.path.basename(o).split(a.marker, 1)[0]]
    for o, n in fall:
        print(f'  clash fallback: {os.path.basename(o)} -> {os.path.basename(n)}')

    edits, skipped, nh, nc = [], [], 0, 0
    for d, _, fs in os.walk(a.refs_root):
        for f in fs:
            p = os.path.join(d, f)
            low = f.lower()
            if low.endswith(('.html', '.htm')):
                raw = open(p, 'rb').read()
                try:
                    text = raw.decode('utf-8')
                except UnicodeDecodeError:
                    if any(os.path.basename(o).encode() in raw for o in renames):
                        skipped.append((p, 'html not utf-8'))
                    continue
                new, n = fix_html(text, d, renames)
                if n:
                    edits.append((p, new.encode('utf-8'), n))
                    nh += n
            elif low.endswith('.csv'):
                raw = open(p, 'rb').read()
                new, n = fix_csv(raw, d, renames)
                if new is None:
                    if any(os.path.basename(o).encode() in raw for o in renames):
                        skipped.append((p, 'csv does not round-trip'))
                    continue
                if n:
                    edits.append((p, new, n))
                    nc += n
    print(f'html links to rewrite: {nh} in {sum(1 for e in edits if e[0].lower().endswith(("htm", "html")))} files')
    print(f'csv cells to rewrite: {nc} in {sum(1 for e in edits if e[0].lower().endswith(".csv"))} files')
    for p, _, n in sorted(edits, key=lambda e: -e[2]):
        print(f'  {n:6d}  {os.path.relpath(p, a.refs_root)}')
    for p, why in skipped:
        print(f'  NOT TOUCHED ({why}): {os.path.relpath(p, a.refs_root)}')
    if not a.go:
        print('dry run; add --go --backup-dir <new dir> to act')
        return

    os.makedirs(a.backup_dir)
    for p, _, _ in edits:
        dst = os.path.join(a.backup_dir, os.path.relpath(p, a.refs_root))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
    with open(os.path.join(a.backup_dir, 'renamed_images.tsv'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('old\tnew\n')
        for o, n in sorted(renames.items()):
            fh.write(f'{os.path.relpath(o, a.refs_root)}\t{os.path.relpath(n, a.refs_root)}\n')
    sizes = {}
    for o, n in renames.items():
        if os.path.exists(n):
            sys.exit(f'target exists, stopped before renaming: {n}')
    for o, n in renames.items():
        sizes[n] = os.path.getsize(o)
        os.rename(o, n)
    for p, data, _ in edits:
        p = renames.get(nfc(p), p)          # a rewritten page may itself have been renamed
        with open(p, 'wb') as fh:
            fh.write(data)

    bad = [n for n, s in sizes.items() if not os.path.isfile(n) or os.path.getsize(n) != s]
    left = [o for o in renames if os.path.exists(o) and nfc(o) != nfc(renames[o])]
    stale = 0
    for p, _, _ in edits:
        p = renames.get(nfc(p), p)
        d = os.path.dirname(p)
        if p.lower().endswith('.csv'):
            _, n = fix_csv(open(p, 'rb').read(), d, renames)
        else:
            _, n = fix_html(open(p, encoding='utf-8').read(), d, renames)
        stale += n
    print(f'renamed {len(renames)}; size mismatch/missing {len(bad)}; old still present {len(left)}; '
          f'references to old paths left {stale}; backup + log in {a.backup_dir}')


if __name__ == '__main__':
    main()
