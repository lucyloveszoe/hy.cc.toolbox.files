#!/usr/bin/env python3 -I
"""Add summary + manifest rows for the Word-derived reports of Great_Redarmy (per-report images/<stem>/manifest.csv). Dry run unless --go."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD, SCRATCH
import os,re,sys,html,csv,io,shutil,unicodedata
GO='--go' in sys.argv
d=(DD+'/mc_2026.11.19/html/topics/Great_Redarmy'); R=d+'/reports'
BK=(SCRATCH+'/4d62ed09-50fc-4936-af43-187ad00942db/scratchpad/bak_redarmy')
nfc=lambda s:unicodedata.normalize('NFC',os.path.normpath(s))
def rd(p):
    raw=open(p,'rb').read(); return list(csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''))),raw.startswith(b'\xef\xbb\xbf'),('\r\n' if b'\r\n' in raw else '\n')
sp=f'{d}/Great_Redarmy_summary.csv'; mp=f'{d}/Great_Redarmy_images_manifest.csv'
sm,b1,e1=rd(sp); mn,b2,e2=rd(mp); print('summary cols',sm[0],'eol',repr(e1),'| manifest cols',mn[0],'eol',repr(e2))
ko=sm[0].index('output'); listed={nfc(os.path.join(d,r[ko])) for r in sm[1:] if len(r)>ko and r[ko]}
newsum=[]; newman=[]
mout={nfc(os.path.join(d,r[mn[0].index('output')])) for r in mn[1:] if len(r)>mn[0].index('output') and r[mn[0].index('output')]}
for f in sorted(os.listdir(R)):
    if not f.endswith('.html') or nfc(f'{R}/{f}') in listed: continue
    stem=f[:-5]; t=open(f'{R}/{f}',encoding='utf-8').read()
    srcs=[html.unescape(x) for x in re.findall(r'<img[^>]*?src="([^"]+)"',t)]; dirs={os.path.dirname(s) for s in srcs}
    assert len(dirs)==1; idir=os.path.normpath(os.path.join(R,dirs.pop())); pm=f'{idir}/manifest.csv'; assert os.path.exists(pm),pm
    names=set(os.path.basename(s) for s in srcs)
    cnt=0
    for r in csv.DictReader(open(pm,encoding='utf-8-sig')):
        img=r['image']; cand=[x for x in os.listdir(idir) if os.path.splitext(x)[0]==os.path.splitext(img)[0] and x!='manifest.csv']
        assert len(cand)==1,(img,cand); out=os.path.relpath(f'{idir}/{cand[0]}',d)
        assert nfc(f'{d}/{out}') not in mout
        newman.append([r['original_url'],'copied: carved from .doc (original url)',out]); cnt+=1
    assert cnt==len(names),(f,cnt,len(names))
    newsum.append([stem+'.doc','doc','','',str(cnt),'','reports/'+f]+['']*(len(sm[0])-7))
print('pages to add',len(newsum),[x[0][:30] for x in newsum],'| manifest rows to add',len(newman))
if not GO: print('DRY'); sys.exit()
os.makedirs(BK); shutil.copy2(sp,BK); shutil.copy2(mp,BK)
sm+=newsum; mn+=newman
for p,rows,b,e in ((sp,sm,b1,e1),(mp,mn,b2,e2)):
    with open(p,'w',encoding='utf-8-sig' if b else 'utf-8',newline='') as f: csv.writer(f,lineterminator=e).writerows(rows)
print('DONE')
