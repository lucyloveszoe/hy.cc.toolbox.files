import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import PROJ, DD
import os,re,sys,csv,hashlib,collections
sys.path.insert(0,PROJ)
from clean_doc_noise import clean as wm_clean
from clean_loose_txt import SPAM,SPAM2,strip_edges
from doc_to_txt import strip_tail
FOOT=re.compile(r'\s+-\s+[^\s-]*春色.*关闭注册[】\]]?\s*$')
T=(DD+'/mc_2026.11.19/txt')
OUT=sys.argv[1]
STAMP=re.compile(r'\[?[ \t]*本帖最[后後]由[^\n\]]*?[于於][^\n\]]*?[编編][辑輯][ \t]*\]?')
NOTICE=re.compile(r'(?:[^\s，,。]{1,20}[，,][ \t]*)?(?:如果您要查看本帖[隐隱]藏[内內]容请[回]?[复復]|本帖[隐隱]藏的[内內]容需要积分高于[ \t]*\d+[ \t]*才可[浏瀏][览覽](?:[，,][ \t]*您当前积分为[ \t]*\d+)?|本帖[隐隱]藏的[内內]容需要[回]?[复復]才可以[浏瀏][览覽])')
MISSING=re.compile(r'^[ \t]*\[image missing\][ \t]*\n?',re.M)
norm=lambda s: re.sub(r'\s+','',s).lower()
files=sorted(os.path.join(dp,f) for dp,_,fn in os.walk(T) for f in fn if f.endswith('.txt') and not f.startswith('mc_merged'))
RUN=re.compile(r'(?:(?<=\s)|^)(?:[!-~]{1,2} ){3,}[!-~]{1,2}(?=\s|$)',re.M)
LD=re.compile(r'[A-Za-z][0-9]|[0-9][A-Za-z]'); SYM=re.compile(r'[&%$*@^|~;`"\\]')
def _run(m):
    toks=m.group(0).split(' ')
    ld=sum(bool(LD.search(x)) for x in toks); sy=sum(bool(SYM.search(x)) for x in toks)
    return '' if (ld>=3 or (ld>=1 and sy>=2)) else m.group(0)
def tidy(t):
    t=t.lstrip('﻿').replace(' ','\n').replace(' ','\n').replace('\r\n','\n').replace('\r','\n')
    t=t.replace('\xa0',' ')
    st={}
    t,st['watermark']=wm_clean(t)
    t,a=SPAM2.subn('',t); t,b=SPAM.subn('',t); st['spam']=a+b
    out=[];tl=ed=0
    for ln in t.split('\n'):
        new,h=strip_tail(ln); tl+=h
        new,h=strip_edges(new); ed+=h
        out.append(new)
    t='\n'.join(out); st['tail']=tl; st['edges']=ed
    n0=len(t); t=RUN.sub(_run,t); st['runs']=int(len(t)!=n0)
    t,st['stamp']=STAMP.subn('',t); t,st['notice']=NOTICE.subn('',t); t,st['img_missing']=MISSING.subn('',t); t,k=re.subn(r'^[ \t]*本帖[隐隱]藏的[内內]容[ \t]*\n?','',t,flags=re.M); st['notice']+=k
    t=t.replace('[image missing]','')
    t=re.sub(r'&#(\d+);',lambda m:chr(int(m.group(1))),t)
    t=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f�]','',t)
    t=re.sub(r'[ \t　]+$','',t,flags=re.M)
    t=re.sub(r'[ \t]{2,}',' ',t)
    t=re.sub(r'\n{3,}','\n\n',t).strip('\n')
    first,_,rest=t.partition('\n'); first,k=FOOT.subn('',first); st['footer']=k; t=first+('\n'+rest if rest else '')
    return t,st
tot=collections.Counter(); items=[]
for p in files:
    raw=open(p,encoding='utf-8').read()
    t,st=tidy(raw); tot.update(st)
    lines=t.split('\n'); title=norm(lines[0])
    body=norm(''.join(l for l in lines[1:] if not l.startswith('作者')))
    items.append(dict(rel=os.path.relpath(p,T),text=t,body=body,n=norm(t)))
empty=[i for i in items if not i['body']]
keep=[i for i in items if i['body']]
groups=collections.defaultdict(list)
for i in keep: groups[hashlib.md5(i['n'].encode()).hexdigest()].append(i)
final=[];dups=[]
for g in groups.values():
    best=max(g,key=lambda i:(len(i['rel'].rsplit('/',1)[-1]),-len(i['rel'])))  # longest file name = most complete title
    final.append(best)
    dups+=[(x['rel'],best['rel']) for x in g if x is not best]
final.sort(key=lambda i:i['rel'])
os.makedirs(OUT,exist_ok=True)
lines=[];man=[];ln=1
for k,i in enumerate(final,1):
    seg=i['text'].split('\n')
    man.append((k,i['rel'].replace('/','／'),ln,ln+len(seg)-1,len('\n'.join(seg))))
    lines+=seg+['']; ln+=len(seg)+1
open(f'{OUT}/mc_merged.txt','w',encoding='utf-8',newline='\n').write('\n'.join(lines[:-1])+'\n')
with open(f'{OUT}/mc_merged.manifest.csv','w',encoding='utf-8-sig',newline='') as fh:
    w=csv.writer(fh,lineterminator='\n'); w.writerow(['no','file','start_line','end_line','chars']); w.writerows(man)
with open(f'{OUT}/removed.tsv','w',encoding='utf-8') as fh:
    for r in empty: fh.write(f"EMPTY\t{r['rel']}\t\n")
    for a,b in dups: fh.write(f"DUP\t{a}\t{b}\n")
print('sources',len(files),'empty',len(empty),'duplicates',len(dups),'stories',len(final)); print(dict(tot))
print('lines',ln-1)
