#!/usr/bin/env python3 -I
import csv, os, sys, shutil, collections, importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
GO='--go' in sys.argv
QN=q.QUAR+'/near'
m=q.scan('merges'); lib=q.scan('topics')+q.scan('locations')
R={(r['root'],r['file']):r for r in m}
plan={}
for w in csv.DictReader(open('near_plan.tsv',encoding='utf-8'),delimiter='\t'):
    if w['decision']=='REMOVE': plan[(w['remove_root'],w['remove_file'])]=(w['keep_root'],w['keep_file'])
assert all(k in R for k in plan) and all(v in R for v in plan.values())
assert not (set(plan)&set(plan.values())), 'kept side removed'
removed=[(R[k],R[v]['path'],'NEAR') for k,v in plan.items()]
rem_paths={q.canon(r['path']) for r,_,_ in removed}
stay=collections.defaultdict(set); stay_md5=set()
for r in m+lib:
    if q.canon(r['path']) in rem_paths: continue
    for i,h in zip(r['imgs'],r['seq']): stay[i].add(r['path']); stay_md5.add(h)
mv={i for r,_,_ in removed for i in r['imgs'] if i not in stay and os.path.exists(i)}
# near copies: images of removed report that the kept lacks are not allowed (rule), so all md5s must stay
nocopy=[i for i in mv if q.md5file(i) not in stay_md5]
print('reports',len(removed),'images to move',len(mv),'no stay copy',len(nocopy)); assert not nocopy
mf={q.canon(r['path']):k for r,k,_ in removed}
ch={}; n=0
for p in q.all_csvs():
    rows,bom,eol=q.read_csv(p)
    if not rows or 'output' not in rows[0]: continue
    k=rows[0].index('output'); hit=[]
    for ri,r in enumerate(rows[1:],1):
        if len(r)>k and r[k]:
            t=q.canon(os.path.join(os.path.dirname(p),r[k]))
            if t in mf or t in mv: hit.append((ri,t))
    if hit: ch[p]=(rows,bom,eol,hit); n+=len(hit)
print('csv files',len(ch),'rows',n)
if not GO: print('DRY'); sys.exit()
assert not os.path.exists(QN); os.makedirs(QN+'/files'); os.makedirs(QN+'/bak_csv')
for p in ch:
    d=QN+'/bak_csv/'+os.path.relpath(p,q.DATA); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copy2(p,d)
with open(QN+'/removed_to_kept.tsv','w',encoding='utf-8') as f:
    f.write('kind\tremoved\tkept\n')
    for r,k,kd in removed: f.write(f"NEAR\t{os.path.relpath(r['path'],q.BASE)}\t{os.path.relpath(k,q.BASE)}\n")
open(QN+'/images_moved.txt','w',encoding='utf-8').write(''.join(os.path.relpath(i,q.BASE)+'\n' for i in sorted(mv)))
for p,(rows,bom,eol,hit) in ch.items():
    h=rows[0]; k=h.index('output'); man='status' in h
    if not man and 'note' not in h:
        h.append('note'); [r.append('') for r in rows[1:]]
    for ri,t in hit:
        r=rows[ri]
        if man:
            s=h.index('status'); r[s]=(r[s] if len(r)>s else '')+q.TAG_STATUS
        else:
            nn=h.index('note')
            while len(r)<=nn: r.append('')
            kp=mf.get(t); r[nn]=f"[near duplicate of {os.path.basename(kp)}; moved to quarantine]" if kp else q.TAG_STATUS.strip()
        r[k]=''
    q.write_csv(p,rows,bom,eol)
for pth in list(rem_paths)+sorted(mv):
    d=QN+'/files/'+os.path.relpath(pth,q.BASE); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.move(pth,d)
print('DONE')
