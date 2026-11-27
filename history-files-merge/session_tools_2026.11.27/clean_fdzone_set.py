"""Clean a layout-A root made by process_html_posts.py from FDZone-Forum saved pages (PROCESSING_LOGIC 4.4 / 4.5).

    python3 clean_fdzone_set.py <root> [<root> ...]          dry run
    python3 clean_fdzone_set.py <root> [<root> ...] --go     in place (only on roots this run generated)

1. Signature tails of reposters (fixed text, removed in html text and txt):
     A  別忘了給 [image missing | <img>] 呀! [THX!]
     B  如果你們喜歡的話,就順便按一下右上角的"[image missing | <img>]"支持我一下!你的支持是我的動力,以后我會找更好的給大家分享!!
   Free-written variants (別忘了給心心呀!, 如果多過30個心…) are post text and stay.
   An <img> inside a block is the forum's thanks button: its link goes with the block; an image file no page links
   any more is deleted and its manifest row gets a blank output + ' [output file no longer in data.done: thanks-button image removed with signature]'.
2. html text nodes: &#N; / &#xN; -> character; 3+ <br> -> 2; <br> runs before </section> dropped.
   txt: '[image missing]' lines removed; 3+ blank lines -> 1.
3. File names (html + txt): board footer ' - ◎『 … 』[ - ◎『 成人無制限聊天 』 - FDZone-Forum]' stripped; a clash
   (NFC, lower case, no whitespace) keeps the old name. Summary 'output' follows; images_copied recounted.
CSV BOM/EOL/column order kept.
"""
import csv
import html
import io
import os
import re
import sys
import unicodedata

SEP = r'(?:\s|<br\s*/?>)*'
INNER = r'(\[image missing\]|<img[^>]*>)?'
A_HTML = re.compile(r'別忘了給' + SEP + INNER + SEP + r'呀!(?:' + SEP + r'THX!)?')
B_HTML = re.compile(r'如果你們喜歡的話,就順便按一下右上角的(?:&quot;|")' + SEP + INNER + SEP + r'(?:&quot;|")' + SEP
                    + r'支持我一下!你的支持是我的動力,以后我會找更好' + SEP + r'的給大家分享!!')
FOOTER = re.compile(r'\s*-\s*◎『.*$')
ENT = re.compile(r'&#(\d+);|&#x([0-9a-fA-F]+);')
IMG_SRC = re.compile(r'<img[^>]*?\ssrc="([^"]+)"', re.I)


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def ent_fix(text):
    parts = re.split(r'(<[^>]*>)', text)
    out = []
    for p in parts:
        if not p.startswith('<'):
            p = ENT.sub(lambda m: html.escape(chr(int(m.group(1)) if m.group(1) else int(m.group(2), 16)), quote=False), p)
        out.append(p)
    return ''.join(out)


def clean_html(t):
    n = 0
    removed_imgs = []

    def cut(m):
        nonlocal n
        n += 1
        if m.group(1) and m.group(1).startswith('<img'):
            removed_imgs.append(html.unescape(IMG_SRC.search(m.group(1)).group(1)))
        return ''
    head, sep, body = t.partition('<body')
    body = A_HTML.sub(cut, body)
    body = B_HTML.sub(cut, body)
    body = ent_fix(body)
    body = re.sub(r'(?:<br>\s*){3,}', '<br>\n<br>\n', body)
    body = re.sub(r'(?:\s*<br>)+\s*</section>', '</section>', body)
    return head + sep + body, n, removed_imgs


def clean_txt(t):
    n = 0

    def cut(m):
        nonlocal n
        n += 1
        return ''
    plain_sep = r'\s*'
    a = re.compile(r'別忘了給' + plain_sep + r'(?:\[image missing\])?' + plain_sep + r'呀!(?:' + plain_sep + r'THX!)?')
    b = re.compile(r'如果你們喜歡的話,就順便按一下右上角的"' + plain_sep + r'(?:\[image missing\])?' + plain_sep + r'"' + plain_sep
                   + r'支持我一下!你的支持是我的動力,以后我會找更好' + plain_sep + r'的給大家分享!!')
    t = b.sub(cut, a.sub(cut, t))
    t2 = re.sub(r'^[ \t]*\[image missing\][ \t]*\n?', '', t, flags=re.M)
    n += t.count('[image missing]') - t2.count('[image missing]')
    t2 = re.sub(r'\n{3,}', '\n\n', t2).rstrip('\n') + '\n'
    return t2, n


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


