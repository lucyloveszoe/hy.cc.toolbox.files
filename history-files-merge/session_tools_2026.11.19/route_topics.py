"""Split mc_merged.txt into topic files mc_<topic>.txt (+ manifests).  Usage: route_topics.py <out dir>
Priority per story: (1) series-topic folder it came from (own folder or any duplicate's folder),
(2) region folder, (3) keyword location score (PROCESSING_RULES 18: title x6, address field x6, body x1),
(4) otherwise 待定义.  Nothing is deleted; mc_merged.txt stays the master."""
import csv, os, re, sys, collections

T = os.environ.get('MC_T', '/Users/hany/Downloads/data.done/mc_2026.11.19/txt')
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

SERIES = {  # folder -> topic file name
    '大盗贼': '大盗贼', '刺桐花落': '刺桐花落', '学生妹': '学生妹', '十里洋场': '十里洋场',
    '十里洋场杯决赛': '十里洋场杯决赛', '十里洋场杯': '十里洋场杯', '松兰山海': '松兰山海', '母女': '母女',
    '上海狼在俄罗斯': '上海狼在俄罗斯', 'Great_上海狼在俄罗斯': '上海狼在俄罗斯', 'Great_上海狼在俄罗斯_02': '上海狼在俄罗斯',
    '王牌写手': '王牌写手', '军密档案': '军密档案', '沧桑的情人': '沧桑的情人', '沧桑的情人_02': '沧桑的情人',
    'Great_Redarmy': 'Redarmy', 'Great_Redarmy_B': 'Redarmy', 'Great_Redarmy_C': 'Redarmy',
    'Great_沈公子': '沈公子', 'Great_沈公子_02': '沈公子', 'J情一夜': 'J情一夜',
}
SERIES_ORDER = list(SERIES)
REGION_FOLDER = {  # location folders -> canonical region file
    '上海': '上海', '东北军区藏经阁': '东北', '川渝精品收藏馆': '川渝', '江苏军区': '江浙', '徐州': '江浙',
    '山东军区冬瀌聚丽': '山东', '湖南': '湖南', '安徽军区': '安徽', '湖北': '湖北', '北京军区流金岁月': '京津',
    '北京军区歌舞升平': '京津', '欧非': '其他海外', '河北': '河北', '河南军区昔日传奇': '河南',
}

