#!/usr/bin/env python3 -I
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DL
import os,hashlib,collections,sys
S=(DL+'/data/2018.06.18_report_word_doc_txt_imgs')
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
files=[]
for dp,dn,fs in os.walk(S):
    dn[:]=sorted(dn)
    for f in sorted(fs):
        if f=='.DS_Store': continue
        files.append(os.path.join(dp,f))
by=collections.defaultdict(list)
for p in files: by[(os.path.getsize(p),)] .append(p)
H={}
for k,L in by.items():
    if len(L)>1:
        for p in L: H[p]=sha(p)
g=collections.defaultdict(list)
for p,h in H.items(): g[h].append(p)
dups={h:L for h,L in g.items() if len(L)>1}
def cat(p):
    e=os.path.splitext(p)[1].lower()
    if e in('.doc','.docx','.txt','.rtf','.pdf','.xls','.exe','.zip'): return 'document/other'
    if e in('.jpg','.jpeg','.png','.gif','.bmp'): return 'image'
    if e in('.php','.js','.css'): return 'web asset'
    if e in('.htm','.html'): return 'saved page'
    return 'other'
print('files',len(files),'| exact-duplicate groups',len(dups),'| extra copies',sum(len(L)-1 for L in dups.values()),'| extra bytes MB',sum(os.path.getsize(L[0])*(len(L)-1) for L in dups.values())//10**6)
c=collections.Counter(); b=collections.Counter()
for L in dups.values():
    k=cat(L[0]); c[k]+=len(L)-1; b[k]+=os.path.getsize(L[0])*(len(L)-1)
for k in c: print(f'  {k}: {c[k]} extra copies, {b[k]/1e6:.0f} MB')
# where the copies live: folder-pair patterns
pat=collections.Counter()
for L in dups.values():
    pat[tuple(sorted({os.path.relpath(p,S).split('/')[0]+('/'+os.path.relpath(p,S).split('/')[1] if os.path.relpath(p,S).count('/')>1 else '') for p in L}))]+=1
for k,v in pat.most_common(12): print(' ',v,'groups in',k)
import pickle; pickle.dump(dups,open('dup_src.pkl','wb'))
