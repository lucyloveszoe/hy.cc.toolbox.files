"""Layout A root (reports/<zip>/**.html, images/<zip>/**, <zip>_summary.csv, <zip>_images_manifest.csv) -> flat layout B
(PROCESSING_RULES 40.5/62.3): <dest>/<set>/<page>.html, <dest>/<set>/images/<set>/<img>, <dest>/<set>_summary.csv,
<dest>/<set>_images_manifest.csv. Names stay plain; a name that clashes (case-insensitive) gets '<zip>__' in ALL its members.
Usage: to_reports_merged.py <A root> <dest> <set> <backup dir> [--go]"""
import os,sys,csv,glob,html,re,shutil,collections
SRC,DEST,BK=[os.path.abspath(a) for a in (sys.argv[1],sys.argv[2],sys.argv[4])];SET=sys.argv[3];GO='--go' in sys.argv
def walk(d,ext=None):
    out=[]
    for dp,_,fn in os.walk(d):
        for f in fn:
            if f=='.DS_Store' or (ext and not f.endswith(ext)): continue
            out.append(os.path.join(dp,f))
    return sorted(out)
def plan(files,top):
    zipof=lambda p:os.path.relpath(p,top).split(os.sep)[0]
    cnt=collections.Counter(os.path.basename(p).lower() for p in files);m={}
    for p in files:
        b=os.path.basename(p);m[p]=b if cnt[b.lower()]==1 else f'{zipof(p)}__{b}'
    c=collections.Counter(v.lower() for v in m.values())
    for p in files:   # same name twice inside one zip: add the parent folder
        if c[m[p].lower()]>1: m[p]=f'{zipof(p)}__{os.path.basename(os.path.dirname(p))}__{os.path.basename(p)}'
    c=collections.Counter(v.lower() for v in m.values());bad=[v for v,n in c.items() if n>1]
    long=[v for v in m.values() if len(v.encode())>250]
    return m,bad,long,sum(1 for v,p in zip(m.values(),files) if v!=os.path.basename(p))
P=walk(SRC+'/reports','.html');I=walk(SRC+'/images')
pm,pbad,plong,ppre=plan(P,SRC+'/reports');im,ibad,ilong,ipre=plan(I,SRC+'/images')
print('pages',len(P),'prefixed',ppre,'unresolved clashes',len(pbad),'too long',len(plong))
print('images',len(I),'prefixed',ipre,'unresolved clashes',len(ibad),'too long',len(ilong))
if pbad or ibad or plong or ilong or not GO: sys.exit(0 if not GO else 1)
OUTD=os.path.join(DEST,SET);OUTI=os.path.join(OUTD,'images',SET)
assert not os.path.exists(OUTD),OUTD
os.makedirs(OUTI)
imgnew={p:os.path.join(OUTI,v) for p,v in im.items()}
pagenew={p:os.path.join(OUTD,v) for p,v in pm.items()}
distinct={}
for p in P:
    t=open(p,encoding='utf-8').read();d=os.path.dirname(p);s=set()
    def sub(m):
        tgt=os.path.normpath(os.path.join(d,html.unescape(m.group(2))))
        assert tgt in im,(p,tgt)
        s.add(tgt);return m.group(1)+html.escape('images/%s/%s'%(SET,im[tgt]),quote=True)+m.group(3)
    t=re.sub(r'(<img[^>]*?\ssrc=")([^"]+)(")',sub,t)
    open(pagenew[p],'w',encoding='utf-8',newline='').write(t);distinct[p]=len(s)
# CSVs
os.makedirs(BK,exist_ok=True)
rel=lambda p:os.path.relpath(p,DEST)
rows_s=[];rows_m=[];hs=hm=None
for c in sorted(glob.glob(SRC+'/*.csv')):
    raw=open(c,'rb').read();rows=list(csv.reader(open(c,encoding='utf-8-sig',newline='')));h=rows[0]
    oi=h.index('output');isS=c.endswith('_summary.csv')
    if isS: hs=hs or h
    else: hm=hm or h
    for r in rows[1:]:
        o=r[oi]
        if o:
            ab=os.path.join(SRC,o)
            if isS: r[oi]=rel(pagenew[ab]) ;
            else: r[oi]=rel(imgnew[ab])
        elif isS: continue          # no output (txt/unsupported page handled elsewhere): not carried over (40.4)
        (rows_s if isS else rows_m).append(r)
for name,h,rows in (('summary',hs,rows_s),('images_manifest',hm,rows_m)):
    with open(os.path.join(DEST,f'{SET}_{name}.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(h);w.writerows(rows)
print('summary rows',len(rows_s),'manifest rows',len(rows_m))
# fix images_copied to distinct images per page
sp=os.path.join(DEST,f'{SET}_summary.csv');rows=list(csv.reader(open(sp,encoding='utf-8-sig',newline='')))
oi=rows[0].index('output');ii=rows[0].index('images_copied');dn={rel(pagenew[p]):distinct[p] for p in P};ch=0
for r in rows[1:]:
    if r[oi] in dn and str(dn[r[oi]])!=r[ii]: r[ii]=str(dn[r[oi]]);ch+=1
with open(sp,'w',encoding='utf-8-sig',newline='') as f: csv.writer(f,lineterminator='\n').writerows(rows)
print('images_copied adjusted',ch)
# move images, back up + remove old pages and CSVs
for p,n in imgnew.items(): os.rename(p,n)
for c in glob.glob(SRC+'/*.csv'): shutil.move(c,os.path.join(BK,os.path.basename(c)))
for p in P: os.unlink(p)
for dp,dn_,fn in os.walk(SRC,topdown=False):
    if '.DS_Store' in fn and len(fn)==1: os.unlink(os.path.join(dp,'.DS_Store'))
    if dp!=SRC and not os.listdir(dp): os.rmdir(dp)
print('left in source:',os.listdir(SRC))
