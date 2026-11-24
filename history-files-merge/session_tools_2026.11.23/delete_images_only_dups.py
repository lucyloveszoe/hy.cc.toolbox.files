"""Delete files in ~/Downloads/images-only that have a byte-identical copy (SHA-256, then cmp) anywhere in ~/Downloads/images-only.done;
prune empty sub-folders. Dry run without --go. (PROCESSING_RULES 62.7)"""
import hashlib,filecmp,os,sys,collections
from pathlib import Path
D=Path.home()/'Downloads'; A=D/'images-only'; go='--go' in sys.argv
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
idx={}
for p in (D/'images-only.done').rglob('*'):
    if p.is_file() and p.name!='.DS_Store': idx.setdefault(sha(p),p)
files=[p for p in A.rglob('*') if p.is_file() and p.name!='.DS_Store']
dup=[(p,idx[sha(p)]) for p in files if sha(p) in idx]
print(len(files),'files;',len(dup),'duplicates of images-only.done')
print(collections.Counter(p.relative_to(A).parts[0] for p,_ in dup).most_common(5))
if go:
    n=bad=0
    for p,k in dup:
        if filecmp.cmp(p,k,shallow=False): p.unlink(); n+=1
        else: bad+=1
    d=0
    for dp,_,_ in sorted(os.walk(A),key=lambda x:-len(x[0])):
        q=Path(dp)
        if q!=A and not [x for x in q.iterdir() if x.name!='.DS_Store']: (q/'.DS_Store').unlink(missing_ok=True); q.rmdir(); d+=1
    print('deleted',n,'cmp mismatches',bad,'empty dirs removed',d)
