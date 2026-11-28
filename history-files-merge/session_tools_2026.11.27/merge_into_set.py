"""Merge new layout-A roots (process_html_posts.py output, already cleaned + de-duplicated) into one flat set.

    python3 -I merge_into_set.py --roots R1,R2 --base <scratch base> --pages <dir> --images <dir> --summary <csv>
        --manifest <csv> --txt <txt_merged.txt> [--txt-manifest <csv>] [--others <scratch base>] [--go --backup-dir D]

  pages    every html of each root -> <pages>/<name>; clash (NFC, lower case, no whitespace) -> '<root>__<name>'
  images   every <img src> of a moved page -> <images>/<name> (same name + same bytes reused, other bytes ->
           '<root>__<name>'); links rewritten relative (html.escape, never percent-encoded)
  txt      every txt story appended to <txt> (old.rstrip('\\n') + '\\n\\n' + story + '\\n'); <txt> is created when
           missing; with --txt-manifest a row (no, title, start_line, end_line, chars) is appended (created when
           missing, BOM + LF, PROCESSING_LOGIC 5.3)
  rows     every summary / image-manifest row of each root is appended to <summary> / <manifest>: 'page' and
           'source_file' get '<root>/' in front; 'output' is re-resolved (moved page, moved image, appended txt ->
           the new place; an existing file elsewhere -> kept, rewritten relative; a page of another new root that
           was the kept copy -> its new place via --others) and written relative to the CSV's folder; rows padded
           to the target header (missing columns such as 'note' are added to the target CSV).
Dry run prints counts; --go backs up the target CSVs and txt files first, writes, then checks 0 broken links in the
moved pages and 0 unresolved 'output' cells in the two target CSVs."""
import argparse
import csv
import filecmp
import html
import io
import os
import re
import shutil
import sys
import unicodedata

IMG_SRC = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")', re.I)


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def nfc(p):
    return unicodedata.normalize('NFC', os.path.normpath(p))


def load(p):
    if not os.path.exists(p):
        return None, True, '\r\n'
    data = open(p, 'rb').read()
    bom = data.startswith(b'\xef\xbb\xbf')
    text = data.decode('utf-8-sig')
    eol = '\r\n' if '\r\n' in text else '\n'
    return list(csv.reader(io.StringIO(text, newline=''))), bom, eol


