#!/usr/bin/env python3 -I
import os,hashlib,pickle,shutil,sys
S='/Users/hany/Downloads/data/2018.06.18_report_word_doc_txt_imgs'
GO='--go' in sys.argv
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
out=pickle.load(open('contained_dirs.pkl','rb')); free=pickle.load(open('free_groups.pkl','rb'))
log=[]; nf=0; nb=0
# A: whole folders — every file must have a byte-identical copy in the host folder
for d,host in out:
    hh={}
    for dp,_,fs in os.walk(host):
        for f in fs:
            if f!='.DS_Store': hh[sha(os.path.join(dp,f))]=os.path.join(dp,f)
    for dp,_,fs in os.walk(d):
        for f in fs:
            if f=='.DS_Store': continue
            p=os.path.join(dp,f); h=sha(p); assert h in hh,('no kept copy',p)
            log.append((p,hh[h],h)); nf+=1; nb+=os.path.getsize(p)
print('A whole folders:',len(out),'files',nf,'MB',nb//10**6)
# B: single extra copies (keep shortest path, then sorted); kept copy must exist and be identical
single=[]; nb2=0; keeps={}
for h,L in free:
    L=sorted(L,key=lambda p:(len(p),p)); keep=L[0]
    assert os.path.exists(keep) and sha(keep)==h
    for p in L[1:]:
        if os.path.exists(p): assert sha(p)==h; single.append((p,keep)); keeps[h]=keep; nb2+=os.path.getsize(p)
print('B single copies:',len(single),'MB',nb2//10**6)
rm={p for p,_ in single}
fixed=[]
for p,kp,h in log:
    if kp in rm:
        assert h in keeps and os.path.exists(keeps[h]) and keeps[h] not in rm
        kp=keeps[h]
    fixed.append((p,kp,h))
log=fixed
assert not (rm&{k for _,k in single}) and not (rm&{k for _,k,_ in log})
if not GO: print('DRY'); sys.exit()
open('dup_deleted_log.tsv','w',encoding='utf-8').write('removed\tkept\n'+''.join(f'{os.path.relpath(a,S)}\t{os.path.relpath(b,S)}\n' for a,b in [(x,y) for x,y,_ in log]+single))
for d,_ in out: shutil.rmtree(d)
for p,_ in single: os.remove(p)
# empty folders (a lone .DS_Store does not count)
gone=0
for dp,dn,fs in os.walk(S,topdown=False):
    if dp==S: continue
    if not os.listdir(dp) or os.listdir(dp)==['.DS_Store']:
        if os.listdir(dp): os.remove(dp+'/.DS_Store')
        os.rmdir(dp); gone+=1
print('DONE; empty folders removed',gone)
