"""Move the pages of new layout-A roots into the routed library (PROCESSING_LOGIC 6.1 mechanics, 6.2 append).

    python3 route_new_into_library.py <assign.tsv> <src base> <backup dir> [--go]

assign.tsv: root, output (relative to <src base>/<root>), kind (html | txt:<topic>), target_root (relative to
<MC>/html, e.g. locations/港澳 or merges/FDZone_内地; for txt = the html root whose summary gets the row), basis, top_scores.
MC = DD/mc_2026.11.19.

html: copied to <target>/reports/<name> (clash, NFC/lower/no-space -> '<stem> (<root>).html'); images copied into
  <target>/images/<target name>/ (same name + same bytes reused, other bytes -> '<root>__<name>'); <img src> rewritten
  relative (html.escape, never percent-encoded).
txt: appended to MC/txt/topics/mc_<topic>.txt (old.rstrip('\\n') + '\\n\\n' + story + '\\n'), manifest row
  (no, '<root>／<file>', start, end, chars) and routing_report row (no, file, topic, basis, top_scores).
CSV rows (summary + images manifest of each source root) move to the target root's CSVs: 'page' / 'source_file'
  get the zip folder in front ('<root>/…'); 'output' is re-resolved and written relative to the target CSV; rows are
  padded to the target header (note column). A summary row goes with the page (or txt story) its output names;
  unsupported rows (no output) go to merges/FDZone_内地; a manifest row goes with the page whose '_files' folder it came
  from. Target CSVs and txt files are backed up first; target folders that do not exist yet are created with the
  source headers + 'note'. Nothing in the source roots is changed.
"""
import csv
import html
import io
import os
import re
import shutil
import sys
import unicodedata
import filecmp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hfm_config import DD  # noqa: E402

