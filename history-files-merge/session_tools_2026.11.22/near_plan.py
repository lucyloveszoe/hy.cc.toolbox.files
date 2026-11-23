#!/usr/bin/env python3 -I
import csv, os, re, html, collections, sys
sys.argv=['x']; 
import importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
BASE=q.BASE
def text(p):
    t=open(p,encoding='utf-8',errors='replace').read()
    ti=re.search(r'(?is)<title>(.*?)</title>',t); title=html.unescape(ti.group(1)).strip() if ti else ''
    b=re.sub(r'(?is)<head>.*?</head>','',t); b=re.sub(r'(?is)<h1[^>]*>.*?</h1>','',b,count=1)
    return title, re.sub(r'\s+','',html.unescape(re.sub(r'<[^>]+>','',b))).lower()
gr=lambda t:{t[i:i+8] for i in range(max(0,len(t)-7))}
rows=list(csv.DictReader(open('scan_near_internal.tsv',encoding='utf-8'),delimiter='\t'))
R={}
for r in q.scan('merges'): R[(r['root'],r['file'])]=r
out=[]; cache={}
def info(k):
    if k not in cache:
        r=R[k]; t,x=text(r['path']); cache[k]=(t,x,gr(x),set(r['seq']))
    return cache[k]
for w in rows:
    a=(w['rootA'],w['fileA']); b=(w['rootB'],w['fileB'])
    if a not in R or b not in R: out.append((w,'GONE','','',0)); continue
    ta,xa,ga,ia=info(a); tb,xb,gb,ib=info(b)
    oa,ob=len(ia-ib),len(ib-ia)
    if oa and ob: dec,cand,keep='KEEP-BOTH(mixed)',None,None
    else:
        # candidate = side without extra image; if same images, shorter text
        if oa==0 and ob==0: cand,keep=(a,b) if (len(xa),len(a[1]))<=(len(xb),len(b[1])) else (b,a)
        elif oa==0: cand,keep=a,b
        else: cand,keep=b,a
        cx,kx=(xa,xb) if cand==a else (xb,xa); cg,kg=(ga,gb) if cand==a else (gb,ga)
        share=len(cg&kg)/max(1,len(cg))
        if share>=0.90 and len(cx)<=len(kx)*1.0+0: dec='REMOVE'
        elif share>=0.90: dec='HOLD(cand has more text)'
        else: dec='KEEP(share %.2f)'%share
        out.append((w,dec,cand,keep,share)); continue
    out.append((w,dec,None,None,0))
# chain resolution
rem={o[2] for o in out if o[1]=='REMOVE'}
fin=[]
for w,dec,c,k,s in out:
    if dec=='REMOVE' and k in rem: dec='HOLD(kept side also removed)'
    fin.append((w,dec,c,k,s))
cnt=collections.Counter(d.split('(')[0] for _,d,_,_,_ in fin); print(cnt)
rm=sorted({c for w,d,c,k,s in fin if d=='REMOVE'}); print('distinct reports to remove:',len(rm))
with open('near_plan.tsv','w',encoding='utf-8') as f:
    f.write('decision\tremove_root\tremove_file\tkeep_root\tkeep_file\tshare\n')
    for w,d,c,k,s in fin:
        f.write(f"{d}\t{c[0] if c else ''}\t{c[1] if c else ''}\t{k[0] if k else ''}\t{k[1] if k else ''}\t{s:.2f}\n")
rem=set(rm)
# exclusive images of removable reports
stay=collections.defaultdict(int); allr=q.scan('topics')+q.scan('locations')+list(R.values())
rpaths={R[c]['path'] for c in rem}
for r in allr:
    if r['path'] in rpaths: continue
    for i in r['imgs']: stay[i]+=1
ex=set(i for c in rem for i in R[c]['imgs'] if i not in stay)
print('exclusive images:',len(ex))
for n,(w,d,c,k,s) in enumerate(fin,1):
    ta=info(c)[0] if c else ''
    print(n,d,'|',w['rootA'],w['charsA'],w['imgsA'],'~',w['rootB'],w['charsB'],w['imgsB'],'| common',w['common'],'only',w['onlyA'],w['onlyB'],'| share %.2f'%s,'|',(ta or w['fileA'])[:24])
