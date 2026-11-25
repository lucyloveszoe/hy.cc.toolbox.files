"""Merge byte-identical images of a layout-A root (PROCESSING_RULES 40.5, 63.x): one file per SHA-256 in images/,
page <img src> and manifest `output` repointed, images.only files that duplicate an image (or each other) deleted.
Usage: merge_identical_images.py <root> <backup dir> [--go]   (dry run without --go)"""
import os,sys,csv,glob,html,re,hashlib,filecmp,shutil,collections
R=os.path.abspath(sys.argv[1]);BK=sys.argv[2];GO='--go' in sys.argv
os.chdir(R)
def sha(p):
    m=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): m.update(b)
    return m.hexdigest()
def files(d): return sorted(os.path.join(dp,f) for dp,_,fn in os.walk(d) for f in fn if f!='.DS_Store')
G=collections.defaultdict(list)
for p in files('images'): G[sha(p)].append(p)
keep={};imap={}   # imap: dup image -> kept image
for x,v in G.items():
    v.sort(key=lambda p:(len(p),p)); keep[x]=v[0]
    for d in v[1:]: imap[d]=v[0]
omap={}           # images.only dup -> kept path (images/ copy or first images.only)
O=collections.defaultdict(list)
for p in files('images.only'): O[sha(p)].append(p)
for x,v in O.items():
    if x in keep:
        for d in v: omap[d]=keep[x]
    else:
        for d in v[1:]: omap[d]=v[0]
print('images/ duplicates to delete:',len(imap),'| images.only duplicates to delete:',len(omap))
if not GO: sys.exit()
os.makedirs(BK,exist_ok=True)
allmap=dict(imap);allmap.update(omap)
# pages
nchg=0;pagedist={}
for p in glob.glob('reports/**/*.html',recursive=True):
    t=open(p,encoding='utf-8').read();d=os.path.dirname(p);srcs=set()
    def sub(m):
        tgt=os.path.normpath(os.path.join(d,html.unescape(m.group(2))))
        new=imap.get(tgt,tgt);srcs.add(new)
        if new==tgt: return m.group(0)
        return m.group(1)+html.escape(os.path.relpath(new,d),quote=True)+m.group(3)
    t2=re.sub(r'(<img[^>]*?\ssrc=")([^"]+)(")',sub,t)
    pagedist[p]=len(srcs)
    if t2!=t:
        b=os.path.join(BK,'pages',p);os.makedirs(os.path.dirname(b),exist_ok=True);shutil.copy2(p,b)
        open(p,'w',encoding='utf-8',newline='').write(t2);nchg+=1
print('pages rewritten',nchg)
# csvs
for c in glob.glob('*.csv'):
    raw=open(c,'rb').read();eol='\r\n' if b'\r\n' in raw else '\n'
    rows=list(csv.reader(open(c,encoding='utf-8-sig',newline='')));h=rows[0]
    if 'output' not in h: continue
    oi=h.index('output');ii=h.index('images_copied') if 'images_copied' in h else None;ch=0
    for r in rows[1:]:
        if len(r)<=oi: continue
        o=os.path.normpath(r[oi]) if r[oi] else ''
        if o in allmap: r[oi]=allmap[o];ch+=1
        if ii is not None and r[oi] in pagedist and str(pagedist[r[oi]])!=r[ii]: r[ii]=str(pagedist[r[oi]]);ch+=1
    if ch:
        shutil.copy2(c,os.path.join(BK,c))
        with open(c,'w',encoding='utf-8-sig',newline='') as f: csv.writer(f,lineterminator=eol).writerows(rows)
        print(c,ch)
# delete verified
n=0
for d,k in allmap.items():
    assert filecmp.cmp(d,k,shallow=False),(d,k)
    os.unlink(d);n+=1
for dp,dn,fn in os.walk('.',topdown=False):
    if dp!='.' and not os.listdir(dp): os.rmdir(dp)
print('deleted',n)