MC = os.path.join(DD, 'mc_2026.11.19')
HT = os.path.join(MC, 'html')
TOP = os.path.join(MC, 'txt', 'topics')
IMG_SRC = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")', re.I)
UNROUTED = 'merges/FDZone_内地'


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def nfc(p):
    return unicodedata.normalize('NFC', os.path.normpath(p))


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
    assign_p, base, backup = sys.argv[1:4]
    go = '--go' in sys.argv
    if go and os.path.exists(backup) and os.listdir(backup) and not os.path.isdir(os.path.join(backup, 'library')):
        pass
    A = [l.split('\t') for l in open(assign_p, encoding='utf-8').read().splitlines()[1:] if l.strip()]
    roots = sorted({a[0] for a in A})
    tdir = lambda t: os.path.join(HT, t)
    tname = lambda t: os.path.basename(t)

    # ---------- plan pages
    page_new = {}          # src page abs -> (target, new abs)
    img_new = {}           # (src img abs, target) -> new abs
    copies = []            # (src, dst) image copies
    writes = []            # (dst page, text)
    names = {}             # target -> set of keys taken
    img_taken = {}         # target -> {name: src path or existing}
    txt_assign = {}
    for root, out, kind, target, basis, top in A:
        p = nfc(os.path.join(base, root, out))
        if kind.startswith('txt:'):
            txt_assign[p] = (kind[4:], target, basis, top, root)
            continue
        T = tdir(target)
        if T not in names:
            names[T] = {key(f) for f in os.listdir(os.path.join(T, 'reports'))} if os.path.isdir(T) else set()
            idir = os.path.join(T, 'images', tname(target))
            img_taken[T] = {f: None for f in os.listdir(idir)} if os.path.isdir(idir) else {}
        nm = os.path.basename(p)
        if key(nm) in names[T]:
            st, ext = os.path.splitext(nm)
            nm = f'{st} ({root}){ext}'
            assert key(nm) not in names[T], nm
        names[T].add(key(nm))
        dst = os.path.join(T, 'reports', nm)
        idir = os.path.join(T, 'images', tname(target))
        t = open(p, encoding='utf-8').read()

        def sub(m):
            v = html.unescape(m.group(2))
            q = nfc(os.path.join(os.path.dirname(p), v))
            if (q, T) not in img_new:
                n = os.path.basename(q)
                for cand in (n, f'{root}__{n}'):
                    if cand not in img_taken[T]:
                        img_taken[T][cand] = q
                        img_new[(q, T)] = os.path.join(idir, cand)
                        copies.append((q, os.path.join(idir, cand)))
                        break
                    other = img_taken[T][cand]
                    other_path = other if other else os.path.join(idir, cand)
                    if filecmp.cmp(q, other_path, shallow=False):
                        img_new[(q, T)] = os.path.join(idir, cand)
                        break
                else:
                    sys.exit(f'image name clash twice: {q} in {T}')
            rel = os.path.relpath(img_new[(q, T)], os.path.join(T, 'reports'))
            return m.group(1) + html.escape(rel, quote=True) + m.group(3)
        writes.append((dst, IMG_SRC.sub(sub, t)))
        page_new[p] = (target, dst)

    # ---------- plan txt appends
    txt_plan = {}          # topic -> list of (root, file name, text, basis, top)
    for p, (topic, target, basis, top, root) in txt_assign.items():
        text = open(p, encoding='utf-8').read().strip('\n')
        txt_plan.setdefault(topic, []).append((root, os.path.basename(p), text, basis, top))
    txt_file = lambda topic: os.path.join(TOP, f'mc_{topic}.txt')

    # ---------- plan CSV rows
    add_summary, add_manifest = {}, {}       # target -> rows (as dicts)
    headers = {}
    owner_target = {}                         # (root, page stem key) -> target
    problems = []
    for root in roots:
        R = os.path.join(base, root)
        rows = list(csv.DictReader(open(os.path.join(R, f'{root}_summary.csv'), encoding='utf-8-sig', newline='')))
        headers.setdefault('summary', list(rows[0].keys()))
        for r in rows:
            o = r['output']
            tgt = UNROUTED
            newo = ''
            if o:
                q = nfc(os.path.join(R, o))
                if q in page_new:
                    tgt, dst = page_new[q]
                    newo = os.path.relpath(dst, tdir(tgt))
                elif q in txt_assign:
                    topic, tgt = txt_assign[q][0], txt_assign[q][1]
                    newo = os.path.relpath(txt_file(topic), tdir(tgt))
                elif q.startswith(nfc(HT) + os.sep) and os.path.isfile(q):      # duplicate of a library page
                    tgt = os.path.relpath(q, HT).split(os.sep)
                    tgt = '/'.join(tgt[:2])
                    newo = os.path.relpath(q, tdir(tgt))
                else:
                    problems.append(('summary output not resolved', root, o))
            stem = key(os.path.splitext(r['page'])[0])
            owner_target.setdefault((root, stem), tgt)
            nr = dict(r)
            nr['page'] = f"{root}/{r['page']}"
            nr['output'] = newo
            add_summary.setdefault(tgt, []).append(nr)
        rows = list(csv.DictReader(open(os.path.join(R, f'{root}_images_manifest.csv'), encoding='utf-8-sig', newline='')))
        headers.setdefault('manifest', list(rows[0].keys()))
        for r in rows:
            sf = r['source_file']
            pg = sf.split('_files/')[0] if '_files/' in sf else os.path.splitext(sf)[0]
            tgt = owner_target.get((root, key(pg)), UNROUTED)
            o = r['output']
            newo = ''
            if o:
                q = nfc(os.path.join(R, o))
                if (q, tdir(tgt)) in img_new:
                    newo = os.path.relpath(img_new[(q, tdir(tgt))], tdir(tgt))
                else:
                    hits = [v for (s, T), v in img_new.items() if s == q]
                    if hits:
                        newo = os.path.relpath(hits[0], tdir(tgt))
                    elif os.path.isfile(q) and q.startswith(nfc(MC) + os.sep):        # flat images / library
                        newo = os.path.relpath(q, tdir(tgt))
                    else:
                        problems.append(('manifest output not resolved', root, o))
            nr = dict(r)
            nr['source_file'] = f'{root}/{sf}'
            nr['output'] = newo
            add_manifest.setdefault(tgt, []).append(nr)

    # ---------- report
    print('pages', len(page_new), '| images to copy', len(copies), '| txt stories', sum(len(v) for v in txt_plan.values()))
    for t in sorted(set(add_summary) | set(add_manifest)):
        n_pages = sum(1 for v in page_new.values() if v[0] == t)
        print(f'   {t:32} pages {n_pages:4}  summary rows {len(add_summary.get(t, [])):4}  manifest rows {len(add_manifest.get(t, [])):5}'
              f"{'  (new root)' if not os.path.isdir(tdir(t)) else ''}")
    for topic, items in txt_plan.items():
        print(f'   txt mc_{topic}: +{len(items)}')
    for x in problems[:20]:
        print('   PROBLEM', x)
    if problems:
        sys.exit(f'{len(problems)} problems; nothing written')
    if not go:
        print('dry run; add --go')
        return

    # ---------- act
    os.makedirs(backup, exist_ok=False)
    touched_csv = set()
    for t in set(add_summary) | set(add_manifest):
        T = tdir(t)
        for kind in ('summary', 'images_manifest'):
            touched_csv.add(os.path.join(T, f'{tname(t)}_{kind}.csv'))
    for p in sorted(touched_csv) + [txt_file(t) for t in txt_plan] + \
            [txt_file(t)[:-4] + '.manifest.csv' for t in txt_plan] + [os.path.join(TOP, 'routing_report.csv')]:
        if os.path.exists(p):
            dst = os.path.join(backup, os.path.relpath(p, DD))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(p, dst)
    for t in set(add_summary) | set(add_manifest):
        T = tdir(t)
        if not os.path.isdir(T):
            os.makedirs(os.path.join(T, 'reports'))
            os.makedirs(os.path.join(T, 'images', tname(t)))
            for kind, hk in (('summary', 'summary'), ('images_manifest', 'manifest')):
                with open(os.path.join(T, f'{tname(t)}_{kind}.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
                    csv.writer(fh, lineterminator='\r\n').writerow(headers[hk] + (['note'] if 'note' not in headers[hk] else []))
    for s, d in copies:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
    for d, text in writes:
        assert not os.path.exists(d), d
        open(d, 'w', encoding='utf-8').write(text)
    for t in set(add_summary) | set(add_manifest):
        T = tdir(t)
        for kind, rowsets in (('summary', add_summary), ('images_manifest', add_manifest)):
            p = os.path.join(T, f'{tname(t)}_{kind}.csv')
            rows, dump = load_csv(p)
            h = rows[0]
            for r in rowsets.get(t, []):
                rows.append([r.get(c, '') for c in h])
                extra = set(r) - set(h)
                assert not extra, (p, extra)
            open(p, 'wb').write(dump(rows))
    # txt appends
    for topic, items in txt_plan.items():
        tf = txt_file(topic)
        mf = tf[:-4] + '.manifest.csv'
        old = open(tf, encoding='utf-8').read().rstrip('\n') if os.path.exists(tf) else ''
        mrows, mdump = load_csv(mf)
        no = int(mrows[-1][0]) if len(mrows) > 1 else 0
        for root, fname, text, basis, top in items:
            start = old.count('\n') + 3 if old else 1
            old = (old + '\n\n' + text) if old else text
            end = start + text.count('\n')
            no += 1
            mrows.append([str(no), f'{root}／{fname}', str(start), str(end), str(len(text))])
        open(tf, 'w', encoding='utf-8', newline='\n').write(old + '\n')
        open(mf, 'wb').write(mdump(mrows))
    rr = os.path.join(TOP, 'routing_report.csv')
    rrows, rdump = load_csv(rr)
    no = int(rrows[-1][0])
    for topic, items in txt_plan.items():
        for root, fname, text, basis, top in items:
            no += 1
            rrows.append([str(no), f'{root}／{fname}', topic, basis, top])
    open(rr, 'wb').write(rdump(rrows))
    print('written; backups in', backup)


if __name__ == '__main__':
    main()
