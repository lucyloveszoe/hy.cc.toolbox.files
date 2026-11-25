"""After dedupe_flagged_batches.py: (1) follow removed->kept chains for summary rows whose page is gone,
(2) set images_copied = distinct images of the page the row points at. Usage: fix_chains_and_counts.py <reports_merged> <set> <removed.tsv>"""
import os,sys,csv,re,html
RM,SET,TSV=os.path.abspath(sys.argv[1]),sys.argv[2],sys.argv[3];D=os.path.join(RM,SET)
nxt={f'{SET}/{a}':f'{SET}/{b}' for a,b in (l.rstrip('\n').split('\t') for l in open(TSV,encoding='utf-8'))}
cnt={}
def distinct(rel):
    if rel not in cnt:
        t=open(os.path.join(RM,rel),encoding='utf-8').read()
        cnt[rel]=len({html.unescape(i) for i in re.findall(r'<img[^>]*?\ssrc="([^"]+)"',t)})
    return cnt[rel]
for c in os.listdir(RM):
    if not c.endswith('_summary.csv'): continue
    p=os.path.join(RM,c);raw=open(p,'rb').read();eol='\r\n' if b'\r\n' in raw else '\n'
    rs=list(csv.reader(open(p,encoding='utf-8-sig',newline='')));h=rs[0];oi=h.index('output');ii=h.index('images_copied');a=b=0
    for r in rs[1:]:
        o=r[oi];seen=0
        while o and not os.path.exists(os.path.join(RM,o)) and o in nxt and seen<20: o=nxt[o];seen+=1
        if o!=r[oi]: r[oi]=o;a+=1
        if o and os.path.exists(os.path.join(RM,o)) and str(distinct(o))!=r[ii]: r[ii]=str(distinct(o));b+=1
    with open(p,'w',encoding='utf-8-sig',newline='') as f: csv.writer(f,lineterminator=eol).writerows(rs)
    print(c,'chains resolved',a,'images_copied set',b)
