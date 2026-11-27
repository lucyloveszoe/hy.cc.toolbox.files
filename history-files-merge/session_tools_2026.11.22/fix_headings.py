#!/usr/bin/env python3 -I
"""Set <title> and <h1> of the renamed reports to the new file-name stem. Dry run unless --go."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD
import os,re,sys,html,shutil
GO='--go' in sys.argv
R=(DD+'/mc_2026.11.19/html/merges/mcjt-total/reports/')
BK='bak_headings'
pl=[l.rstrip('\n').split('\t') for l in open('bak_rename_csv/renamed.tsv',encoding='utf-8')]
T=re.compile(r'(?is)(<title[^>]*>)(.*?)(</title>)'); H1=re.compile(r'(?is)(<h1[^>]*>)(.*?)(</h1>)')
plan=[]; bad=0
for old,new in pl:
    p=R+new
    if not os.path.exists(p): print('missing',new); bad+=1; continue
    t=open(p,encoding='utf-8').read(); mt=T.search(t); mh=H1.search(t)
    num=old[:-5]
    ok = mt and mh and html.unescape(mt.group(2)).strip()==num and html.unescape(mh.group(2)).strip()==num
    if not ok: print('heading is not the old number:',new[:30],mt and mt.group(2)[:20],mh and mh.group(2)[:20]); bad+=1; continue
    stem=new[:-5]; esc=html.escape(stem,quote=False)
    t2=T.sub(lambda m:m.group(1)+esc+m.group(3),t,count=1); t2=H1.sub(lambda m:m.group(1)+esc+m.group(3),t2,count=1)
    # body outside head/h1 must be identical
    strip=lambda s:H1.sub('',re.sub(r'(?is)<head>.*?</head>','',s),count=1)
    assert strip(t)==strip(t2) and t.count('<img')==t2.count('<img')
    plan.append((p,t2))
print('reports',len(pl),'to update',len(plan),'problems',bad)
if not GO or bad: print('DRY' if not GO else 'ABORT'); sys.exit()
os.makedirs(BK)
for p,t2 in plan:
    shutil.copy2(p,BK+'/'+os.path.basename(p)); open(p,'w',encoding='utf-8',newline='').write(t2)
print('DONE')
