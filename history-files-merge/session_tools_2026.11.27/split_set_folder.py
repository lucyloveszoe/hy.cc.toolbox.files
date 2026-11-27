"""Repair a set folder the user split by hand: pages moved from <base>/<src> to <base>/<new> (flat layout B,
images in <set>/images/<set>/). Images are not moved by hand, so the moved pages' links break.

    python3 split_set_folder.py <base> <src set> <new set> [--go --backup-dir D]

For every page in <base>/<new>: each local <img src> is resolved against the page's OLD folder <base>/<src>.
  * image used only by pages now in <new>  -> moved to <base>/<new>/images/<new>/<same name>
  * image also used by a page still in <src> (or any other folder) -> stays; link points to it (../<src>/images/…)
  Links are rewritten relative (html.escape, never percent-encoded).
Every CSV under <base>: a cell that resolves (relative to the CSV's folder) to a page that was in <src> and is now
in <new>, or to a moved image, is rewritten to the new place. BOM/EOL/column order kept; a CSV that does not
round-trip byte-identically through the csv module stops the run. --go backs up the CSVs and the pages first.
Checks after --go: 0 broken links in <new> and <src>, 0 CSV cells pointing to the old paths.
"""
import csv, html, io, os, re, shutil, sys, unicodedata

SRC = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")', re.I)
nfc = lambda p: unicodedata.normalize('NFC', os.path.normpath(p))


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
    return (rows, dump) if dump(rows) == data else (None, None)


def local(v):
    return not re.match(r'^(?:[a-z][a-z0-9+.-]*:|//)', v, re.I)


def main():
    base, src, new = [os.path.abspath(sys.argv[1])] + sys.argv[2:4]
    go = '--go' in sys.argv
    backup = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
    if go and (not backup or os.path.exists(backup)):
        sys.exit('--go needs --backup-dir that does not exist yet')
    S, N = os.path.join(base, src), os.path.join(base, new)
    new_pages = [f for f in os.listdir(N) if f.lower().endswith(('.html', '.htm'))]
    # who uses which image (pages anywhere under base, resolved from their own folder; new pages from the old one)
    users = {}
    for d, _, fs in os.walk(base):
        if os.sep + 'images' in d[len(base):]:
            continue
        for f in fs:
            if not f.lower().endswith(('.html', '.htm')):
                continue
            p = os.path.join(d, f)
            ref = S if nfc(d) == nfc(N) else d
            for _, s, _ in SRC.findall(open(p, encoding='utf-8', errors='replace').read()):
                v = html.unescape(s)
                if local(v):
                    users.setdefault(nfc(os.path.join(ref, v)), set()).add(nfc(d))
    moved_img, missing = {}, []
    idir = os.path.join(N, 'images', new)
    for q, ds in users.items():
        if nfc(N) in ds:
            if not os.path.isfile(q):
                if not os.path.isfile(q.replace(nfc(S), nfc(N), 1)):
                    missing.append(q)
                continue
            if ds == {nfc(N)} and q.startswith(nfc(S) + os.sep):
                moved_img[q] = os.path.join(idir, os.path.basename(q))
    names = {}
    for q, t in moved_img.items():
        k = unicodedata.normalize('NFC', os.path.basename(t)).lower()
        if k in names:
            sys.exit(f'name clash in {idir}: {t}')
        names[k] = q
    page_old_new = {nfc(os.path.join(S, f)): os.path.join(N, f) for f in new_pages}
    # pages: rewrite links
    page_text = {}
    for f in new_pages:
        p = os.path.join(N, f)
        t = open(p, encoding='utf-8').read()

        def sub(m):
            v = html.unescape(m.group(2))
            if not local(v):
                return m.group(0)
            q = nfc(os.path.join(S, v))
            if not os.path.isfile(q) and os.path.isfile(nfc(os.path.join(N, v))):
                return m.group(0)                      # already fine
            tgt = moved_img.get(q, q)
            return m.group(1) + html.escape(os.path.relpath(tgt, N), quote=True) + m.group(3)
        nt = SRC.sub(sub, t)
        if nt != t:
            page_text[p] = nt
    # CSVs
    gone = {**page_old_new, **moved_img}
    edits = []
    for d, _, fs in os.walk(base):
        for f in fs:
            if not f.endswith('.csv'):
                continue
            p = os.path.join(d, f)
            rows, dump = load_csv(p)
            if rows is None:
                sys.exit(f'csv does not round-trip: {p}')
            n = 0
            for r in rows[1:]:
                for i, c in enumerate(r):
                    v = c.strip()
                    if v and '/' in v:
                        q = nfc(os.path.join(d, v))
                        if q in gone:
                            r[i] = os.path.relpath(gone[q], d)
                            n += 1
            if n:
                edits.append((p, dump(rows), n))
    print(f'pages in {new}: {len(new_pages)} (links to rewrite in {len(page_text)}) | images to move {len(moved_img)} | '
          f'shared images left in place {sum(1 for q, ds in users.items() if nfc(N) in ds and q not in moved_img and os.path.isfile(q))} | '
          f'missing images {len(missing)}')
    for p, _, n in edits:
        print(f'   csv {n:5d} cells  {os.path.relpath(p, base)}')
    if not go:
        print('dry run; add --go --backup-dir <new dir>')
        return
    os.makedirs(backup)
    for p, _, _ in edits:
        shutil.copy2(p, os.path.join(backup, os.path.basename(p)))
    os.makedirs(os.path.join(backup, 'pages'))
    for p in page_text:
        shutil.copy2(p, os.path.join(backup, 'pages', os.path.basename(p)))
    with open(os.path.join(backup, 'moved_images.tsv'), 'w', encoding='utf-8') as fh:
        fh.write('old\tnew\n')
        for q, t in moved_img.items():
            fh.write(f'{os.path.relpath(q, base)}\t{os.path.relpath(t, base)}\n')
    os.makedirs(idir, exist_ok=True)
    for q, t in moved_img.items():
        assert not os.path.exists(t), t
        shutil.move(q, t)
    for p, t in page_text.items():
        open(p, 'w', encoding='utf-8').write(t)
    for p, data, _ in edits:
        open(p, 'wb').write(data)
    broken = 0
    for D in (S, N):
        for f in os.listdir(D):
            if f.lower().endswith(('.html', '.htm')):
                for _, s, _ in SRC.findall(open(os.path.join(D, f), encoding='utf-8', errors='replace').read()):
                    v = html.unescape(s)
                    if local(v) and not os.path.isfile(os.path.join(D, v)):
                        broken += 1
    stale = 0
    for d, _, fs in os.walk(base):
        for f in fs:
            if f.endswith('.csv'):
                for r in csv.reader(open(os.path.join(d, f), encoding='utf-8-sig', newline='')):
                    stale += sum(1 for c in r if c.strip() and '/' in c and nfc(os.path.join(d, c.strip())) in gone)
    print(f'moved {len(moved_img)} images; broken links in {src}+{new}: {broken}; csv cells on old paths: {stale}; backup {backup}')


if __name__ == '__main__':
    main()
