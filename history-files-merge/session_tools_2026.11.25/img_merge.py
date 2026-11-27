import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DL
"""Flat merge of image folders: one file per SHA-256, named <first folder>__<name>, + images_merged.manifest.csv.
Usage: python3 -I img_merge.py [src=~/Downloads/images-only] [dest=<src>.merged] [--go]   (dry run without --go; dest must not exist)"""
import os,sys,hashlib,csv,shutil,unicodedata,collections
_a=[x for x in sys.argv[1:] if not x.startswith('--')]; GO='--go' in sys.argv
S=_a[0] if _a else (DL+'/images-only'); D=_a[1] if len(_a)>1 else S.rstrip('/')+'.merged'
g=collections.OrderedDict(); fake=[]
for top in sorted(os.listdir(S)):
    for dp,dn,fn in os.walk(os.path.join(S,top)):
        dn.sort()
        for f in sorted(fn):
            if f in('.DS_Store','Thumbs.db'): continue
            p=os.path.join(dp,f); b=open(p,'rb').read()
            if not(b[:3]==b'\xff\xd8\xff' or b[:8]==b'\x89PNG\r\n\x1a\n' or b[:3]==b'GIF' or b[:2]==b'BM'): fake.append(p); continue
            g.setdefault(hashlib.sha256(b).hexdigest(),[]).append(p)
print('files',sum(len(v) for v in g.values()),'distinct',len(g),'non-images',len(fake),'->',D)
if not GO: sys.exit('dry run: add --go to write')
os.makedirs(D,exist_ok=False); names=set(); rows=[]
for i,(h,ps) in enumerate(g.items(),1):
    p=ps[0]; rel=os.path.relpath(p,S); top=rel.split(os.sep)[0]; base=os.path.basename(p)
    n=unicodedata.normalize('NFC',f'{top}__{base}')
    assert n.lower() not in names and len(n.encode())<255; names.add(n.lower())
    shutil.copy2(p,os.path.join(D,n)); assert hashlib.sha256(open(os.path.join(D,n),'rb').read()).hexdigest()==h
    rows.append((i,n,h,os.path.getsize(p),len(ps),' | '.join(os.path.relpath(x,S) for x in ps)))
with open(D+'/images_merged.manifest.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f,lineterminator='\n'); w.writerow(['no','file','sha256','bytes','copies_merged','original_paths']); w.writerows(rows)
open(D+'/not_images.tsv','w',encoding='utf-8').write(''.join(os.path.relpath(p,S)+'\n' for p in fake))
print(len(rows),'images copied;',len(fake),'non-images listed; dup groups',sum(r[4]>1 for r in rows))
