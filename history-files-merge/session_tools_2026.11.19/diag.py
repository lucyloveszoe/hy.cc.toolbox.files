import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import PROJ
import sys,csv,re,collections
from pathlib import Path
sys.path.insert(0,PROJ)
from htmltree import decode_file
root=Path(sys.argv[1]); summ=Path(sys.argv[2]); n=int(sys.argv[3]) if len(sys.argv)>3 else 4
rows=[r for r in csv.DictReader(open(summ,encoding='utf-8-sig')) if r['mode']=='unsupported']
print(len(rows),'unsupported')
sig=collections.Counter(); ex={}
for r in rows:
    p=next(root.rglob(r['page']),None) if '/' not in r['page'] else root/r['page']
    if not p: continue
    t=decode_file(p)
    size=len(t)
    cj=len(re.findall(r'[一-鿿]',re.sub(r'(?is)<(script|style).*?</\1>','',t)))
    cls=collections.Counter(re.findall(r'(?:class|id)=["\']?([\w\-]+)',t,re.I))
    key=('tiny' if size<1500 else 'nocjk' if cj<50 else 'content')
    sig[key]+=1; ex.setdefault(key,[]).append((p,size,cj,cls.most_common(12)))
print(sig)
for k,v in ex.items():
    for p,size,cj,c in v[:n]:
        print(k,p.name[:40],size,cj,c)
