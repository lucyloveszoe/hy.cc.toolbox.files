import os,hashlib,collections,unicodedata,sys
R=sys.argv[1]; g=collections.defaultdict(list); fake=[]
for dp,_,fn in os.walk(R):
    for f in sorted(fn):
        if f in('.DS_Store','Thumbs.db'): continue
        p=os.path.join(dp,f); b=open(p,'rb').read()
        if not(b[:3]==b'\xff\xd8\xff' or b[:8]==b'\x89PNG\r\n\x1a\n' or b[:3]==b'GIF' or b[:2]==b'BM'): fake.append((p,len(b)))
        g[hashlib.sha256(b).hexdigest()].append(p)
n=sum(len(v) for v in g.values())
print('files',n,'distinct',len(g),'extra',n-len(g),'fake',len(fake),fake[:5])
cross=sum(1 for v in g.values() if len({p.split('/')[len(R.rstrip('/').split('/'))] for p in v})>1)
print('groups across folders',cross)
names=collections.Counter(unicodedata.normalize('NFC',os.path.basename(v[0])).lower() for v in g.values()); print('basename clashes among kept',sum(1 for c in names.values() if c>1))
