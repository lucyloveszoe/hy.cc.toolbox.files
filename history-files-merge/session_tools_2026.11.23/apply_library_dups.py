"""Delete the exact-duplicate reports listed in a plan.json (from report_vs_library.py), then the images no remaining
report uses, then CSV rows whose output file is gone. Usage: python3 -I apply_library_dups.py <plan.json> <csv-backup-dir> [--go]"""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import PROJ
import re,sys,csv,json,html,os,shutil
from pathlib import Path
C=Path((PROJ+'/outputs/GoChina.consolidated'))
plan=json.load(open(sys.argv[1])); bk=Path(sys.argv[2]); go='--go' in sys.argv
dele={Path(a) for a,_ in plan['exact']}
assert all(p.is_file() and str(p).startswith(str(C/'reports')) for p in dele)
imgs=lambda p:{(p.parent/html.unescape(i)).resolve() for i in re.findall(r'<img[^>]+src="([^"]+)"',p.read_text(encoding='utf-8'))}
gone=set(); 
for p in dele: gone|=imgs(p)
keep=set()
for p in (C/'reports').rglob('*.html'):
    if p not in dele: keep|=imgs(p)
di=sorted(i for i in gone-keep if i.is_file())
print('reports to delete',len(dele),'images to delete',len(di),'images still used',len(gone&keep))
if not go: sys.exit()
bk.mkdir(parents=True)
for f in C.glob('*.csv'): shutil.copy2(f,bk/f.name)
for p in dele: p.unlink()
for i in di: i.unlink()
nrows=0
for f in sorted(C.glob('*.csv')):
    raw=f.read_bytes(); eol='\r\n' if b'\r\n' in raw else '\n'
    rows=list(csv.reader(open(f,encoding='utf-8-sig',newline='')))
    h=rows[0]; oi=h.index('output'); out=[h]
    for r in rows[1:]:
        if r[oi] and not (C/r[oi]).exists(): nrows+=1; continue
        out.append(r)
    with open(f,'w',encoding='utf-8-sig',newline='') as fh: csv.writer(fh,lineterminator=eol).writerows(out)
n=0
for d,_,_ in sorted(os.walk(C),key=lambda x:-len(x[0])):
    q=Path(d)
    if q!=C and not [x for x in q.iterdir() if x.name!='.DS_Store']:
        (q/'.DS_Store').unlink(missing_ok=True); q.rmdir(); n+=1
print('deleted',len(dele),'reports',len(di),'images; CSV rows pruned',nrows,'empty dirs',n)
