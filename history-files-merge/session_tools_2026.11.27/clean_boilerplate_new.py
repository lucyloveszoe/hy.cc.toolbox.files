"""Fixed-text forum boilerplate in new layout-A roots (PROCESSING_LOGIC 4.4.3.4): dry run by default, --go to write.

    python3 -I clean_boilerplate_new.py <root> [<root> ...] [--go]

Works on the text nodes of reports/**/*.html and on lines of txt/**/*.txt. A text node / line is removed when it is:
  * a reply-to-see placeholder: 以下内容需要回复才能看到 / 以下内容跟帖回复才能看到
  * the rating block: 本帖最近评分记录 + the rating lines right after it (`<who> 经验|威望|金钱|… +N [text] YYYY-M-D H:MM`)
  * the paid-thread notice: 本主题需向作者支付…才能浏览 / 售价(现金): N 军币 / 已购买人数: N (记录) / 购买主题 (also one-line form)
  * an edit stamp without brackets: 由 <who> 最後編輯於 <date> <time>
  * forum disclaimers / copyright lines: 相片內容可能涉及不雅！…請你立即離開！ / 本文內容圖片屬男人頌論壇所有,轉載必究 /
    歡迎光臨“男人頌”論壇 songmen.cc/bbs/; 上海龙凤 site lines (收藏 分享, 【赠送金币】…, 上海龙凤特别声明： + 凡在龙凤特荐中的MM…)
Author thread index (FDZone boa9114 posts): from his signature '希望得到大家的紅心 這樣才能更造福大家' or from a '貼圖' line
directly followed by a 'DD-MM-YYYY' line to the end of the
post (html: up to </section>; txt: to the end of the file) - his list of links to his other threads; skipped if the range
holds an <img>.
A maichun hidden-font remnant inside txt (`font style="font-size:0px…">bbs.maichun.org<garbage>`) is cut out.
Afterwards <br> runs are collapsed (3+ -> 2, none before </section>), txt blank runs -> one. Counts per pattern."""
import collections
import html
import os
import re
import sys

ROOTS = [a for a in sys.argv[1:] if a != '--go']
GO = '--go' in sys.argv
DATE = r'\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?'
PAT = {
    'reply placeholder': re.compile(r'以下内容(?:需要|跟帖)回复才能看到'),
    'rating header': re.compile(r'本帖最近(?:评分记录|評分記錄)'),    # traditional form added 2026-11-28 (2010 mc)
    'paid notice': re.compile(r'(?:购买主题\s*)?(?:已购买人数\s*:?\s*\d+\s*\(?记录\)?\s*)?本主题需向作者支付[^\n]{0,20}?才能浏览'
                              r'|售价\(现金\):\s*\d+\s*\S{1,3}|已购买人数:\s*\d+\s*\(记录\)|购买主题'),
    'edit stamp': re.compile(r'由\s*\S{1,30}\s*最[後后][編编][輯辑]於\s*\d{1,4}-\d{1,2}-\d{1,4}\s+\d{1,2}:\d{2}(?:\s*[AP]M)?'),
    'disclaimer': re.compile(r'相片內容可能涉及不雅！令人反感！及廢話連篇！如閣下不同意話題內容或閣下是道德主義者\s*請你立即離開！'
                             r'|本文內容圖片屬男人頌論壇所有,轉載必究|歡迎光臨“男人頌”論壇\s*songmen\.cc/bbs/'
                             r'|收藏\s*分享|【赠送金币】：点击发帖评价，即送金币|上海龙凤特别声明：'
                             r'|凡在龙凤特荐中的MM，照片完全真实，无PS,服务到位，不虚报，待人热情,态度好'),
}
RATING = re.compile(r'\S{1,20}\s+(?:经验|威望|金钱|贡献|军币|金币|爽幣|积分)\s*[+-]\s*\d+(?:\s+[^\n]{0,80}?)?\s+' + DATE)
DATE_AFTER = re.compile(r'(?:\s|<[^>]{0,200}>){0,12}\d{2}-\d{2}-\d{4}')


