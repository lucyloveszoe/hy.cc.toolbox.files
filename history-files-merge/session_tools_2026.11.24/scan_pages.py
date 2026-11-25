"""Read-only scan of reports_merged/<set>: content length, blank pages, exact-duplicate signatures, noise characters.
Writes <out>.json. Usage: scan_pages.py <reports_merged/141 dir> <out.json>"""
import os,re,sys,json,html,hashlib,collections
D=os.path.abspath(sys.argv[1]);OUT=sys.argv[2]
def sha(p):
    m=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): m.update(b)
    return m.hexdigest()
ih={}
def imgh(p):
    if p not in ih: ih[p]=sha(p)
    return ih[p]
NOISE=re.compile('[  \xa0�-​-‏‪-‮⁠﻿\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|&#\\d+;|maichun|本帖来源|本帖最[后後]由|本帖[隐隱]藏的|INCLUDEPICTURE|HYPERLINK|招财进宝|关闭注册')
res={}
for f in sorted(os.listdir(D)):
    if not f.endswith('.html'): continue
    t=open(os.path.join(D,f),encoding='utf-8').read()
    body=t.split('<body>',1)[-1]
    body=re.sub(r'<h1>.*?</h1>','',body,flags=re.S)
    imgs=re.findall(r'<img[^>]*?\ssrc="([^"]+)"',body)
    ex=[i for i in imgs if os.path.exists(os.path.join(D,html.unescape(i)))]
    txt=re.sub(r'<h3>.*?</h3>','',body,flags=re.S)
    txt=html.unescape(re.sub(r'<[^>]+>',' ',txt)).replace('[image missing]','')
    core=re.findall(r'[\w一-鿿]',txt)
    norm=re.sub(r'\s+','',txt).lower()
    res[f]=dict(core=len(core),imgs=len(ex),missing=body.count('[image missing]'),
        sig=hashlib.md5(norm.encode()).hexdigest()+'|'+hashlib.md5('|'.join(imgh(os.path.join(D,html.unescape(i))) for i in ex).encode()).hexdigest(),
        txt=hashlib.md5(norm.encode()).hexdigest(),noise=sorted(set(m.group() for m in NOISE.finditer(t))))
json.dump(res,open(OUT,'w'),ensure_ascii=False)
c=collections.Counter()
for r in res.values():
    for b in (0,10,30,60,100): 
        if r['core']<=b and r['imgs']==0: c[f'noimg core<={b}']+=1
    if r['core']<=30: c[f'core<=30 (any imgs)']+=1
print(len(res),dict(c))
g=collections.defaultdict(list)
for f,r in res.items(): g[r['sig']].append(f)
print('exact dup groups',sum(1 for v in g.values() if len(v)>1),'extra',sum(len(v)-1 for v in g.values() if len(v)>1))
g2=collections.defaultdict(list)
for f,r in res.items(): g2[r['txt']].append(f)
print('same-text groups',sum(1 for v in g2.values() if len(v)>1),'extra',sum(len(v)-1 for v in g2.values() if len(v)>1))
n=collections.Counter(x for r in res.values() for x in r['noise']);print('noise',len([1 for r in res.values() if r['noise']]),dict(n))
