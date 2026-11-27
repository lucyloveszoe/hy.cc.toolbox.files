#!/usr/bin/env python3 -I
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD
import os,re,html,csv,io,unicodedata,collections
D=DD; H=D+'/mc_2026.11.19/html'
nfc=lambda s:unicodedata.normalize('NFC',s)
ATTR=re.compile(r'<(img|a|link|script|source|video|audio|iframe)\b[^>]*?\b(src|href)\s*=\s*"([^"]*)"',re.I)
npages=0; links=collections.Counter(); broken=[]; remote=0; linked=set()
for dp,_,fs in os.walk(D):
    for f in fs:
        if not f.lower().endswith(('.html','.htm')): continue
        p=os.path.join(dp,f); npages+=1; t=open(p,encoding='utf-8',errors='replace').read()
        for tag,attr,v in ATTR.findall(t):
            v=html.unescape(v).strip()
            if not v or v.startswith(('#','mailto:','javascript:','data:')): continue
            if re.match(r'[a-z]+://',v,re.I) or v.startswith('//'): remote+=1; continue
            v=v.split('#')[0].split('?')[0]
            if not v: continue
            tgt=nfc(os.path.normpath(os.path.join(dp,v))); links[tag.lower()]+=1; linked.add(tgt)
            if not os.path.exists(os.path.join(dp,v)): broken.append((os.path.relpath(p,D),tag,v))
print('html pages under data.done:',npages,'| local links',dict(links),'| remote links (not checked)',remote,'| BROKEN',len(broken))
for b in broken[:10]: print('  ',b)
# unlinked images inside the html roots
orph=0; n=0
for g in ('merges','topics','locations'):
    for root in os.listdir(f'{H}/{g}'):
        for dp,_,fs in os.walk(f'{H}/{g}/{root}/images'):
            for f in fs:
                if f in('.DS_Store','manifest.csv'): continue
                n+=1
                if nfc(os.path.normpath(os.path.join(dp,f))) not in linked: orph+=1
print('images in html roots',n,'| not linked by any page',orph)
# csv outputs
tot=miss=ncsv=0; bad=[]
for dp,_,fs in os.walk(D):
    for f in fs:
        if not f.lower().endswith('.csv'): continue
        p=os.path.join(dp,f); raw=open(p,'rb').read().decode('utf-8-sig',errors='replace'); rows=list(csv.reader(io.StringIO(raw,newline='')))
        if not rows or 'output' not in rows[0]: continue
        ncsv+=1; k=rows[0].index('output')
        for r in rows[1:]:
            if len(r)>k and r[k]:
                tot+=1
                if not os.path.exists(os.path.normpath(os.path.join(dp,r[k]))): miss+=1; bad.append((f,r[k]))
print('CSV files with output:',ncsv,'| outputs',tot,'| missing',miss); print(bad[:5])
