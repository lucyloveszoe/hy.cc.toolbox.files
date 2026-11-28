"""READ-ONLY: propose a target for every page of an existing flat library root (e.g. merges/mcjt-total).

    python3 -I route_existing_root.py <plan.tsv from route_plan_new.py> <root dir> <out.tsv>

Order (first hit wins; PROCESSING_LOGIC 6.1.3):
  1 series / contest keyword in the title     -> topic root (SERIES)
  2 place word in the (simplified) title      -> region root; words followed by an origin noun (四川妹, 东北姑娘) and
                                                 ambiguous words are ignored; words of 2+ regions -> the one the body
                                                 score confirms, else held
  3 board tag in the title ([桂总阅], 【沪参阅】, 亚总/美总/欧总) -> region, unless the body is confident for another
  4 body keyword score confident (route_plan_new kw_basis keyword / keyword+tag)
  5 genre / board topic keyword in the title  -> topic root (GENRE)
  else stays. Output: output, title, target (root path under html/ or ''), basis, top_scores."""
import csv
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(os.path.dirname(HERE), 'session_tools_2026.11.19', 'route_topics.py'), encoding='utf-8').read().split('\n')
ns = {'re': re}
exec('\n'.join(src[25:64]), ns)
REG, TAG, TAGRE = ns['REG'], ns['TAG'], ns['TAGRE']

ROOT = {'川渝': 'locations/川渝精品收藏馆', '广东': 'locations/广东', '上海': 'locations/上海', '山东': 'locations/山东军区冬瀌聚丽',
        '东北': 'locations/东北军区藏经阁', '江浙': 'locations/江苏军区', '安徽': 'locations/安徽军区', '河南': 'locations/河南军区昔日传奇',
        '新疆': 'locations/新疆', '港澳': 'locations/港澳', '京津': 'locations/北京军区歌舞升平', '湖南': 'locations/湖南',
        '湖北': 'locations/湖北', '云南': 'locations/云南', '贵州': 'locations/贵州', '陕西': 'locations/陕西', '山西': 'locations/山西',
        '甘肃': 'locations/甘肃', '河北': 'locations/河北', '福建': 'locations/福建', '海南': 'locations/海南', '江西': 'locations/江西',
        '广西': 'locations/广西', '台湾': 'locations/台湾', '韩国': 'locations/海外', '日本': 'locations/海外', '美国': 'locations/海外',
        '俄罗斯': 'locations/海外', '其他海外': 'locations/海外', '欧非': 'locations/欧非'}
EUAF = '英国 伦敦 法国 巴黎 德国 柏林 欧洲 非洲 多哥 法兰克福 慕尼黑 阿姆斯特丹 布拉格 维也纳 米兰 罗马 巴塞罗那 马德里 欧总阅 FKK 荷兰 乌克兰 波兰 东欧'.split()
SUB = {'徐州': 'locations/徐州', '天津': 'locations/天津'}       # title word -> own root inside a region
AMBIG = set('长安 南海 沙田 白云 南山 天河 朝阳区 大兴 通州 昌平 房山 南京路 川沙 澳门路 延安西路 韩庄 龙华 远东 中山公园 江北区'.split())
ORIGIN = re.compile(r'^(?:妹|女|姐|婆|嫂|少妇|MM|mm|美女|小姐|辣妹|姑娘|妞|籍|靓女|靓妹|大奶妹|小妹|美眉|人)')
SERIES = [(r'十里洋场杯', 'locations/十里洋场'), (r'上海狼在俄罗斯', 'topics/Great_上海狼在俄罗斯'), (r'大盗贼', 'topics/大盗贼'),
          (r'沈公子|点点派', 'topics/Great_沈公子'), (r'老陳系列|老陈系列', 'topics/老陳系列')]
GENRE = [(r'独发私密|首发私密|独发密区|独发秘区|MC私密|同发密营|密营|密总阅', 'topics/私密图文'), (r'学生妹', 'topics/学生妹'),
         (r'母女', 'topics/母女')]
BOARD = [(re.compile(r'[\[【(（](?:亚总|亚副)'), '其他海外'), (re.compile(r'[\[【(（](?:美总|美副)'), '美国'),
         (re.compile(r'[\[【(（](?:欧总|欧副)'), '欧非'), (re.compile(r'^\(澳門\)|^\(香港\)|^（澳門）'), '港澳')]