def dump(rows, bom, eol):
    buf = io.StringIO()
    csv.writer(buf, lineterminator=eol).writerows(rows)
    return (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')


def main():
    ap = argparse.ArgumentParser()
    for a in ('--roots', '--base', '--pages', '--images', '--summary', '--manifest', '--txt'):
        ap.add_argument(a, required=True)
    ap.add_argument('--txt-manifest')
    ap.add_argument('--others', action='append', default=[])
    ap.add_argument('--go', action='store_true')
    ap.add_argument('--backup-dir')
    a = ap.parse_args()
    roots = a.roots.split(',')
    P, I = os.path.abspath(a.pages), os.path.abspath(a.images)
    taken_p = {key(f) for f in os.listdir(P)} if os.path.isdir(P) else set()
    taken_i = {key(f): os.path.join(I, f) for f in os.listdir(I)} if os.path.isdir(I) else {}   # case/NFC-insensitive (APFS)
    page_new, img_new, copies, writes, stories = {}, {}, [], [], []
    for root in roots:
        R = os.path.join(a.base, root)
        for d, _, fs in os.walk(os.path.join(R, 'reports')):
            for f in sorted(fs):
                if not f.endswith('.html'):
                    continue
                p = nfc(os.path.join(d, f))
                nm = f
                if key(nm) in taken_p:
                    nm = f'{root}__{f}'
                    assert key(nm) not in taken_p, nm
                taken_p.add(key(nm))
                dst = os.path.join(P, nm)
                t = open(p, encoding='utf-8').read()

                def sub(m):
                    v = html.unescape(m.group(2))
                    if re.match(r'^[a-z]+:', v, re.I):
                        return m.group(0)
                    q = nfc(os.path.join(os.path.dirname(p), v))
                    if q not in img_new:
                        n = os.path.basename(q)
                        for cand in (n, f'{root}__{n}'):
                            if key(cand) not in taken_i:
                                taken_i[key(cand)] = q
                                img_new[q] = os.path.join(I, cand)
                                copies.append((q, img_new[q]))
                                break
                            if filecmp.cmp(q, taken_i[key(cand)], shallow=False) and \
                                    os.path.basename(taken_i[key(cand)]) == cand:
                                img_new[q] = os.path.join(I, cand)
                                break
                        else:
                            sys.exit(f'image clash twice: {q}')
                    return m.group(1) + html.escape(os.path.relpath(img_new[q], P), quote=True) + m.group(3)
                writes.append((dst, IMG_SRC.sub(sub, t)))
                page_new[p] = dst
        for d, _, fs in os.walk(os.path.join(R, 'txt')):
            for f in sorted(fs):
                if f.endswith('.txt'):
                    p = nfc(os.path.join(d, f))
                    stories.append((root, p, open(p, encoding='utf-8').read().strip('\n')))
    txt_set = {p for _, p, _ in stories}
    # pages of other new bases that were kept copies (rows of removed duplicates point there)
    others = {}
    for ob in a.others:
        others.update(json_like(ob))
    out_rows = {'summary': [], 'manifest': []}
    problems = []
    for kind, tcsv in (('summary', a.summary), ('manifest', a.manifest)):
        tdir = os.path.dirname(os.path.abspath(tcsv))
        for root in roots:
            R = os.path.join(a.base, root)
            sp = os.path.join(R, f'{root}_{"summary" if kind == "summary" else "images_manifest"}.csv')
            rows, _, _ = load(sp)
            if not rows:
                continue
            h = rows[0]
            for r in rows[1:]:
                d = dict(zip(h, r))
                col = 'page' if kind == 'summary' else 'source_file'
                d[col] = f'{root}/{d[col]}'
                o = d.get('output', '')
                if o:
                    q = nfc(os.path.join(R, o))
                    if q in page_new:
                        new = page_new[q]
                    elif q in img_new:
                        new = img_new[q]
                    elif q in txt_set:
                        new = os.path.abspath(a.txt)
                    elif q in others:
                        new = others[q]
                    elif os.path.exists(q) and not q.startswith(nfc(a.base) + os.sep):
                        new = q
                    else:
                        problems.append((kind, root, o))
                        new = None
                    d['output'] = os.path.relpath(new, tdir) if new else ''
                out_rows[kind].append(d)
    print(f'pages {len(page_new)} | images copied {len(copies)} | txt stories {len(stories)} | '
          f'summary rows {len(out_rows["summary"])} | manifest rows {len(out_rows["manifest"])}')
    for x in problems[:15]:
        print('   PROBLEM', x)
    if problems:
        sys.exit(f'{len(problems)} problems; nothing written')
    if not a.go:
        print('dry run; add --go --backup-dir <new dir>')
        return
    assert a.backup_dir and not os.path.exists(a.backup_dir)
    os.makedirs(a.backup_dir)
    for f in (a.summary, a.manifest, a.txt, a.txt_manifest):
        if f and os.path.exists(f):
            shutil.copy2(f, os.path.join(a.backup_dir, os.path.basename(f)))
    os.makedirs(P, exist_ok=True)
    os.makedirs(I, exist_ok=True)
    for s, d in copies:
        assert not os.path.exists(d), d          # never overwrite (APFS is case-insensitive)
        shutil.copy2(s, d)
    for d, t in writes:
        assert not os.path.exists(d), d
        open(d, 'w', encoding='utf-8').write(t)
    for kind, tcsv in (('summary', a.summary), ('manifest', a.manifest)):
        rows, bom, eol = load(tcsv)
        if rows is None:
            first = out_rows[kind][0] if out_rows[kind] else {}
            rows, bom, eol = [list(first.keys())], True, '\r\n'
        h = rows[0]
        for d in out_rows[kind]:
            for c in d:
                if c not in h:
                    h.append(c)
                    for r in rows[1:]:
                        r.append('')
            rows.append([d.get(c, '') for c in h])
        open(tcsv, 'wb').write(dump(rows, bom, eol))
    if stories:
        old = open(a.txt, encoding='utf-8').read().rstrip('\n') if os.path.exists(a.txt) else ''
        mrows = None
        if a.txt_manifest:
            mrows, mbom, meol = load(a.txt_manifest)
            if mrows is None:
                mrows, mbom, meol = [['no', 'title', 'start_line', 'end_line', 'chars']], True, '\n'
        no = int(mrows[-1][0]) if mrows and len(mrows) > 1 else 0
        for root, p, text in stories:
            start = old.count('\n') + 3 if old else 1
            old = (old + '\n\n' + text) if old else text
            no += 1
            if mrows is not None:
                mrows.append([str(no), text.split('\n')[0], str(start), str(start + text.count('\n')), str(len(text))])
        open(a.txt, 'w', encoding='utf-8', newline='\n').write(old + '\n')
        if mrows is not None:
            open(a.txt_manifest, 'wb').write(dump(mrows, mbom, meol))
    broken = sum(1 for d, _ in writes for m in IMG_SRC.finditer(open(d, encoding='utf-8').read())
                 if not re.match(r'^[a-z]+:', m.group(2), re.I)
                 and not os.path.isfile(os.path.join(os.path.dirname(d), html.unescape(m.group(2)))))
    bad = 0
    for tcsv in (a.summary, a.manifest):
        tdir = os.path.dirname(os.path.abspath(tcsv))
        for r in csv.DictReader(open(tcsv, encoding='utf-8-sig')):
            if r.get('output') and not os.path.exists(os.path.join(tdir, r['output'])):
                bad += 1
    print(f'written; broken links in moved pages {broken}; unresolved output cells in target CSVs {bad}')


def json_like(path):
    """TSV 'old page<TAB>new page' produced by an earlier run (lets rows of a removed copy follow its kept page)."""
    m = {}
    for l in open(path, encoding='utf-8').read().splitlines():
        if '\t' in l:
            o, n = l.split('\t', 1)
            m[nfc(o)] = n
    return m


if __name__ == '__main__':
    main()