def cut_index(body, c):
    """boa9114 signature '希望得到大家的紅心…' or a '貼圖' text node directly followed by a DD-MM-YYYY text node
    -> drop up to the next </section> (only when no <img> lies in that range)."""
    out, pos = [], 0
    while True:
        cand = [(x, mark) for mark in ('希望得到大家的紅心', '貼圖') for x in [body.find(mark, pos)] if x >= 0]
        if not cand:
            break
        i, mark = min(cand)
        j = body.find('</section>', i)
        ok_start = mark == '希望得到大家的紅心' or DATE_AFTER.match(body, i + len(mark))
        if j < 0 or not ok_start or '<img' in body[i:j].lower():
            out.append(body[pos:i + len(mark)])
            pos = i + len(mark)
            continue
        k = i                                     # step back over the tags / <br> right before '貼圖'
        while True:
            m = re.search(r'(?:<[^>]{0,200}>|\s)$', body[max(pos, k - 210):k])
            if not m or k - len(m.group(0)) < pos:
                break
            k -= len(m.group(0))
        out.append(body[pos:k])
        c['author thread index'] += 1
        pos = j
    out.append(body[pos:])
    return ''.join(out)


INDEX_TXT = re.compile(r'\n(?:希望得到大家的紅心[^\n]*|貼圖\n\d{2}-\d{2}-\d{4})\n.*\Z', re.S)
MAICHUN = re.compile(r'(?:\?u>[^\s?]{0,12}\?)?font style="font-size:0px[^"]*">bbs\.maichun\.org[!-~]*')


def clean_units(units, c):
    """units: list of text strings (text nodes or lines). Returns new list; whole-unit removals only."""
    out, in_rating = [], False
    for u in units:
        s = u.strip()
        if not s:
            out.append(u)
            continue
        if in_rating and RATING.fullmatch(s):
            c['rating line'] += 1
            out.append('')
            continue
        in_rating = False
        hit = next((k for k, p in PAT.items() if p.fullmatch(s)), None)
        if hit:
            c[hit] += 1
            in_rating = hit == 'rating header'
            out.append('')
        else:
            out.append(u)
    return out


def main():
    tot = collections.Counter()
    changed = []
    for R in ROOTS:
        for d, _, fs in os.walk(R):
            for f in fs:
                p = os.path.join(d, f)
                isH = f.endswith('.html') and os.sep + 'reports' + os.sep in p
                isT = f.endswith('.txt') and os.sep + 'txt' + os.sep in p
                if not (isH or isT):
                    continue
                o = open(p, encoding='utf-8').read()
                c = collections.Counter()
                if isH:
                    head, sep, body = o.partition('<body>')
                    parts = re.split(r'(<[^>]*>)', body)
                    idx = [i for i, x in enumerate(parts) if not x.startswith('<')]
                    texts = [html.unescape(parts[i]) for i in idx]
                    new = clean_units(texts, c)
                    for i, old, nw in zip(idx, texts, new):
                        if nw != old:
                            parts[i] = html.escape(nw, quote=True)
                    body = ''.join(parts)
                    body = cut_index(body, c)
                    body = re.sub(r'(?:<br\s*/?>\s*){3,}', '<br>\n<br>\n', body)
                    body = re.sub(r'(?:<br\s*/?>\s*)+(?=</section>)', '', body)
                    t = head + sep + body
                else:
                    t, k = MAICHUN.subn('', o)
                    c['maichun remnant'] += k
                    t, k = INDEX_TXT.subn('', t)
                    c['author thread index'] += k
                    lines = clean_units(t.split('\n'), c)
                    t = '\n'.join(x.rstrip() for x in lines)
                    t = re.sub(r'\n{3,}', '\n\n', t)
                if t != o and c:
                    changed.append((p, c))
                    tot.update(c)
                    if GO:
                        open(p, 'w', encoding='utf-8', newline='').write(t)
    for p, c in changed:
        print(os.path.relpath(p, os.path.commonpath(ROOTS) if len(ROOTS) > 1 else ROOTS[0])[:90], dict(c))
    print('files', len(changed), dict(tot), '(written)' if GO else '(dry run)')


if __name__ == '__main__':
    main()