def kw(s): return [x for x in s.split() if x]
REG = {
 '川渝': kw('四川 重庆 成都 绵阳 德阳 乐山 宜宾 泸州 南充 自贡 攀枝花 内江 眉山 广元 遂宁 雅安 达州 万州 涪陵 渝中 解放碑 南坪 沙坪坝 九龙坡 观音桥 杨家坪 石桥铺 双流 温江 郫县 龙泉驿 春熙路 川渝 渝北 巴蜀 江北区 黄龙溪'),
 '广东': kw('广东 广州 深圳 东莞 佛山 中山市 珠海 惠州 汕头 江门 湛江 茂名 肇庆 清远 韶关 揭阳 潮州 梅州 河源 阳江 汕尾 顺德 番禺 福田 罗湖 宝安 龙岗 盐田 南头 黄岗 石岩 常平 樟木头 虎门 厚街 塘厦 凤岗 清溪 石龙 石碣 大朗 寮步 横沥 桥头镇 谢岗 黄江 洪梅 道滘 麻涌 高埗 万江 花都 增城 从化 越秀 海珠 荔湾 凤凰岗 沙井 西乡 观澜 布吉 坪山 公明 松岗 光明新区'),
 '上海': kw('上海 浦东 徐汇 静安 闵行 虹口 杨浦 普陀 长宁 黄浦 卢湾 宝山 嘉定 松江 青浦 奉贤 南汇 崇明 川沙 陆家嘴 人民广场 淮海路 徐家汇 五角场 莘庄 七宝 龙华 漕河泾 中山公园 延安西路 曹杨 真如 大场 罗店 上海滩 沪上 申城'),
 '山东': kw('山东 济南 青岛 烟台 威海 潍坊 淄博 临沂 济宁 泰安 日照 德州 聊城 滨州 东营 枣庄 菏泽 莱芜 龙口 蓬莱 荣成 文登 乳山 海阳 即墨 胶州 诸城 寿光 曲阜 微山 韩庄'),
 '云南': kw('云南 昆明 大理 丽江 西双版纳 景洪 曲靖 玉溪 保山 德宏 瑞丽 芒市 河口 个旧 蒙自 开远 文山 楚雄 普洱 思茅 临沧 红河 香格里拉 中甸 腾冲 畹町'),
 '湖南': kw('湖南 长沙 株洲 湘潭 衡阳 岳阳 常德 益阳 邵阳 郴州 永州 怀化 娄底 张家界 吉首 浏阳 宁乡 韶山 株州'),
 '湖北': kw('湖北 武汉 宜昌 襄阳 荆州 黄石 十堰 孝感 黄冈 咸宁 鄂州 随州 荆门 恩施 汉口 汉阳 武昌 江汉路 光谷 洪山 江夏 汉正街'),
 '安徽': kw('安徽 合肥 芜湖 蚌埠 淮南 马鞍山 淮北 铜陵 安庆 黄山市 滁州 阜阳 宿州 六安 亳州 池州 宣城 巢湖 明光 桐城 蜀山区 包河区 瑶海区 庐阳区'),
 '江浙': kw('江苏 浙江 南京 苏州 无锡 常州 镇江 扬州 泰州 南通 盐城 淮安 连云港 宿迁 徐州 杭州 宁波 温州 嘉兴 湖州 绍兴 金华 衢州 舟山 台州 丽水 义乌 昆山 张家港 常熟 太仓 江阴 宜兴 溧阳 金坛 句容 丹阳 吴江 江宁 仙林 新街口 夫子庙 西湖 萧山 余杭 临安 慈溪 余姚 诸暨 温岭 瑞安 乐清 海宁 平湖 桐乡 睢宁 邳州 新沂 沛县 丰县'),
 '京津': kw('北京 天津 海淀 丰台 石景山 门头沟 顺义 怀柔 平谷 密云 延庆 望京 三里屯 中关村 国贸 五道口 和平区 河西区 河东区 南开区 塘沽 滨海新区 北辰 西青 津南 京城'),
 '东北': kw('黑龙江 吉林 辽宁 哈尔滨 长春 沈阳 大连 鞍山 抚顺 本溪 丹东 锦州 营口 阜新 辽阳 盘锦 铁岭 朝阳市 葫芦岛 齐齐哈尔 牡丹江 佳木斯 大庆 鸡西 双鸭山 伊春 七台河 鹤岗 绥化 四平 辽源 通化 松原 白城 延吉 东北'),
 '河北': kw('河北 石家庄 唐山 秦皇岛 邯郸 邢台 保定 张家口 承德 沧州 廊坊 衡水 燕郊 三河 涿州 霸州 任丘 野三坡 北戴河 山海关'),
 '福建': kw('福建 福州 厦门 泉州 漳州 莆田 三明 龙岩 宁德 晋江 石狮 南安 惠安 福清 霞浦 福鼎'),
 '海南': kw('海南 海口 三亚 琼海 儋州 文昌 万宁'),
 '江西': kw('江西 南昌 九江 赣州 吉安 宜春 上饶 抚州 景德镇 萍乡 新余 鹰潭'),
 '河南': kw('河南 郑州 洛阳 开封 南阳 安阳 新乡 许昌 平顶山 焦作 濮阳 商丘 信阳 周口 驻马店 漯河 三门峡 鹤壁 济源 豫区'),
 '陕西': kw('西凤 陕西 西安 咸阳 宝鸡 渭南 汉中 榆林 铜川 安康 商洛'),
 '山西': kw('山西 太原 大同 临汾 运城 晋中 长治 晋城 阳泉 朔州 忻州 吕梁'),
 '广西': kw('广西 南宁 桂林 柳州 梧州 北海 玉林 钦州 防城港 贵港 百色 河池 来宾 崇左 贺州 浦寨 东兴 凭祥'),
 '贵州': kw('贵州 贵阳 遵义 六盘水 安顺 毕节 铜仁 都匀 凯里'),
 '新疆': kw('巴郎子 新疆 乌鲁木齐 克拉玛依 喀什 伊犁 库尔勒 吐鲁番 哈密 石河子 昌吉'),
 '甘肃': kw('甘肃 兰州 天水 白银 酒泉 嘉峪关 张掖 武威 平凉 庆阳'),
 '内蒙': kw('内蒙 呼和浩特 包头 鄂尔多斯 赤峰 通辽 呼伦贝尔 乌海 满洲里'),
 '宁夏': kw('宁夏 银川 石嘴山 吴忠 固原'),
 '青海': kw('青海 西宁 格尔木'),
 '港澳': kw('香港 澳门 九龙 尖沙咀 旺角 湾仔 铜锣湾 新界 葡京 氹仔 港澳'),
 '台湾': kw('台湾 台北 台中 台南 基隆 新竹 桃园 高雄市'),
 '俄罗斯': kw('俄罗斯 莫斯科 圣彼得堡 海参崴 符拉迪沃斯托克 远东 伊尔库茨克 新西伯利亚'),
 '日本': kw('日本 东京 大阪 名古屋 北海道 福冈 横滨 京都'),
 '韩国': kw('韩国 首尔 釜山 仁川 济州'),
 '美国': kw('美总阅 美国 纽约 洛杉矶 旧金山 芝加哥 拉斯维加斯 华盛顿 波士顿 休斯顿'),
 '其他海外': kw('加拿大 多伦多 温哥华 澳洲 澳大利亚 悉尼 墨尔本 新西兰 奥克兰 英国 伦敦 法国 巴黎 德国 柏林 泰国 曼谷 芭堤雅 新加坡 马来西亚 吉隆坡 越南 河内 胡志明 菲律宾 马尼拉 印尼 雅加达 非洲 多哥 欧洲 古巴 墨西哥 迪拜 印度 柬埔寨 缅甸 老挝 法兰克福 慕尼黑 阿姆斯特丹 布拉格 维也纳 米兰 罗马 巴塞罗那 马德里 欧总阅 FKK'),
}
TAG = {'桂': '广西', '云': '云南', '川': '川渝', '渝': '川渝', '湘': '湖南', '鄂': '湖北', '豫': '河南', '京': '京津', '津': '京津',
       '沪': '上海', '粤': '广东', '苏': '江浙', '浙': '江浙', '皖': '安徽', '鲁': '山东', '闽': '福建', '陕': '陕西', '晋': '山西', '冀': '河北', '赣': '江西', '黔': '贵州'}
