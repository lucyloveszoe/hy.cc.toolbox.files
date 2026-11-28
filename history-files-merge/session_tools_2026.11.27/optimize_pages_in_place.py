"""Replace saved pages that show pictures by their clean report version, in place (raw archives such as 旅行记录).

    python3 -I optimize_pages_in_place.py <archive dir> <processed base> <folder,...> [--txt] [--go --quarantine Q]

--txt: handle the rows with mode txt instead (pages without saved pictures): the original page and its '_files'
folder -> Q, <same dir>/<stem>.txt = the cleaned story (title, author line, post text). An existing <stem>.txt is
never overwritten (the page is then listed and skipped).

<processed base>/<folder> is process_html_posts.py output for <archive dir>/<folder> (+ add_summary_output.py, noise
passes). For every summary row with mode html:
  original  <archive>/<folder>/<page>  (.htm/.html) and its '<stem>_files' / '<stem>.files' folder -> Q (same paths)
  new       <same dir>/<stem>.html = the report; its pictures copied into <same dir>/<stem>_files/ (report names
            p<NNN>_…), <img src> rewritten '<stem>_files/<name>' (html.escape, never percent-encoded)
A '_files' folder that another page staying in the same directory links is copied, not moved. Pages without pictures
(txt rows) and unsupported pages are left as they are. Checks after --go: every <img src> of the new pages resolves,
0 original pages left, nothing overwritten (APFS is case-insensitive: existence is checked before every write)."""
import csv
import html
import os
import re
import shutil
import sys
import unicodedata

IMG_SRC = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")', re.I)


def main():
    A, B, folders = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
    go = '--go' in sys.argv
    mode = 'txt' if '--txt' in sys.argv else 'html'
    Q = sys.argv[sys.argv.index('--quarantine') + 1] if '--quarantine' in sys.argv else None
    jobs = []
    for f in folders:
        R = os.path.join(B, f)
        for r in csv.DictReader(open(os.path.join(R, f'{f}_summary.csv'), encoding='utf-8-sig')):
            if r['mode'] != mode or not r['output']:
                continue
            src = os.path.join(A, f, r['page'])
            rep = os.path.join(R, r['output'])
            assert os.path.isfile(src) and os.path.isfile(rep), (src, rep)
            d, stem = os.path.dirname(src), os.path.splitext(os.path.basename(src))[0]
            fdirs = [os.path.join(d, stem + s) for s in ('_files', '.files') if os.path.isdir(os.path.join(d, stem + s))]
            jobs.append((src, rep, d, stem, fdirs))
    srcs = {j[0] for j in jobs}
    # a _files folder linked by a page that stays (not in jobs) in the same dir must be copied, not moved
    shared = set()
    for src, rep, d, stem, fdirs in jobs:
        for fd in fdirs:
            name = os.path.basename(fd)
            for g in os.listdir(d):
                p = os.path.join(d, g)
                if p in srcs or not g.lower().endswith(('.htm', '.html')):
                    continue
                if name.encode('utf-8') in open(p, 'rb').read() or name in open(p, encoding='utf-8', errors='replace').read():
                    shared.add(fd)
    if mode == 'txt':
        return do_txt(A, jobs, shared, go, Q)
    plan = []
    for src, rep, d, stem, fdirs in jobs:
        new = os.path.join(d, stem + '.html')
        ndir = os.path.join(d, stem + '_files')
        t = open(rep, encoding='utf-8').read()
        imgs = []

        def sub(m):
            v = html.unescape(m.group(2))
            if re.match(r'^[a-z]+:', v, re.I):
                return m.group(0)
            q = os.path.normpath(os.path.join(os.path.dirname(rep), v))
            imgs.append(q)
            return m.group(1) + html.escape(f'{stem}_files/{os.path.basename(q)}', quote=True) + m.group(3)
        plan.append((src, new, ndir, fdirs, IMG_SRC.sub(sub, t), imgs))
    n_img = sum(len(set(p[5])) for p in plan)
    print(f'pages {len(plan)} | pictures {n_img} | _files folders to quarantine {sum(len(p[3]) for p in plan) - len(shared)} '
          f'| shared _files (copied, kept) {len(shared)}')
    if not go:
        print('dry run; add --go --quarantine <new dir>')
        return
    assert Q and not os.path.exists(Q)
    os.makedirs(Q)
    log = open(os.path.join(Q, 'replaced.tsv'), 'w', encoding='utf-8')
    for src, new, ndir, fdirs, text, imgs in plan:
        for p in [src] + fdirs:
            dst = os.path.join(Q, os.path.relpath(p, A))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            (shutil.copytree(p, dst) if p in shared else shutil.move(p, dst))
        assert not os.path.exists(new) and not os.path.exists(ndir), new
        os.makedirs(ndir)
        for q in dict.fromkeys(imgs):
            shutil.copy2(q, os.path.join(ndir, os.path.basename(q)))
        open(new, 'w', encoding='utf-8').write(text)
        log.write(f'{os.path.relpath(src, A)}\t{os.path.relpath(new, A)}\n')
    broken = 0
    for src, new, ndir, fdirs, text, imgs in plan:
        for m in IMG_SRC.finditer(open(new, encoding='utf-8').read()):
            v = html.unescape(m.group(2))
            if not re.match(r'^[a-z]+:', v, re.I) and not os.path.isfile(os.path.join(os.path.dirname(new), v)):
                broken += 1
    left = sum(os.path.exists(p[0]) for p in plan if os.path.splitext(p[0])[1].lower() != '.html')
    print(f'written {len(plan)} pages; broken links {broken}; originals left {left}; quarantine {Q}')


def do_txt(A, jobs, shared, go, Q):
    plan, skipped, thin = [], [], []
    for src, rep, d, stem, fdirs in jobs:
        new = os.path.join(d, stem + '.txt')
        if os.path.exists(new):
            skipped.append(new)
            continue
        text = open(rep, encoding='utf-8').read()
        body = [l for l in text.split('\n')[1:] if l.strip() and not l.startswith('作者')]
        if not any(len(l.strip()) >= 5 for l in body):
            thin.append(os.path.relpath(src, A))
        plan.append((src, new, fdirs, text))
    print(f'pages {len(plan)} | _files folders to quarantine {sum(len(p[2]) for p in plan) - len(shared)} | shared (copied) '
          f'{len(shared)} | skipped (txt name exists) {len(skipped)} | stories with almost no text {len(thin)}')
    for s in skipped:
        print('   SKIP', os.path.relpath(s, A))
    for s in thin[:20]:
        print('   THIN', s)
    if not go:
        print('dry run; add --go --quarantine <new dir>')
        return
    assert Q and not os.path.exists(Q)
    os.makedirs(Q)
    log = open(os.path.join(Q, 'replaced.tsv'), 'w', encoding='utf-8')
    for src, new, fdirs, text in plan:
        for p in [src] + fdirs:
            dst = os.path.join(Q, os.path.relpath(p, A))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            (shutil.copytree(p, dst) if p in shared else shutil.move(p, dst))
        assert not os.path.exists(new), new
        open(new, 'w', encoding='utf-8', newline='\n').write(text if text.endswith('\n') else text + '\n')
        log.write(f'{os.path.relpath(src, A)}\t{os.path.relpath(new, A)}\n')
    left = sum(os.path.exists(p[0]) for p in plan)
    print(f'written {len(plan)} txt; originals left {left}; quarantine {Q}')


if __name__ == '__main__':
    main()
