#!/usr/bin/env python3 -I
"""After the user deleted report files by hand: blank the summary rows, move the images that no report links any more
to a quarantine, tag the manifest rows. Dry run unless --go."""
import os,sys,shutil,collections,importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
GO='--go' in sys.argv; T=q.BASE+'/merges/mcjt-total'; QR='/Users/hany/Downloads/quarantine.removed.2026.11.22'
# 1 summary rows whose report is gone
csvs=[p for p in q.all_csvs()]
gone=set()
for p in csvs:
    rows,_,_=q.read_csv(p)
    if not rows or 'output' not in rows[0]: continue
    k=rows[0].index('output')
    for r in rows[1:]:
        if len(r)>k and r[k] and r[k].endswith('.html') and not os.path.exists(os.path.join(os.path.dirname(p),r[k])): gone.add(q.canon(os.path.join(os.path.dirname(p),r[k])))
print('missing reports',len(gone)); [print('  ',os.path.basename(g)[:70]) for g in sorted(gone)]
# 2 images no report links any more (all roots)
linked=set()
for g in ('merges','topics','locations'):
    for r in q.scan(g):
        for i in r['imgs']: linked.add(i)
orph=[]
for d in os.listdir(q.BASE+'/merges'):
    base=f'{q.BASE}/merges/{d}/images'
    for dp,_,fs in os.walk(base):
        orph+=[os.path.join(dp,f) for f in fs if f not in('.DS_Store','manifest.csv') and q.canon(os.path.join(dp,f)) not in linked]
orphs={q.canon(o) for o in orph}
print('images no report links:',len(orphs),'bytes',sum(os.path.getsize(o) for o in orph))
# 3 rows to change
ch={}; n=0
for p in csvs:
    rows,bom,eol=q.read_csv(p)
    if not rows or 'output' not in rows[0]: continue
    k=rows[0].index('output'); hit=[]
    for ri,r in enumerate(rows[1:],1):
        if len(r)>k and r[k]:
            c=q.canon(os.path.join(os.path.dirname(p),r[k]))
            if c in gone or c in orphs: hit.append((ri,c in gone))
    if hit: ch[p]=(rows,bom,eol,hit); n+=len(hit)
print('csv files',len(ch),'rows',n,[ (os.path.basename(p),len(v[3])) for p,v in ch.items()])
exp=(5,71)
if not GO: print('DRY'); sys.exit()
assert not os.path.exists(QR); os.makedirs(QR+'/files'); os.makedirs(QR+'/bak_csv')
for p in ch:
    d=QR+'/bak_csv/'+os.path.relpath(p,q.DATA); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copy2(p,d)
for p,(rows,bom,eol,hit) in ch.items():
    h=rows[0]; k=h.index('output'); man='status' in h
    if not man and 'note' not in h: h.append('note'); [r.append('') for r in rows[1:]]
    for ri,isrep in hit:
        r=rows[ri]
        if man: s=h.index('status'); r[s]=(r[s] if len(r)>s else '')+q.TAG_STATUS
        else:
            nn=h.index('note')
            while len(r)<=nn: r.append('')
            r[nn]='[report removed by user; images moved to quarantine]'
        r[k]=''
    q.write_csv(p,rows,bom,eol)
for o in sorted(orph):
    d=QR+'/files/'+os.path.relpath(o,q.BASE); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.move(o,d)
open(QR+'/images_moved.txt','w',encoding='utf-8').write(''.join(os.path.relpath(o,q.BASE)+'\n' for o in sorted(orph)))
print('DONE')
