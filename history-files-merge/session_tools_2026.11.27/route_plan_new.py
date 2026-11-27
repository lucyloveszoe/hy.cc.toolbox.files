"""READ-ONLY routing plan for the pages of new layout-A roots (PROCESSING_LOGIC 6.1), html and txt alike.

    python3 route_plan_new.py <out.tsv> <root> [<root> ...]

Per summary row with an output: title (source page name, board footer stripped), body (visible text), forum board
(from the '◎『 … 』' footer of the source page name), keyword scores with the route_topics.py region table and
thresholds (title x6, address field x6, body x1; confident = best >= 8 and >= 2x second, ...). Traditional text is
converted to simplified first with the macOS ICU transform 'Traditional-Simplified' (osascript, no network).
Columns: root, page, output, board, title, kw_target, kw_basis, top_scores.
"""
import csv
import html
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
src = open(os.path.join(PROJ, 'session_tools_2026.11.19', 'route_topics.py'), encoding='utf-8').read().split('\n')
ns = {'re': re}
exec('\n'.join(src[25:64]), ns)          # kw(), REG, TAG, TAGRE, FIELD (lines 26-64; do not shift them)
REG, TAG, TAGRE, FIELD = ns['REG'], ns['TAG'], ns['TAGRE'], ns['FIELD']
BOARD = re.compile(r'◎『\s*([^』]*?)\s*』')
FOOTER = re.compile(r'\s*-\s*◎『.*$')


def keyword_route(title, body):            # same rules as route_topics.keyword_route
    sc = {}
    fld = ' '.join(FIELD.findall(body[:4000]))
    for reg, ws in REG.items():
        s = sum(6 * title.count(w) + 6 * fld.count(w) + body.count(w) for w in ws)
        if s:
            sc[reg] = s
    m = TAGRE.search(title)
    tag = TAG[m.group(1)] if m else None
    if not sc:
        return (tag, 'tag-only', sc) if tag else (None, 'no-clue', sc)
    ranked = sorted(sc.items(), key=lambda x: -x[1])
    best, bs = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if bs >= 8 and bs >= 2 * second:
        return best, 'keyword', sc
    if tag and tag in sc and sc[tag] >= max(3, 0.5 * bs):
        return tag, 'keyword+tag', sc
    if bs >= 4 and second == 0:
        return best, 'keyword-weak', sc
    if bs >= 4 and bs >= 1.5 * second:
        return best, 'keyword-lead', sc
    return None, 'unsure', sc


def t2s(texts):
    sep = '\n␞\n'
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'in.txt')
        open(p, 'w', encoding='utf-8').write(sep.join(texts))
        js = ('ObjC.import("Foundation"); var s=$.NSString.stringWithContentsOfFileEncodingError("%s",4,null);'
              's.stringByApplyingTransformReverse("Traditional-Simplified",false).js' % p)
        out = subprocess.run(['osascript', '-l', 'JavaScript', '-e', js], capture_output=True, text=True, check=True).stdout
    res = out.rstrip('\n').split(sep)
    assert len(res) == len(texts), (len(res), len(texts))
    return res


def visible(p):
    t = open(p, encoding='utf-8', errors='replace').read()
    if p.endswith('.html'):
        t = re.sub(r'(?is)<head.*?</head>|<h1.*?</h1>|<h3>.*?</h3>', '', t)
        t = html.unescape(re.sub(r'<[^>]+>', '\n', t))
    return t


def main():
    out, roots = sys.argv[1], [os.path.abspath(r) for r in sys.argv[2:]]
    recs = []
    for root in roots:
        name = os.path.basename(root)
        for r in csv.DictReader(open(os.path.join(root, f'{name}_summary.csv'), encoding='utf-8-sig', newline='')):
            o = r.get('output') or ''
            if not o:
                continue
            p = os.path.normpath(os.path.join(root, o))
            if not os.path.isfile(p) or not p.startswith(root):     # rows repointed to a kept page elsewhere
                continue
            pg = os.path.basename(r['page'])
            m = BOARD.search(pg)
            title = FOOTER.sub('', os.path.splitext(pg)[0]).strip()
            recs.append(dict(root=name, page=r['page'], output=o, board=m.group(1) if m else '', title=title,
                             body=visible(p)))
    seen = set()
    uniq = []
    for x in recs:                        # one decision per output file (a page may have several rows)
        k = (x['root'], x['output'])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    conv = t2s([x['title'] + '\n' + x['body'] for x in uniq])
    for x, c in zip(uniq, conv):
        title, _, body = c.partition('\n')
        x['kw_target'], x['kw_basis'], sc = keyword_route(title, body)
        x['top'] = ';'.join(f'{k}:{v}' for k, v in sorted(sc.items(), key=lambda kv: -kv[1])[:3])
    with open(out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('root\tpage\toutput\tboard\ttitle\tkw_target\tkw_basis\ttop_scores\n')
        for x in uniq:
            fh.write('\t'.join([x['root'], x['page'], x['output'], x['board'], x['title'], x['kw_target'] or '',
                                x['kw_basis'], x['top']]) + '\n')
    print('pages', len(uniq))


if __name__ == '__main__':
    main()