TAGRE = re.compile(r'[【\[]([桂云川渝湘鄂豫京津沪粤苏浙皖鲁闽陕晋冀赣黔])(?:总阅|副阅|参阅|总参|参|副|总)')
FIELD = re.compile(r'【(?:买春)?(?:地址|地点|位置|店名|地区|城市|区域)[^】]*】[：:]?([^\n【]{0,60})')

man = list(csv.DictReader(open(T + '/mc_merged.manifest.csv', encoding='utf-8-sig')))
lines = open(T + '/mc_merged.txt', encoding='utf-8').read().split('\n')
dups = collections.defaultdict(list)
for l in open(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/txt_cand/removed.tsv', encoding='utf-8'):
    p = l.rstrip('\n').split('\t')
    if p[0] == 'DUP': dups[p[2]].append(p[1])

def root(rel): return rel.split('／')[0].split('/')[0]

def keyword_route(title, body):
    sc = {}
    fld = ' '.join(FIELD.findall(body[:4000]))
    for reg, ws in REG.items():
        s = 0
        for w in ws:
            s += 6 * title.count(w) + 6 * fld.count(w) + body.count(w)
        if s: sc[reg] = s
    tag = None
    m = TAGRE.search(title)
    if m: tag = TAG[m.group(1)]
    if not sc:
        return (TAG and tag), 'tag-only' if tag else None, sc
    ranked = sorted(sc.items(), key=lambda x: -x[1])
    best, bs = ranked[0]; second = ranked[1][1] if len(ranked) > 1 else 0
    if bs >= 8 and bs >= 2 * second: return best, 'keyword', sc
    if tag and tag in sc and sc[tag] >= max(3, 0.5 * bs): return tag, 'keyword+tag', sc
    if bs >= 4 and second == 0: return best, 'keyword-weak', sc
    if bs >= 4 and bs >= 1.5 * second: return best, 'keyword-lead', sc
    return None, 'unsure', sc

recs = []
for r in man:
    s, e = int(r['start_line']), int(r['end_line'])
    seg = lines[s - 1:e]
    rel = r['file'].replace('／', '/')
    chain = [root(rel)] + [root(x) for x in dups.get(rel, [])]
    target = basis = None
    for f in SERIES_ORDER:  # series topic folder anywhere in the chain
        if f in chain: target, basis = SERIES[f], 'series-folder' + ('' if f == chain[0] else '(dup)'); break
    if not target:
        for f in chain:
            if f in REGION_FOLDER: target, basis = REGION_FOLDER[f], 'region-folder' + ('' if f == chain[0] else '(dup)'); break
    sc = {}
    if not target:
        t, b, sc = keyword_route(seg[0], '\n'.join(seg[1:]))
        if t: target, basis = t, b
        else: target, basis = '待定义', b or 'no-clue'
    recs.append(dict(r=r, seg=seg, target=target, basis=basis, sc=sc))

# ---- pass 2 (pending only): learn venue/street names from confident stories, then relax the thresholds
RELAX = '--relax' in sys.argv
if RELAX:
    CJ = re.compile(r'[一-鿿]+')
    known = {w for ws in REG.values() for w in ws}
    gram = collections.defaultdict(collections.Counter)
    for x in recs:
        if x['basis'] in ('keyword', 'keyword+tag', 'region-folder') and x['target'] in REG:
            txt = '\n'.join(x['seg'])[:2500]
            seen = set()
            for run in CJ.findall(txt):
                for n in (3, 4):
                    for i in range(len(run) - n + 1): seen.add(run[i:i + n])
            for g in seen: gram[g][x['target']] += 1
    learned = {}
    for g, c in gram.items():
        tot = sum(c.values())
        if tot >= 5:
            reg, k = c.most_common(1)[0]
            if k / tot >= 0.9 and g not in known: learned[g] = reg
    print('learned clue words:', len(learned), collections.Counter(learned.values()).most_common(5))
    by_reg = collections.defaultdict(list)
    for g, reg in learned.items(): by_reg[reg].append(g)
    for x in recs:
        if x['target'] != '待定义': continue
        title, body = x['seg'][0], '\n'.join(x['seg'][1:])
        text = title + '\n' + body
        sc = dict(x['sc'])
        for reg, gs in by_reg.items():
            s = sum(text.count(g) for g in gs)
            if s: sc[reg] = sc.get(reg, 0) + s
        x['sc'] = sc
        if not sc: x['basis'] = 'no-clue'; continue
        ranked = sorted(sc.items(), key=lambda kv: -kv[1])
        best, bs = ranked[0]; second = ranked[1][1] if len(ranked) > 1 else 0
        if bs > second:
            x['target'], x['basis'] = best, 'mentions-majority' if bs >= 3 else 'mention-single'
        else:  # tie: region whose clue word appears first (title counts as position -1)
            tied = [reg for reg, v in ranked if v == bs]
            def first_pos(reg):
                ws = list(REG.get(reg, [])) + by_reg.get(reg, [])
                if any(w in title for w in ws): return -1
                ps = [body.find(w) for w in ws if w in body]
                return min(ps) if ps else 10 ** 9
            x['target'], x['basis'] = min(tied, key=first_pos), 'first-mention'

for x in recs:  # weak evidence stays pending; the candidate region is kept in the basis column for review
    if x['basis'] in ('mention-single', 'first-mention'):
        x['basis'] = f"{x['basis']}(held:{x['target']})"; x['target'] = '待定义'

stories = {}; route = []
for x in recs:
    stories.setdefault(x['target'], []).append((x['r']['file'], x['seg']))
    top = sorted(x['sc'].items(), key=lambda kv: -kv[1])[:2]
    route.append((x['r']['no'], x['r']['file'], x['target'], x['basis'], ';'.join(f'{k}:{v}' for k, v in top)))

for name, items in stories.items():
    out = []; man_out = []; ln = 1
    for k, (f, seg) in enumerate(items, 1):
        man_out.append((k, f, ln, ln + len(seg) - 1, len('\n'.join(seg))))
        out += seg + ['']; ln += len(seg) + 1
    open(f'{OUT}/mc_{name}.txt', 'w', encoding='utf-8', newline='\n').write('\n'.join(out[:-1]) + '\n')
    with open(f'{OUT}/mc_{name}.manifest.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n'); w.writerow(['no', 'file', 'start_line', 'end_line', 'chars']); w.writerows(man_out)
with open(f'{OUT}/routing_report.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh, lineterminator='\n'); w.writerow(['no', 'file', 'topic', 'basis', 'top_scores']); w.writerows(route)
bc = collections.Counter(r[3].split('(')[0] for r in route)
print('stories', len(route), 'topics', len(stories)); print(dict(bc))
for n, it in sorted(stories.items(), key=lambda x: -len(x[1])): print(f'{len(it):5} {n}')
