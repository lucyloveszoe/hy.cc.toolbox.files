#!/usr/bin/env python3 -I
import os,subprocess,importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
R=q.BASE+'/merges/mcjt-total/reports/'
def imgs(fn):
    t,srcs=q.load(R+fn); return [q.canon(os.path.join(R,s)) for s in srcs]
def dim(p):
    o=subprocess.run(['sips','-g','pixelWidth','-g','pixelHeight',p],capture_output=True,text=True).stdout.split()
    return (int(o[o.index('pixelWidth:')+1]),int(o[o.index('pixelHeight:')+1]))
def show(a,b):
    A=imgs(a);B=imgs(b); ha={q.md5file(i):i for i in A}; hb={q.md5file(i):i for i in B}
    ua=[ha[h] for h in ha if h not in hb]; ub=[hb[h] for h in hb if h not in ha]
    for tag,L in (('onlyA',ua),('onlyB',ub)):
        for i in L: print(tag,os.path.basename(i)[:28],dim(i),os.path.getsize(i))
fs=os.listdir(R)
a=[f for f in fs if '盗梦空间' in f and '三多' in f][0]; b=[f for f in fs if '盗梦空间' in f and '53' in f and '三多' not in f][0]; show(a,b)
c=sorted(f for f in fs if '山路18弯' in f); print(); show(c[0],c[1])
