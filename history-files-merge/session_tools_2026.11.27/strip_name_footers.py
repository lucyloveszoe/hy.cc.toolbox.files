"""Peel forum board footers (and a leading 【新提醒】) off page / story names in new layout-A roots (PROCESSING_LOGIC 4.4.3.5, 4.5).

    python3 -I strip_name_footers.py <root> [<root> ...]                      dry run
    python3 -I strip_name_footers.py <root> [<root> ...] --go --backup-dir D  act (D must not exist)

For reports/**/*.html and txt/**/*.txt: the footers below are peeled off the file name in a loop; the same footers are
peeled off <title>/<h1> (html) or the first line (txt). A leading 【新提醒】 is dropped from the file name only.
Clash (NFC, lower case, no whitespace) with a file in the same folder or another rename -> old name kept, listed.
The 'output' cells of <root>_summary.csv are repointed; changed files and CSVs are backed up first.
Add new footers to FOOTERS (anchored at the end)."""
import csv
import html
import io
import os
import re
import shutil
import sys
import unicodedata

FOOTERS = [re.compile(p) for p in (
    r'\s*-\s*推油、足浴、FL及其他\s*-\s*爱上海同城对对碰交友网\s*-\s*Powered by Discuz!$',
    r'\s*-\s*【足浴发廊】\s*-\s*上海龙凤\s*_上海楼凤$',
    r'\s*-\s*优惠场所专区\s*-\s*上海419_上海龙凤_爱上海$',
    r'\s*-\s*☆[^☆]{1,12}☆\s*-\s*☆[^☆]{1,12}☆\s*-\s*ＭＣ军团（招財進寶）\[关闭注册\].*$',
    r'\s*-\s*上 海 原 创 信 息\s*-\s*★ 上 海 军 区 ★\s*-\s*【买春堂】.*$',
    r'\s*买春堂\s*-\s*Powered by Discuz!$',
    r'\s*韓國夜遊\s*-$',
    # 2026-11-28 (data/shlf): 爱上海 boards incl. hand-added copy markers (`交友网2`, `Discuz!b`, `Discuzb!`, `gDiscuz!`);
    # a `第N页` before the board is a real page number and stays
    r'\s*-\s*(?:推油、足浴、FL及其他|桑拿会所体验区|女生自荐区|女生交流区|版主推荐区)\s*-\s*爱上海同城对对碰交友网\s*\d?\s*'
    r'(?:-\s*Powered by [a-z]?Discuz[a-z0-9]?!?[a-z0-9]?)?$',          # title lines often lack the Powered-by part
    r'\s*-\s*【寻凤阁[^】]{2,8}】\s*-\s*寻凤阁(?:\s*-\s*(?:Powered by Discuz!|www\.hhxx\.us))?$',
    r'\s*-\s*(?:女生自荐区)\s*-\s*爱上海同城对对碰交友网$',
    r'\s*-\s*『试发新贴处』\s*-\s*上海金屋藏娇\s*上海最好的交友论坛$',
    r'\s*-\s*【[^】]{2,6}】\s*-\s*上海龙凤\s+上海楼凤\s+上海桑拿$',
    r'\s*-\s*Powered by Discuz!$',
)]
HEADS = [re.compile(p) for p in (     # board heads, peeled like the footers (2026-11-28: 春风楼)
    r'^【[\s\u3000]*】\s*',          # empty bracket head (爱上海/寻凤阁 sticky-post marker)
    r'^上海春风楼同城交友论坛,[^,]{1,20}\([^)]{2,6}\),[^,]{1,20}\([^)]{2,6}\),\s*',
)]
HEAD = '【新提醒】'


def key(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', s).lower())


def peel(s):
    while True:
        for f in FOOTERS + HEADS:
            n = f.sub('', s)
            if n != s:
                s = n.rstrip()
                break
        else:
            return s


def main():
    args = sys.argv[1:]
    go = '--go' in args
    bdir = args[args.index('--backup-dir') + 1] if '--backup-dir' in args else None
    roots = [os.path.abspath(a) for a in args if not a.startswith('--') and a != bdir]
    if go:
        assert bdir and not os.path.exists(bdir), 'need a new --backup-dir'
        os.makedirs(bdir)
    total, clashes = 0, []
    for R in roots:
        ren = {}
        for sub, ext in (('reports', '.html'), ('txt', '.txt')):
            for d, _, fs in os.walk(os.path.join(R, sub)):
                taken = {key(f) for f in fs}
                for f in sorted(fs):
                    if not f.endswith(ext):
                        continue
                    st = f[:-len(ext)]
                    n = peel(st)
                    while n.startswith(HEAD):
                        n = n[len(HEAD):].lstrip()
                    if n == st or not n:
                        continue
                    if key(n + ext) in taken:
                        clashes.append(os.path.join(d, f))
                        continue
                    taken.discard(key(f))
                    taken.add(key(n + ext))
                    ren[os.path.join(d, f)] = os.path.join(d, n + ext)
        for old, new in sorted(ren.items()):
            print('  ', os.path.relpath(old, R)[:70], '->', os.path.basename(new)[:60])
        total += len(ren)
        if not go:
            continue
        for old, new in ren.items():
            dst = os.path.join(bdir, os.path.relpath(old, os.path.dirname(R)))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(old, dst)
            t = open(old, encoding='utf-8').read()
            if old.endswith('.html'):
                t = re.sub(r'(<title>)([^<]*)(</title>)',
                           lambda m: m.group(1) + html.escape(peel(html.unescape(m.group(2))), quote=False) + m.group(3), t, count=1)
                t = re.sub(r'(<h1[^>]*>)([^<]*)(</h1>)',
                           lambda m: m.group(1) + html.escape(peel(html.unescape(m.group(2))), quote=False) + m.group(3), t, count=1)
            else:
                lines = t.split('\n')
                lines[0] = peel(lines[0])
                t = '\n'.join(lines)
            open(new, 'w', encoding='utf-8').write(t)
            os.remove(old)
        name = os.path.basename(R)
        sp = os.path.join(R, f'{name}_summary.csv')
        data = open(sp, 'rb').read()
        bom = data.startswith(b'\xef\xbb\xbf')
        text = data.decode('utf-8-sig')
        eol = '\r\n' if '\r\n' in text else '\n'
        rows = list(csv.reader(io.StringIO(text, newline='')))
        oi = rows[0].index('output')
        n = 0
        for r in rows[1:]:
            if r[oi]:
                q = os.path.normpath(os.path.join(R, r[oi]))
                if q in ren:
                    r[oi] = os.path.relpath(ren[q], R)
                    n += 1
        if n:
            shutil.copy2(sp, os.path.join(bdir, os.path.basename(sp)))
            buf = io.StringIO()
            csv.writer(buf, lineterminator=eol).writerows(rows)
            open(sp, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8'))
        left = [o for o in ren if os.path.exists(o)]
        print(f'{name}: renamed {len(ren)}, summary cells {n}, old paths left {len(left)}')
    for c in clashes:
        print('   CLASH kept old name:', c)
    print('total', total, 'clashes', len(clashes), '(written)' if go else '(dry run)')


if __name__ == '__main__':
    main()
