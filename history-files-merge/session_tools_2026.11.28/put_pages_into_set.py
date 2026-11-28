"""Put processed report pages (layout A, scratch) into a finished set's html/ (PROCESSING_LOGIC 8), add or replace.

    python3 put_pages_into_set.py <plan.tsv>                                   dry run
    python3 put_pages_into_set.py <plan.tsv> --go --quarantine Q               act (Q must not exist)

plan.tsv (no header), one row per page:
    new_page <TAB> set_html <TAB> page_dir <TAB> img_dir <TAB> target_name <TAB> add|replace [<TAB> title]
  set_html    the set's html/ folder (images already anywhere under it are reused by SHA-256)
  page_dir    folder the page goes to (under set_html)
  img_dir     folder new pictures go to (e.g. <set>/html/images/<source>)
  target_name file name of the page (replace: the existing page of that name is moved to Q first)
Per picture of the new page (<img src> resolved against the new page): same SHA-256 as a file under set_html ->
link that file; else copied into img_dir under its own name (NFC + lower case + no-whitespace clash with a different
file -> '<n>__' prefix, n = 2, 3, ...). Links are written relative, html.escape'd, never percent-encoded; <title>/<h1>
become the title column (default: the target name's stem). replace: pictures only the old page used and the new page does not link go to Q too
(listed; each must have a byte-identical copy linked by the new page, else the row is refused).
Checks after --go: every <img src> of every written page resolves; Q holds only moved files; removed_to_kept.tsv in Q.
Refuses: target page exists (add), missing new picture, name > 240 bytes.
"""
import hashlib
import html
import os
import re
import shutil
import sys
import unicodedata

IMG_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)
key = lambda n: re.sub(r'\s+', '', unicodedata.normalize('NFC', n).lower())


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def srcs(page):
    t = open(page, encoding='utf-8').read()
    return t, [(m, os.path.normpath(os.path.join(os.path.dirname(page), html.unescape(m.group(2)))))
               for m in IMG_RE.finditer(t) if not m.group(2).startswith(('http:', 'https:', 'data:'))]


def main():
    a = sys.argv[1:]
    go = '--go' in a
    Q = a[a.index('--quarantine') + 1] if '--quarantine' in a else None
    rows = [l.split('\t') for l in open(a[0], encoding='utf-8').read().splitlines() if l.strip()]
    if go:
        assert Q and not os.path.exists(Q), 'need a new --quarantine dir'
        os.makedirs(Q)
    index = {}      # set_html -> {size: [paths]} built lazily; sha cache
    shac = {}

    def find_same(set_html, p):
        if set_html not in index:
            d = {}
            for dp, _, fs in os.walk(set_html):
                for f in fs:
                    if os.path.splitext(f)[1].lower() in ('.jpg', '.jpeg', '.png', '.gif', '.bmp'):
                        q = os.path.join(dp, f); d.setdefault(os.path.getsize(q), []).append(q)
            index[set_html] = d
        if p not in shac:
            shac[p] = sha(p)
        s = shac[p]
        for q in index[set_html].get(os.path.getsize(p), []):
            if q not in shac:
                shac[q] = sha(q)
            if shac[q] == s:
                return q
        return None

    planned_names = {}
    log, n_copy, n_link, n_q = [], 0, 0, 0
    for row in rows:
        new_page, set_html, page_dir, img_dir, name, mode = row[:6]
        title = row[6] if len(row) > 6 and row[6] else os.path.splitext(name)[0]
        assert len(name.encode()) <= 240, name
        target = os.path.join(page_dir, name)
        exists = os.path.exists(target)
        assert (mode == 'replace') == exists, f'{mode} but target exists={exists}: {target}'
        t, imgs = srcs(new_page)
        old_imgs = srcs(target)[1] if exists else []
        new_links, copies = {}, []
        for m, p in imgs:
            assert os.path.isfile(p), f'missing picture {p} of {new_page}'
            if p in new_links:
                continue
            same = find_same(set_html, p)
            if same:
                new_links[p] = same; n_link += 1
                continue
            base = os.path.basename(p); cand, k = base, 1
            used = planned_names.setdefault(img_dir, {key(x): os.path.join(img_dir, x) for x in (os.listdir(img_dir) if os.path.isdir(img_dir) else [])})
            while key(cand) in used:
                k += 1; cand = f'{k}__{base}'
            dst = os.path.join(img_dir, cand); used[key(cand)] = dst
            new_links[p] = dst; copies.append((p, dst)); n_copy += 1
            index[set_html].setdefault(os.path.getsize(p), []).append(dst); shac[dst] = shac[p]
        keep_paths = set(new_links.values())
        drop_imgs = []
        if exists:
            others = set()
            for dp, _, fs in os.walk(set_html):
                for f in fs:
                    q = os.path.join(dp, f)
                    if f.endswith('.html') and q != target:
                        others.update(x for _, x in srcs(q)[1])
            for _, p in old_imgs:
                if p not in keep_paths and p not in others and os.path.exists(p) and p not in drop_imgs:
                    s = sha(p)
                    assert any(shac.get(x) == s for x in keep_paths), f'old picture {p} has no copy in the new page'
                    drop_imgs.append(p)
        stem = html.escape(title, quote=True)

        def rep(m):
            p = os.path.normpath(os.path.join(os.path.dirname(new_page), html.unescape(m.group(2))))
            if p not in new_links:
                return m.group(0)
            return m.group(1) + html.escape(os.path.relpath(new_links[p], page_dir), quote=True) + m.group(3)
        out = IMG_RE.sub(rep, t)
        out = re.sub(r'<title>.*?</title>', f'<title>{stem}</title>', out, count=1, flags=re.S)
        out = re.sub(r'<h1>.*?</h1>', f'<h1>{stem}</h1>', out, count=1, flags=re.S)
        log.append((new_page, target, mode, len(imgs), len(copies), len(drop_imgs)))
        if go:
            if exists:
                qd = os.path.join(Q, os.path.relpath(target, os.path.dirname(set_html.rstrip('/'))))
                os.makedirs(os.path.dirname(qd), exist_ok=True); shutil.move(target, qd); n_q += 1
                for p in drop_imgs:
                    qd = os.path.join(Q, os.path.relpath(p, os.path.dirname(set_html.rstrip('/'))))
                    os.makedirs(os.path.dirname(qd), exist_ok=True); shutil.move(p, qd); n_q += 1
            for p, dst in copies:
                assert not os.path.exists(dst), dst
                os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(p, dst)
                assert sha(dst) == shac[p], dst
            os.makedirs(page_dir, exist_ok=True)
            open(target, 'w', encoding='utf-8').write(out)
            _, chk = srcs(target)
            bad = [x for _, x in chk if not os.path.isfile(x)]
            assert not bad, (target, bad[:3])
    for r in log:
        print(f'{r[2]:7} imgs {r[3]:3} copied {r[4]:3} old-pics-to-Q {r[5]:2} | {os.path.basename(r[0])[:45]} -> {r[1][-70:]}')
    print(f'pages {len(log)} | pictures copied {n_copy}, linked to an existing identical file {n_link} | '
          f'moved to quarantine {n_q}', '(written)' if go else '(dry run)')
    if go:
        with open(os.path.join(Q, 'removed_to_kept.tsv'), 'w', encoding='utf-8') as w:
            for r in log:
                if r[2] == 'replace':
                    w.write(f'{r[1]}\t{r[1]}\t(replaced by {r[0]})\n')


if __name__ == '__main__':
    main()
