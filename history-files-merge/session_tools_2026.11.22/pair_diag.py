#!/usr/bin/env python3 -I
import os,re,html,sys,importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
R=q.BASE+'/merges/mcjt-total/reports/'
def info(fn):
    p=R+fn; t,srcs=q.load(p); imgs=[q.canon(os.path.join(R,s)) for s in srcs]; seq=[q.md5file(i) for i in imgs]
    return t,seq
gr=lambda t:{t[i:i+8] for i in range(max(0,len(t)-7))}
def cmp(a,b):
    ta,sa=info(a); tb,sb=info(b); ga,gb=gr(ta),gr(tb); inter=len(ga&gb)
    print(f'chars {len(ta)} / {len(tb)} | imgs {len(sa)}({len(set(sa))} uniq) / {len(sb)}({len(set(sb))}) | common imgs {len(set(sa)&set(sb))} onlyA {len(set(sa)-set(sb))} onlyB {len(set(sb)-set(sa))} | jaccard {inter/len(ga|gb):.2f} contain {inter/min(len(ga),len(gb)):.2f}')
fs=sorted(os.listdir(R))
def find(*frag): 
    r=[f for f in fs if all(x in f for x in frag)]; return r
A=find('盗梦空间','三多'); B=[f for f in find('盗梦空间','53') if f not in A]
print(A,B)
for a in A:
    for b in B: cmp(a,b)
C=find('山路18弯'); print(C)
for i in range(len(C)):
    for j in range(i+1,len(C)): print(C[i][:30],'~',C[j][:30]); cmp(C[i],C[j])
