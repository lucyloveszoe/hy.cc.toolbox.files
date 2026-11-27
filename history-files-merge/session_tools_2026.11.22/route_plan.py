#!/usr/bin/env python3 -I
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import PROJ, DD
import re, os, html, csv, collections, sys
src=open((PROJ+'/session_tools_2026.11.19/route_topics.py'),encoding='utf-8').read().split('\n')
ns={'re':re,'os':os,'collections':collections}
exec('\n'.join(src[25:64]),ns)           # kw, REG, TAG, TAGRE, FIELD
exec('\n'.join(src[74:94]),ns)           # keyword_route
REG=ns['REG']; keyword_route=ns['keyword_route']
BASE=(DD+'/mc_2026.11.19/html')
LOC2REG={'上海':'上海','东北军区藏经阁':'东北','川渝精品收藏馆':'川渝','江苏军区':'江浙','徐州':'江浙','山东军区冬瀌聚丽':'山东','湖南':'湖南','安徽军区':'安徽','湖北':'湖北','河南军区昔日传奇':'河南','河北':'河北','欧非':'其他海外','广东':'广东','海外':'其他海外','广西':'广西','福建':'福建','陕西':'陕西','云南':'云南','港澳':'港澳','新疆':'新疆','贵州':'贵州','台湾':'台湾','山西':'山西','海南':'海南','甘肃':'甘肃','江西':'江西','北京军区歌舞升平':'京津','天津':'京津'}
def page(p):
    t=open(p,encoding='utf-8',errors='replace').read()
    h=re.search(r'(?is)<h1[^>]*>(.*?)</h1>',t); title=html.unescape(re.sub(r'<[^>]+>','',h.group(1))).strip() if h else ''
    b=re.sub(r'(?is)<head>.*?</head>','',t); b=re.sub(r'(?is)<h1[^>]*>.*?</h1>','',b,count=1)
    b=re.sub(r'(?i)<br\s*/?>|</p>|</div>|</section>','\n',b)
    return title, html.unescape(re.sub(r'<[^>]+>','',b))
# learn venue words from locations
CJ=re.compile(r'[一-鿿]+'); known={w for ws in REG.values() for w in ws}
gram=collections.defaultdict(collections.Counter)
for root in os.listdir(f'{BASE}/locations'):
    reg=LOC2REG.get(root); rp=f'{BASE}/locations/{root}/reports'
    if not reg or not os.path.isdir(rp): continue
    for fn in os.listdir(rp):
        if not fn.endswith('.html'): continue
        t,b=page(os.path.join(rp,fn)); seen=set()
        for run in CJ.findall((t+'\n'+b)[:2500]):
            for n in (3,4):
                for i in range(len(run)-n+1): seen.add(run[i:i+n])
        for g in seen: gram[g][reg]+=1
learned={}
for g,c in gram.items():
    tot=sum(c.values())
    if tot>=5:
        reg,k=c.most_common(1)[0]
        if k/tot>=0.9 and g not in known: learned[g]=reg
by=collections.defaultdict(list)
for g,r in learned.items(): by[r].append(g)
print('learned words',len(learned))
rows=[]
for root in sorted(os.listdir(f'{BASE}/merges')):
    rp=f'{BASE}/merges/{root}/reports'
    if not os.path.isdir(rp): continue
    for fn in sorted(os.listdir(rp)):
        if not fn.endswith('.html'): continue
        t,b=page(os.path.join(rp,fn)); title=t or fn
        reg,basis,sc=keyword_route(title,b)
        if basis in ('unsure','keyword-weak','keyword-lead',None,'tag-only') or reg is None:
            s2=dict(sc); text=title+'\n'+b
            for r,gs in by.items():
                v=sum(text.count(g) for g in gs)
                if v: s2[r]=s2.get(r,0)+v
            rk=sorted(s2.items(),key=lambda kv:-kv[1])
            if rk and (len(rk)==1 or rk[0][1]>=2*rk[1][1]) and rk[0][1]>=5 and basis!='keyword-weak' or (rk and basis in ('keyword-weak','keyword-lead') and rk[0][1]>=8 and (len(rk)==1 or rk[0][1]>=2*rk[1][1])):
                rows.append((root,fn,rk[0][0],'learned',';'.join(f'{k}:{v}' for k,v in rk[:2]),title)); continue
            rows.append((root,fn,reg or '',basis or 'no-clue',';'.join(f'{k}:{v}' for k,v in rk[:2]),title)); continue
        rows.append((root,fn,reg,basis,';'.join(f'{k}:{v}' for k,v in sorted(sc.items(),key=lambda kv:-kv[1])[:2]),title))
with open('route_plan.tsv','w',encoding='utf-8') as f:
    f.write('root\tfile\tregion\tbasis\tscores\ttitle\n')
    for r in rows: f.write('\t'.join(r)+'\n')
print('reports',len(rows)); print(collections.Counter(r[3] for r in rows))
print(collections.Counter(r[2] for r in rows if r[3] in ('keyword','keyword+tag','learned')).most_common())
