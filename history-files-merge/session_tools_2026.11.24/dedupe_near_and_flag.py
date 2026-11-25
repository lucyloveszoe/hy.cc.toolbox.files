"""(1) Pages with the same image sequence (SHA-256, in order) whose text differs by <=20 chars on each side and is >=95%
similar are duplicates (PROCESSING_RULES 40.4): keep the longest text, delete the rest, repoint summary rows.
(2) Flag everything else: same-text groups and near pairs (merge_report_folders.near_pairs) -> <set>_flagged_duplicates.csv.
Usage: dedupe_near_and_flag.py <reports_merged> <set> <removed.tsv> [--go]"""
import os,sys,re,html,csv,hashlib,difflib,collections
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import merge_report_folders as M
RM=os.path.abspath(sys.argv[1]);SET=sys.argv[2];TSV=sys.argv[3];GO='--go' in sys.argv;D=os.path.join(RM,SET)
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
cache={}
def info(f):
    t=open(os.path.join(D,f),encoding='utf-8').read().split('<body>',1)[1]
    t=re.sub(r'<h1>.*?</h1>','',t,flags=re.S)
    imgs=[html.unescape(i) for i in re.findall(r'<img[^>]*?\ssrc="([^"]+)"',t)]
    seq=tuple(cache.setdefault(i,sha(os.path.join(D,i))) for i in imgs)
    tx=re.sub(r'\s+','',html.unescape(re.sub(r'<[^>]+>',' ',re.sub(r'<h3>.*?</h3>','',t,flags=re.S)).replace('[image missing]',''))).lower()
    return seq,tx
pages=sorted(f for f in os.listdir(D) if f.endswith('.html'))
I={f:info(f) for f in pages}
byseq=collections.defaultdict(list)
for f,(s,t) in I.items(): byseq[s].append(f)
plan=[];stats=[]
for s,v in byseq.items():
    if len(v)<2: continue
    v=sorted(v,key=lambda f:(-len(I[f][1]),f.count('__'),f));gone=set()
    for i,k in enumerate(v):
        if k in gone: continue
        for d in v[i+1:]:
            if d in gone: continue
            a,b=I[k][1],I[d][1]
            sm=difflib.SequenceMatcher(None,a,b,autojunk=False)
            ops=[o for o in sm.get_opcodes() if o[0]!='equal']
            da=sum(i2-i1 for _,i1,i2,_,_ in ops);db=sum(j2-j1 for _,_,_,j1,j2 in ops)
            if da<=20 and db<=20 and sm.ratio()>=0.95: plan.append((d,k));gone.add(d);stats.append((da,db))
print('same-image-sequence groups',sum(1 for v in byseq.values() if len(v)>1),'| duplicates to remove',len(plan),'| max diff chars',max(max(s) for s in stats) if stats else 0)
if GO:
    rel=lambda f:f'{SET}/{f}';m={rel(d):rel(k) for d,k in plan}
    for c in os.listdir(RM):
        if not c.endswith('_summary.csv'): continue
        p=os.path.join(RM,c);raw=open(p,'rb').read();eol='\r\n' if b'\r\n' in raw else '\n'
        rows=list(csv.reader(open(p,encoding='utf-8-sig',newline='')));oi=rows[0].index('output');n=0
        for r in rows[1:]:
            if r[oi] in m: r[oi]=m[r[oi]];n+=1
        with open(p,'w',encoding='utf-8-sig',newline='') as f: csv.writer(f,lineterminator=eol).writerows(rows)
        print(c,'rows repointed',n)
    with open(TSV,'a',encoding='utf-8') as f:
        for d,k in plan: f.write(f'{d}\t{k}\n')
    for d,k in plan: os.unlink(os.path.join(D,d))
    print('deleted',len(plan))
    gone={d for d,_ in plan}
else: gone={d for d,_ in plan}
left=[f for f in pages if f not in gone]
# flags
rows=[];gid=0
g=collections.defaultdict(list)
for f in left: g[I[f][1]].append(f)
for t,v in g.items():
    if len(v)>1 and t:
        gid+=1
        for f in v: rows.append((gid,'same text, different images',f,len(set(I[f][0])),len(I[f][1])))
nsame=gid
pairs=M.near_pairs([os.path.join(D,f) for f in left])
done={frozenset(x) for x in ()}
for j,a,c in pairs:
    gid+=1;ha,hc=set(I[os.path.basename(a)][0]),set(I[os.path.basename(c)][0])
    for f,h in((a,ha),(c,hc)):
        b=os.path.basename(f);rows.append((gid,f'near duplicate J={j:.2f}; common images {len(ha&hc)}, only-a {len(ha-hc)}, only-b {len(hc-ha)}',b,len(h),len(I[b][1])))
print('flag groups: same-text',nsame,'near pairs',len(pairs),'rows',len(rows))
if GO:
    with open(os.path.join(RM,f'{SET}_flagged_duplicates.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['group','kind','page','distinct_images','text_chars']);w.writerows(rows)
