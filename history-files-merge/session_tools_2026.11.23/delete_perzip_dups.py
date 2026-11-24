"""Delete per-zip files that GoChina.consolidated already holds (same bytes at the same path, or same text+image-sequence signature for reports, or same SHA-256 for images). Keeps CSVs. Dry run without --go. Run from the project folder. (PROCESSING_RULES 61.3)"""
import re,sys,hashlib,html,filecmp,os
from pathlib import Path
O=Path('outputs');C=O/'GoChina.consolidated';go='--go' in sys.argv
norm=lambda s: re.sub(r'\s+','',re.sub(r'<[^>]+>','',re.sub(r'(?s)<head>.*?</head>|<h1>.*?</h1>','',s))).lower()
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def sig(p):
    t=p.read_text(encoding='utf-8')
    seq=tuple(re.sub(r'^p\d+_','',Path(html.unescape(i)).name) for i in re.findall(r'<img[^>]+src="([^"]+)"',t))
    return hashlib.md5(norm(t).encode()).hexdigest(),seq
csig={sig(p) for p in (C/'reports').rglob('*.html')}
ch={sha(p) for p in (C/'images').rglob('*') if p.is_file()}
dele=[];keep=[]
for z in sorted(d for d in O.iterdir() if d.is_dir() and d.name!='GoChina.consolidated'):
    for p in z.rglob('*'):
        if not p.is_file() or p.suffix=='.csv' or p.name=='.DS_Store': continue
        rel=p.relative_to(z); c=C/rel
        if c.is_file() and filecmp.cmp(p,c,shallow=False): ok=True
        elif rel.parts[0]=='reports' and p.suffix=='.html': ok=sig(p) in csig
        elif rel.parts[0]=='images': ok=sha(p) in ch
        else: ok=False
        (dele if ok else keep).append(p)
print('deletable',len(dele),'| kept',len(keep))
import collections
print(collections.Counter((p.parts[2],p.suffix) for p in keep).most_common(8))
for p in keep[:6]: print(' keep',p)
if go:
    for p in dele: p.unlink()
    n=0
    for z in O.iterdir():
        if z.is_dir() and z.name!='GoChina.consolidated':
            for d,_,_ in sorted(os.walk(z),key=lambda x:-len(x[0])):
                dp=Path(d)
                if not [x for x in dp.iterdir() if x.name!='.DS_Store']:
                    (dp/'.DS_Store').unlink(missing_ok=True); dp.rmdir(); n+=1
    print('deleted',len(dele),'empty dirs removed',n)
