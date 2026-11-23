#!/usr/bin/env python3 -I
import os,re,html,subprocess,collections,hashlib,importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
R=q.BASE+'/merges/mcjt-total/reports/'
rep=[]
for fn in sorted(os.listdir(R)):
    if not fn.endswith('.html'): continue
    t,srcs=q.load(R+fn); imgs=[q.canon(os.path.join(R,s)) for s in srcs]
    rep.append(dict(fn=fn,text=t,imgs=imgs,seq=[q.md5file(i) for i in imgs],n=len(t)))
print('reports',len(rep))
# exact (text+images) re-check
g=collections.defaultdict(list)
for r in rep: g[hashlib.md5((r['text']+'|'+','.join(r['seq'])).encode()).hexdigest()].append(r['fn'])
print('exact groups',sum(1 for v in g.values() if len(v)>1))
cand=[r for r in rep if r['n']>=300]
G=[{r['text'][i:i+8] for i in range(len(r['text'])-7)} for r in cand]
inv=collections.defaultdict(list)
for i,s in enumerate(G):
    for x in list(s)[::7]: inv[x].append(i)
pairs=set()
for i,s in enumerate(G):
    c=collections.Counter()
    for x in list(s)[::7]:
        for j in inv[x]:
            if j>i: c[j]+=1
    for j,n in c.items():
        if n>=4: pairs.add((i,j))
print('candidate pairs',len(pairs))
dimc={}
def dim(p):
    if p not in dimc:
        o=subprocess.run(['sips','-g','pixelWidth','-g','pixelHeight',p],capture_output=True,text=True).stdout.split()
        try: dimc[p]=(int(o[o.index('pixelWidth:')+1]),int(o[o.index('pixelHeight:')+1]))
        except Exception: dimc[p]=(0,0)
    return dimc[p]
def trivial(p): 
    w,h=dim(p); return max(w,h)<=150 or os.path.getsize(p)<8000
out=[]
for i,j in pairs:
    a,b=cand[i],cand[j]; inter=len(G[i]&G[j]); jac=inter/len(G[i]|G[j]); cont=inter/min(len(G[i]),len(G[j]))
    if not(jac>0.5 and cont>0.8): continue
    ha={h:p for h,p in zip(a['seq'],a['imgs'])}; hb={h:p for h,p in zip(b['seq'],b['imgs'])}
    ua=[p for h,p in ha.items() if h not in hb]; ub=[p for h,p in hb.items() if h not in ha]
    ra=[p for p in ua if not trivial(p)]; rb=[p for p in ub if not trivial(p)]
    if not ua and not ub: cls='same-images'
    elif not ra and not rb: cls='extras-trivial-both'
    elif not ra: cls='A-thin' 
    elif not rb: cls='B-thin'
    else: cls='mixed-real'
    out.append((cls,a['fn'],b['fn'],a['n'],b['n'],len(set(a['seq'])),len(set(b['seq'])),len(set(a['seq'])&set(b['seq'])),len(ra),len(rb),jac,cont))
print('pairs',len(out),collections.Counter(o[0] for o in out))
with open('rescan_total.tsv','w',encoding='utf-8') as f:
    f.write('class\tA\tB\tcharsA\tcharsB\timgsA\timgsB\tcommon\trealOnlyA\trealOnlyB\tjaccard\tcontain\n')
    for o in sorted(out): f.write('\t'.join(str(x) if not isinstance(x,float) else f'{x:.2f}' for x in o)+'\n')
