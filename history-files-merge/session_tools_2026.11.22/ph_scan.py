#!/usr/bin/env python3 -I
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD
import os,re,collections,html
B=(DD+'/mc_2026.11.19/html'); KEY='以下内容需要回复才能看到'
files=0; lines=0; per=collections.Counter(); forms=collections.Counter(); ctx=collections.Counter(); roots=collections.Counter()
for dp,_,fs in os.walk(B):
    for f in fs:
        if not f.endswith('.html'): continue
        p=os.path.join(dp,f); t=open(p,encoding='utf-8',errors='replace').read()
        if KEY not in t: continue
        files+=1; roots[os.path.relpath(p,B).split('/')[0]+'/'+os.path.relpath(p,B).split('/')[1]]+=1
        # work per text node between tags/br
        for m in re.finditer(r'[^<>\n]*'+KEY+r'[^<>\n]*',t):
            lines+=1; s=html.unescape(m.group(0)); forms[re.sub(r'\s+',' ',s.strip())[:60]]+=1
        # what surrounds it in markup
        for m in re.finditer(r'(.{0,25})'+KEY+r'(.{0,25})',t,re.S): ctx[(re.sub(r'\s+',' ',m.group(1))[-12:],re.sub(r'\s+',' ',m.group(2))[:12])]+=1
print('files',files,'occurrences',lines)
print('distinct line forms',len(forms)); [print(' ',n,repr(k)) for k,n in forms.most_common(8)]
print('markup context (before | after):'); [print(' ',n,repr(k)) for k,n in ctx.most_common(8)]
print(roots.most_common(8),'... roots',len(roots))
