"""Merge the per-page txt of a consolidated root into 141.txt + 141.manifest.csv + 141.removed.tsv (empty = <=2 non-blank lines, duplicates by normalised md5). Usage: merge_txt_pages.py <txt dir> (PROCESSING_RULES 61)"""
import os,re,csv,hashlib,sys
T=sys.argv[1]
norm=lambda s: re.sub(r'\s+','',s).lower()
files=sorted(os.path.join(dp,f) for dp,_,fn in os.walk(T) for f in fn if f.endswith('.txt') and not f.startswith('141.'))
seen={};kept=[];rem=[]
for p in files:
    t=open(p,encoding='utf-8-sig').read().replace('\r\n','\n').replace('\r','\n').replace('\xa0',' ')
    t='\n'.join(l.rstrip() for l in t.split('\n')); t=re.sub(r'\n{3,}','\n\n',t).strip('\n')
    rel=os.path.relpath(p,T)
    if sum(1 for l in t.split('\n') if l.strip())<=2: rem.append(('EMPTY',rel,'')); continue
    h=hashlib.md5(norm(t).encode()).hexdigest()
    if h in seen: rem.append(('DUP',rel,seen[h])); continue
    seen[h]=rel; kept.append((rel,t))
out=[];rows=[];ln=1
for i,(rel,t) in enumerate(kept,1):
    n=t.count('\n')+1
    rows.append((i,rel.replace('/','／'),ln,ln+n-1,len(t))); out.append(t); ln+=n+1
open(os.path.join(T,'141.txt'),'w',encoding='utf-8',newline='\n').write('\n\n'.join(out)+'\n')
with open(os.path.join(T,'141.manifest.csv'),'w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f,lineterminator='\n'); w.writerow(['no','file','start_line','end_line','chars']); w.writerows(rows)
with open(os.path.join(T,'141.removed.tsv'),'w',encoding='utf-8') as f:
    for r in rem: f.write('\t'.join(r)+'\n')
print(len(files),'files ->',len(kept),'stories;',len(rem),'removed',sum(1 for r in rem if r[0]=='EMPTY'),'empty;',ln-2,'lines')
# verify
L=open(os.path.join(T,'141.txt'),encoding='utf-8').read().split('\n')
bad=sum(1 for (_,_,s,e,c),(_,t) in zip(rows,kept) if '\n'.join(L[s-1:e])!=t or len(t)!=c)
print('manifest mismatches',bad,'| 作者 headers',sum(1 for l in L if l.startswith('作者')))
