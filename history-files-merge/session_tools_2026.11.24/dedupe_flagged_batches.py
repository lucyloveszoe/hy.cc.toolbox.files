"""Batches 1+2 of the flagged near duplicates (63.6), re-verified from the files:
 batch 1: image-hash SET identical -> delete the page with the shorter text;
 batch 2: one page's image-hash set is a strict subset of the other's -> delete the subset page (the one with fewer images),
          only if every extra image of the keeper is >= 5 KB (not an icon/error stub).
Usage: dedupe_flagged_batches.py <reports_merged> <set> <removed.tsv> [--go]"""
import os,sys,re,csv,html,hashlib,collections
RM=os.path.abspath(sys.argv[1]);SET=sys.argv[2];TSV=sys.argv[3];GO='--go' in sys.argv;D=os.path.join(RM,SET)
rows=list(csv.DictReader(open(os.path.join(RM,f'{SET}_flagged_duplicates.csv'),encoding='utf-8-sig')))
g=collections.OrderedDict()
for r in rows:
    if r['kind'].startswith('near'): g.setdefault(r['group'],[]).append(r['page'])
cache={}
def sha(p):
    if p not in cache:
        h=hashlib.sha256()
        with open(p,'rb') as f:
            for b in iter(lambda:f.read(1<<20),b''): h.update(b)
        cache[p]=h.hexdigest()
    return cache[p]
def info(f):
    t=open(os.path.join(D,f),encoding='utf-8').read().split('<body>',1)[1]
    t=re.sub(r'<h1>.*?</h1>','',t,flags=re.S)
    ims=[os.path.join(D,html.unescape(i)) for i in re.findall(r'<img[^>]*?\ssrc="([^"]+)"',t)]
    tx=re.sub(r'\s+','',html.unescape(re.sub(r'<[^>]+>',' ',re.sub(r'<h3>.*?</h3>','',t,flags=re.S)).replace('[image missing]',''))).lower()
    return {sha(p):os.path.getsize(p) for p in ims},len(tx)
plan=[];gone=set();skip=collections.Counter()
for gid,(a,b) in g.items():
    if a in gone or b in gone: skip['partner already removed']+=1;continue
    (ia,ta),(ib,tb)=info(a),info(b);sa,sb=set(ia),set(ib)
    if sa==sb: kind=1;keep,rm=(a,b) if (ta,-a.count('__'))>=(tb,-b.count('__')) else (b,a)
    elif sa<sb or sb<sa:
        kind=2;small,big=(a,b) if sa<sb else (b,a);ibig=ia if big==a else ib;ismall=ia if small==a else ib
        if any(ibig[h]<5000 for h in set(ibig)-set(ismall)): skip['extra picture <5KB']+=1;continue
        keep,rm=big,small
    else: continue
    plan.append((kind,rm,keep));gone.add(rm)
print('batch1',sum(1 for k,_,_ in plan if k==1),'batch2',sum(1 for k,_,_ in plan if k==2),'skipped',dict(skip))
if not GO: sys.exit()
rel=lambda f:f'{SET}/{f}';m={rel(d):rel(k) for _,d,k in plan}
for c in os.listdir(RM):
    if not c.endswith('_summary.csv'): continue
    p=os.path.join(RM,c);raw=open(p,'rb').read();eol='\r\n' if b'\r\n' in raw else '\n'
    rs=list(csv.reader(open(p,encoding='utf-8-sig',newline='')));oi=rs[0].index('output');n=0
    for r in rs[1:]:
        if r[oi] in m: r[oi]=m[r[oi]];n+=1
    with open(p,'w',encoding='utf-8-sig',newline='') as f: csv.writer(f,lineterminator=eol).writerows(rs)
    print(c,'rows repointed',n)
with open(TSV,'a',encoding='utf-8') as f:
    for _,d,k in plan: f.write(f'{d}\t{k}\n')
for _,d,k in plan: os.unlink(os.path.join(D,d))
print('deleted',len(plan))
