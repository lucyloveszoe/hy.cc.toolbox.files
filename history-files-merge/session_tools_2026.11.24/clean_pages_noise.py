"""Noise pass over reports_merged/<set> pages: zero-width/bidi characters; garbage-token tails of plain text lines
(doc_to_txt.strip_tail, rule 4.1 variant 1). Usage: clean_pages_noise.py <dir> [--go]  (dry run without --go)"""
import os,sys,re,html
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from doc_to_txt import strip_tail
D=sys.argv[1];GO='--go' in sys.argv
ZW=re.compile('[​-‏‪-‮⁠﻿]')
nz=nt=files=0;samples=[]
for f in sorted(os.listdir(D)):
    if not f.endswith('.html'): continue
    p=os.path.join(D,f);t=o=open(p,encoding='utf-8').read()
    head,sep,body=t.partition('<body>')
    t2,k=ZW.subn('',body);nz+=k
    out=[]
    for line in t2.split('\n'):
        m=re.fullmatch(r'([^<]*?)((?:<br>)?)',line)
        if m and m.group(1).strip():
            tx=html.unescape(m.group(1));new,hit=strip_tail(tx)
            if hit:
                nt+=1
                if len(samples)<6: samples.append(tx[len(new):][:40])
                line=html.escape(new,quote=True)+m.group(2)
        out.append(line)
    t2=head+sep+'\n'.join(out)
    if t2!=o:
        files+=1
        if GO: open(p,'w',encoding='utf-8',newline='').write(t2)
print('files changed',files,'zero-width removed',nz,'garbage tails removed',nt,'samples',samples)
