"""One-off repair of a to_reports_merged.py run where SET had been turned into an absolute path (fixed in the script)."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD
import os,sys,re,csv,shutil
P=os.path.abspath('.');W=P+'/141';D=(DD+'/141_2026.11.24/reports_merged')
os.makedirs(D+'/141/images/141');BADI='images/'+W+'/';REL=os.path.relpath(W,D)+'/'   # ../../../../Documents/.../141/
names=os.listdir(W);pages=[n for n in names if n.endswith('.html')];imgs=[n for n in names if not n.endswith('.html')]
print(len(pages),len(imgs))
for n in imgs: os.rename(W+'/'+n,D+'/141/images/141/'+n)
n_src=0
for n in pages:
    t=open(W+'/'+n,encoding='utf-8').read();t2=t.replace(BADI,'images/141/');n_src+=t.count(BADI)
    assert BADI not in t2
    open(D+'/141/'+n,'w',encoding='utf-8',newline='').write(t2);os.unlink(W+'/'+n)
os.rmdir(W);print('src rewritten',n_src)
for name in('summary','images_manifest'):
    f=f'141_{name}.csv';rows=list(csv.reader(open(f,encoding='utf-8-sig',newline='')));oi=rows[0].index('output');ch=0
    for r in rows[1:]:
        o=r[oi]
        if o:
            assert o.startswith(REL),o
            b=o[len(REL):];r[oi]='141/'+b if o.endswith('.html') else '141/images/141/'+b;ch+=1
    with open(D+'/'+f,'w',encoding='utf-8-sig',newline='') as g: csv.writer(g,lineterminator='\n').writerows(rows)
    os.unlink(f);print(f,ch)
