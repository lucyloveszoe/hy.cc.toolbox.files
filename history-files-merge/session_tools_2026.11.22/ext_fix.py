#!/usr/bin/env python3 -I
"""Rename image files whose extension does not match their header (section 40.5), repoint html src, CSV outputs and images_merged.manifest.csv. Dry run unless --go."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD, SCRATCH
import os,re,sys,html,csv,io,shutil,collections,unicodedata
GO='--go' in sys.argv
D=DD; L=D+'/mc_2026.11.19/images'; H=D+'/mc_2026.11.19/html'
BK=(SCRATCH+'/4d62ed09-50fc-4936-af43-187ad00942db/scratchpad/bak_ext')
nfc=lambda s:unicodedata.normalize('NFC',os.path.normpath(s))
SIG={b'\xff\xd8\xff':'.jpg',b'\x89PNG':'.png',b'GIF8':'.gif',b'BM':'.bmp'}
OK={'.jpg':('.jpg','.jpeg'),'.png':('.png',),'.gif':('.gif',),'.bmp':('.bmp',)}
def sniff(p):
    h=open(p,'rb').read(8)
    for k,v in SIG.items():
        if h.startswith(k): return v
mp={}; allfiles=set()
for base in (H,L):
    for dp,_,fs in os.walk(base):
        for f in fs:
            p=os.path.join(dp,f)
            if f.lower().endswith(('.html','.csv','.ds_store')) or f=='.DS_Store': continue
            allfiles.add(nfc(p).lower())
            s=sniff(p)
            if s and not p.lower().endswith(OK[s]):
                stem,_=os.path.splitext(p); mp[p]=stem+s
clash=[(o,n) for o,n in mp.items() if os.path.exists(n) or nfc(n).lower() in allfiles]
print('files to rename',len(mp),'| clashes',len(clash),clash[:3])
print(collections.Counter((os.path.splitext(o)[1].lower(),os.path.splitext(n)[1]) for o,n in mp.items()))
assert len({nfc(n).lower() for n in mp.values()})==len(mp)
cm={nfc(o):nfc(n) for o,n in mp.items()}
# html pages
ATTR=re.compile(r'(<img[^>]*?src=")([^"]+)(")',re.I)
pages={}; nlinks=0
for dp,_,fs in os.walk(D):
    for f in fs:
        if not f.lower().endswith(('.html','.htm')): continue
        p=os.path.join(dp,f); t=open(p,encoding='utf-8').read(); cnt=0
        def fx(m):
            global nlinks
            v=html.unescape(m.group(2))
            if re.match(r'[a-z]+:|//',v,re.I): return m.group(0)
            c=nfc(os.path.join(dp,v.split('#')[0].split('?')[0]))
            if c in cm: nlinks+=1; return m.group(1)+html.escape(os.path.relpath(cm[c],dp),quote=True)+m.group(3)
            return m.group(0)
        t2=ATTR.sub(fx,t)
        if t2!=t: pages[p]=t2
print('pages to rewrite',len(pages),'links repointed',nlinks)
# csv
cs={}
for dp,_,fs in os.walk(D):
    for f in fs:
        if not f.lower().endswith('.csv'): continue
        p=os.path.join(dp,f); raw=open(p,'rb').read(); bom=raw.startswith(b'\xef\xbb\xbf'); eol='\r\n' if b'\r\n' in raw else '\n'
        rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''))); 
        if not rows: continue
        h=rows[0]; ch=0
        if 'output' in h:
            k=h.index('output')
            for r in rows[1:]:
                if len(r)>k and r[k]:
                    c=nfc(os.path.join(dp,r[k]))
                    if c in cm: r[k]=os.path.relpath(cm[c],dp); ch+=1
        if f=='images_merged.manifest.csv' and dp==D+'/mc_2026.11.19':
            fi=h.index('file')
            for r in rows[1:]:
                c=nfc(L+'/'+r[fi])
                if c in cm: r[fi]=os.path.basename(cm[c]); ch+=1
        if ch: cs[p]=(rows,bom,eol,ch)
print('csv files',len(cs),'rows',sum(v[3] for v in cs.values()),[ (os.path.basename(p),v[3]) for p,v in cs.items()][:8])
if not GO or clash: print('DRY' if not GO else 'ABORT'); sys.exit()
os.makedirs(BK)
for p in list(pages)+list(cs): 
    d=BK+'/'+os.path.relpath(p,D); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copy2(p,d)
for p,t in pages.items(): open(p,'w',encoding='utf-8',newline='').write(t)
for p,(rows,bom,eol,_) in cs.items():
    with open(p,'w',encoding='utf-8-sig' if bom else 'utf-8',newline='') as f: csv.writer(f,lineterminator=eol).writerows(rows)
for o,n in mp.items(): os.rename(o,n)
open(BK+'/renamed.tsv','w',encoding='utf-8').write(''.join(f'{o}\t{n}\n' for o,n in mp.items()))
print('DONE')