def run(root, go):
    name = os.path.basename(root.rstrip('/'))
    summ, man = os.path.join(root, f'{name}_summary.csv'), os.path.join(root, f'{name}_images_manifest.csv')
    stats = dict(blocks_html=0, blocks_txt=0, pages_changed=0, txt_changed=0, renamed=0, clash=0, img_deleted=0)
    candidates = set()
    for sub in ('reports', 'txt'):
        for d, _, fs in os.walk(os.path.join(root, sub)):
            for f in fs:
                p = os.path.join(d, f)
                if f.endswith('.html'):
                    t = open(p, encoding='utf-8').read()
                    new, n, imgs = clean_html(t)
                    stats['blocks_html'] += n
                    candidates.update(os.path.normpath(os.path.join(d, s)) for s in imgs)
                    if new != t:
                        stats['pages_changed'] += 1
                        if go:
                            open(p, 'w', encoding='utf-8').write(new)
                elif f.endswith('.txt'):
                    t = open(p, encoding='utf-8').read()
                    new, n = clean_txt(t)
                    stats['blocks_txt'] += n
                    if new != t:
                        stats['txt_changed'] += 1
                        if go:
                            open(p, 'w', encoding='utf-8').write(new)
    # images no page links any more (only those removed with a block)
    linked = set()
    for d, _, fs in os.walk(os.path.join(root, 'reports')):
        for f in fs:
            if f.endswith('.html'):
                p = os.path.join(d, f)
                t = open(p, encoding='utf-8').read()
                if not go:
                    t = clean_html(t)[0]
                linked.update(os.path.normpath(os.path.join(d, html.unescape(s))) for s in IMG_SRC.findall(t))
    dead = sorted(c for c in candidates if c not in linked and os.path.isfile(c))
    stats['img_deleted'] = len(dead)
    # renames
    renames = {}
    for sub in ('reports', 'txt'):
        for d, _, fs in os.walk(os.path.join(root, sub)):
            taken = {key(f) for f in fs}
            for f in sorted(fs):
                stem, ext = os.path.splitext(f)
                ns = FOOTER.sub('', stem).rstrip()
                if ns == stem or not ns:
                    continue
                nf = ns + ext
                if key(nf) in taken:
                    stats['clash'] += 1
                    print('   clash, kept:', f)
                    continue
                taken.discard(key(f))
                taken.add(key(nf))
                renames[os.path.join(d, f)] = os.path.join(d, nf)
    stats['renamed'] = len(renames)
    print(name, stats)
    if not go:
        return
    for c in dead:
        os.remove(c)
    for o, n in renames.items():
        os.rename(o, n)
    # summary
    rows, dump = load_csv(summ)
    h = rows[0]
    oi, ii = h.index('output'), h.index('images_copied')
    for r in rows[1:]:
        if len(r) <= oi or not r[oi]:
            continue
        p = os.path.normpath(os.path.join(root, r[oi]))
        if p in renames:
            p = renames[p]
            r[oi] = os.path.relpath(p, root)
        if p.endswith('.html') and os.path.isfile(p):
            t = open(p, encoding='utf-8').read()
            r[ii] = str(len({s for s in IMG_SRC.findall(t)}))
    open(summ, 'wb').write(dump(rows))
    # manifest
    rows, dump = load_csv(man)
    h = rows[0]
    oi, si = h.index('output'), h.index('status')
    deads = set(dead)
    for r in rows[1:]:
        if len(r) > oi and r[oi] and os.path.normpath(os.path.join(root, r[oi])) in deads:
            r[oi] = ''
            r[si] += ' [output file no longer in data.done: thanks-button image removed with signature]'
    open(man, 'wb').write(dump(rows))


if __name__ == '__main__':
    go = '--go' in sys.argv
    for r in [a for a in sys.argv[1:] if a != '--go']:
        run(os.path.abspath(r), go)
