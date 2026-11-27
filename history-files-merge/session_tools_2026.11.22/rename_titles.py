#!/usr/bin/env python3 -I
"""Rename numeric-named reports in mcjt-total/reports to the first line of the primary post. Dry run unless --go."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import SCRATCH
import os,re,sys,html,csv,collections,unicodedata,shutil,importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
GO='--go' in sys.argv
R=q.BASE+'/merges/mcjt-total/reports/'
nk=lambda s:re.sub(r'\s+','',unicodedata.normalize('NFC',s)).lower()
FOOT=[re.compile(r'\s+-\s+[^\s-]*春色.*$'),re.compile(r'\s*买春堂(?:\s*-\s*Powered by Discuz!)?\s*$'),re.compile(r'\s*-?\s*Powered by Discuz!\s*$'),
      re.compile(r'\s+-\s+★\s*军\s*密\s*档\s*案\s*★.*$')]
def title_of(t):
    m=re.search(r'(?is)</h3>\s*(.*?)(?:<br|</section|<img)',t)
    if not m: return ''
    s=html.unescape(re.sub(r'<[^>]+>','',m.group(1)))
    s=re.sub(r'[\x00-\x1f\x7f   　]',' ',s); s=re.sub(r'\s+',' ',s).strip()
    return s
def clean(s):
    ch=True
    while ch:
        ch=False
        for f in FOOT:
            n=f.sub('',s).strip()
            if n!=s: s=n; ch=True
    s=s.replace('/','／').replace(':','：') if False else s.replace('/','／')
    return s.strip(' .')
names=open('rename_list.txt').read().split(); files=[n+'.html' for n in names]
existing={nk(f) for f in os.listdir(R) if f.endswith('.html')}-{nk(f) for f in files}
used=set(existing); plan=[]; flags=collections.Counter(); foot=0
for f in files:
    t=open(R+f,encoding='utf-8').read(); raw=title_of(t); s=clean(raw)
    if s!=raw: foot+=1
    if len(s)<4: flags['too short/empty']+=1; plan.append((f,None,raw)); continue
    stem=s
    while len((stem+'.html').encode())>240: stem=stem[:-1]
    if stem!=s: flags['truncated to 240 bytes']+=1
    new=stem.rstrip(' .')+'.html'; k=2; base=new[:-5]
    while nk(new) in used:
        new=f'{base} ({k}).html'; k+=1; flags['name clash -> suffix']+=1
    used.add(nk(new)); plan.append((f,new,raw))
print('files',len(files),'| footers peeled',foot,'|',dict(flags))
bad=[p for p in plan if p[1] is None]; print('no usable title:',[(p[0],p[2][:20]) for p in bad])
for f,n,r in plan[:6]+plan[70:73]+plan[-3:]: print(' ',f,'->',(n or '')[:70])
lens=[len(n.encode()) for _,n,_ in plan if n]; print('longest new name (bytes)',max(lens),'| shortest title chars',min(len(n)-5 for _,n,_ in plan if n))
assert len({nk(n) for _,n,_ in plan if n})==len([1 for _,n,_ in plan if n])
if not GO or bad: print('DRY' if not GO else 'ABORT'); sys.exit()
# CSV + rename
mp={q.canon(R+f):n for f,n,_ in plan}
cs=[]
for p in q.all_csvs():
    rows,bom,eol=q.read_csv(p)
    if not rows or 'output' not in rows[0]: continue
    k=rows[0].index('output'); hit=[]
    for ri,r in enumerate(rows[1:],1):
        if len(r)>k and r[k]:
            c=q.canon(os.path.join(os.path.dirname(p),r[k]))
            if c in mp: hit.append((ri,c))
    if hit: cs.append((p,rows,bom,eol,hit,k))
print('csv files',len(cs),'rows',sum(len(c[4]) for c in cs))
BK=(SCRATCH+'/4d62ed09-50fc-4936-af43-187ad00942db/scratchpad/bak_rename_csv')
os.makedirs(BK)
for p,rows,bom,eol,hit,k in cs:
    shutil.copy2(p,BK+'/'+os.path.basename(p))
    for ri,c in hit: rows[ri][k]=os.path.relpath(os.path.join(os.path.dirname(c),mp[c]),os.path.dirname(p))
    q.write_csv(p,rows,bom,eol)
for f,n,_ in plan: os.rename(R+f,R+n)
open(BK+'/renamed.tsv','w',encoding='utf-8').write(''.join(f'{f}\t{n}\n' for f,n,_ in plan))
print('DONE')
