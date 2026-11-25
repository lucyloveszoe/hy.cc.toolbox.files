"""Delete exact-duplicate pages (same normalised text + same image sequence by SHA-256) of reports_merged/<set>,
repoint summary rows to the kept page, delete nothing else. Usage: dedupe_pages.py <scan.json> <reports_merged> <set> <removed.tsv> [--go]"""
import json,sys,os,csv,collections,re,html
scan,RM,SET,TSV=sys.argv[1:5];GO='--go' in sys.argv;D=os.path.join(RM,SET)
r=json.load(open(scan));g=collections.defaultdict(list)
for f,v in r.items(): g[v['sig']].append(f)
plan=[]
for s,v in g.items():
    if len(v)<2: continue
    v=sorted(v,key=lambda f:(-r[f]['imgs'],f.count('__'),f))
    for d in v[1:]: plan.append((d,v[0]))
print('groups',sum(1 for v in g.values() if len(v)>1),'pages to remove',len(plan))
for d,k in plan: print(' remove',d[:70],'| keep',k[:70])
if not GO: sys.exit()
rel=lambda f:f'{SET}/{f}'
m={rel(d):rel(k) for d,k in plan}
# images used by the kept page must cover the removed page
src=lambda f:set(re.findall(r'<img[^>]*?\ssrc="([^"]+)"',open(os.path.join(D,f),encoding='utf-8').read()))
for d,k in plan: assert src(d)==src(k) or [x for x in re.findall(r'src="([^"]+)"',open(os.path.join(D,d),encoding='utf-8').read())]==[x for x in re.findall(r'src="([^"]+)"',open(os.path.join(D,k),encoding='utf-8').read())],(d,k)
for c in os.listdir(RM):
    if not c.endswith('_summary.csv'): continue
    p=os.path.join(RM,c);raw=open(p,'rb').read();eol='\r\n' if b'\r\n' in raw else '\n'
    rows=list(csv.reader(open(p,encoding='utf-8-sig',newline='')));oi=rows[0].index('output');n=0
    for row in rows[1:]:
        if row[oi] in m: row[oi]=m[row[oi]];n+=1
    with open(p,'w',encoding='utf-8-sig',newline='') as f: csv.writer(f,lineterminator=eol).writerows(rows)
    print(c,'rows repointed',n)
with open(TSV,'w',encoding='utf-8') as f:
    for d,k in plan: f.write(f'{d}\t{k}\n')
for d,k in plan: os.unlink(os.path.join(D,d))
print('deleted',len(plan))
