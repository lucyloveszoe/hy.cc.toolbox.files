import os,re,csv,hashlib,sys,unicodedata
sys.path.insert(0,'/Users/hany/Documents/cc.self/hy.cc.toolbox.files/history-files-merge')
from doc_to_txt import strip_tail
SRC,OUT=sys.argv[1],sys.argv[2]
norm=lambda s: re.sub(r'\s+','',s).lower()
GAR=r'(?:[ \xa0　](?:&(?:amp|quot|lt|gt|#x27|#39);|[!-;=-~]){1,2})*(?=[ \xa0　]*(?:[\n]|$|[^\x00-\x7f]))'
STAMP=re.compile(r'\[?\s*本帖最[后後]由[^\n]{1,60}?[于於][^\n]{1,40}?[编編][辑輯]\s*\]?'+GAR)
REPLY=re.compile(r'本帖[隐隱]藏的[内內](?:容需要[回]?[复復]才可以[浏瀏][览覽])?')
def clean(t):
    t=unicodedata.normalize('NFC',t).replace('\r\n','\n').replace('\r','\n').replace('\xa0',' ').replace(' ','\n').replace(' ','\n')
    t=re.sub('[​-‏﻿�-\x00-\x08\x0b\x0c\x0e-\x1f]','',t)
    t=STAMP.sub('',t); t=REPLY.sub('',t)
    t=re.sub(r'\[/?(?:image missing|img)\]','',t,flags=re.I)
    t='\n'.join(strip_tail(l)[0].rstrip() for l in t.split('\n'))
    return re.sub(r'\n{3,}','\n\n',t).strip('\n')
files=sorted(os.path.join(dp,f) for dp,_,fn in os.walk(SRC) for f in fn if f.endswith('.txt') and f!='141.txt')
seen={};kept=[];rem=[];changed=0
for p in files:
    raw=open(p,encoding='utf-8-sig').read(); t=clean(raw); changed+=t!=raw.strip('\n')
    rel=os.path.relpath(p,SRC)
    body=[l for l in t.split('\n')[1:] if l.strip() and not l.startswith('作者')]
    if sum(len(l.strip()) for l in body)<5 or not body: rem.append(('EMPTY',rel,'')); continue
    h=hashlib.md5(norm(t).encode()).hexdigest()
    if h in seen: rem.append(('DUP',rel,seen[h])); continue
    seen[h]=rel; kept.append((rel,t))
import difflib
core=lambda s: re.sub(r'[^\w]|b$|新提醒|神州\w+|賽後報告|及賽後報','',s.lower())
drop=set()
for i in range(len(kept)):
    for j in range(i+1,len(kept)):
        if i in drop or j in drop: continue
        a,b=core(kept[i][1].split('\n')[0]),core(kept[j][1].split('\n')[0])
        if len(a)>=6 and (a==b or a in b or b in a):
            A,B=norm(kept[i][1]),norm(kept[j][1])
            if difflib.SequenceMatcher(None,A[:3000],B[:3000],autojunk=False).ratio()>=0.95:
                lo,hi=(i,j) if len(A)>len(B) else (j,i)   # drop shorter; tie -> later
                if len(A)==len(B): lo,hi=j,i
                drop.add(lo); rem.append(('NEARDUP',kept[lo][0],kept[hi][0]))
kept=[k for n,k in enumerate(kept) if n not in drop]
os.makedirs(OUT,exist_ok=False)
out=[];rows=[];ln=1
for i,(rel,t) in enumerate(kept,1):
    n=t.count('\n')+1
    rows.append((i,t.split('\n')[0].strip(),ln,ln+n-1,len(t))); out.append(t); ln+=n+1
open(OUT+'/txt_merged.txt','w',encoding='utf-8',newline='\n').write('\n\n'.join(out)+'\n')
with open(OUT+'/txt_merged.manifest.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f,lineterminator='\n'); w.writerow(['no','title','start_line','end_line','chars']); w.writerows(rows)
open(OUT+'/txt_merged.removed.tsv','w',encoding='utf-8').write(''.join('\t'.join(r)+'\n' for r in rem))
print(len(files),'files, changed by clean',changed,'->',len(kept),'stories;',len(rem),'removed:',sum(r[0]=='EMPTY' for r in rem),'empty',sum(r[0]=='DUP' for r in rem),'dup',sum(r[0]=='NEARDUP' for r in rem),'near-dup;',ln-2,'lines')
L=open(OUT+'/txt_merged.txt',encoding='utf-8').read().split('\n')
print('manifest mismatches',sum('\n'.join(L[s-1:e])!=t or len(t)!=c for (_,_,s,e,c),(_,t) in zip(rows,kept)))