def t2s(texts):
    sep = '\n␞\n'
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'in.txt')
        open(p, 'w', encoding='utf-8').write(sep.join(texts))
        js = ('ObjC.import("Foundation"); var s=$.NSString.stringWithContentsOfFileEncodingError("%s",4,null);'
              's.stringByApplyingTransformReverse("Traditional-Simplified",false).js' % p)
        out = subprocess.run(['osascript', '-l', 'JavaScript', '-e', js], capture_output=True, text=True, check=True).stdout
    res = out.rstrip('\n').split(sep)
    assert len(res) == len(texts)
    return res


def title_regions(t):
    hits = {}
    for reg, ws in REG.items():
        for w in ws:
            if w in AMBIG:
                continue
            for m in re.finditer(re.escape(w), t):
                if ORIGIN.match(t[m.end():]):
                    continue
                r = '欧非' if (reg == '其他海外' and w in EUAF) else reg
                hits.setdefault(r, []).append(w)
    for w in EUAF:
        if w in t and not ORIGIN.match(t[t.find(w) + len(w):]):
            hits.setdefault('欧非', []).append(w)
    if '欧非' in hits and '其他海外' in hits and not (set(hits['其他海外']) - set(EUAF)):
        del hits['其他海外']
    return hits


def scores(s):
    d = {}
    for x in (s or '').split(';'):
        if ':' in x:
            k, v = x.split(':')
            d[k] = int(v)
    return d


def main():
    plan, root, out = sys.argv[1:4]
    rows = list(csv.DictReader(open(plan, encoding='utf-8'), delimiter='\t'))
    titles = [os.path.splitext(os.path.basename(r['output']))[0] for r in rows]
    simp = t2s(titles)
    res = []
    for r, t0, t in zip(rows, titles, simp):
        sc = scores(r['top_scores'])
        best = r['kw_target'] if r['kw_basis'] in ('keyword', 'keyword+tag') else None
        tgt, basis = '', ''
        for pat, dst in SERIES:
            if re.search(pat, t) or re.search(pat, t0):
                tgt, basis = dst, f'series ({pat})'
                break
        if not tgt:
            hits = title_regions(t)
            if len(hits) == 1:
                reg = next(iter(hits))
                tgt, basis = ROOT.get(reg, ''), f"title ({','.join(sorted(set(hits[reg])))})"
                if not tgt:
                    basis = f'held: no root for {reg}'
            elif len(hits) > 1:
                conf = [g for g in hits if g == best or (sc.get(g, 0) and sc.get(g, 0) == max(sc.values()))]
                if len(conf) == 1 and ROOT.get(conf[0]):
                    tgt, basis = ROOT[conf[0]], f"title+body ({conf[0]} of {'/'.join(hits)})"
                else:
                    basis = f"held: title names {'/'.join(hits)}"
            if tgt:
                for w, d in SUB.items():
                    if w in t:
                        tgt = d
        if not tgt and not basis.startswith('held'):
            m = TAGRE.search(t)
            reg = TAG[m.group(1)] if m else next((g for p, g in BOARD if p.search(t0) or p.search(t)), None)
            if reg and (best in (None, reg)) and ROOT.get(reg):
                tgt, basis = ROOT[reg], f'board tag ({reg})'
        if not tgt and not basis.startswith('held') and best and ROOT.get(best):
            tgt, basis = ROOT[best], f"body {r['kw_basis']}"
        if not tgt:
            for pat, dst in GENRE:
                if re.search(pat, t):
                    tgt, basis = dst, f'genre ({pat})' + (f'; {basis}' if basis else '')
                    break
        res.append((r['output'], t0, tgt, basis or f"stays: {r['kw_basis']}", r['top_scores']))
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write('output\ttitle\ttarget\tbasis\ttop_scores\n')
        for x in res:
            fh.write('\t'.join(x) + '\n')
    c = {}
    for x in res:
        c[x[2] or '(stays)'] = c.get(x[2] or '(stays)', 0) + 1
    for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
        print(f'{v:4} {k}')


if __name__ == '__main__':
    main()
