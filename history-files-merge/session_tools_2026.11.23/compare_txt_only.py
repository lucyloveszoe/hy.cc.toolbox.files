"""Compare ~/Downloads/txt-only with the stories of gochina_2026.11.19/txt_merged.txt and mc_2026.11.19/txt (exact, lower-case, no whitespace). Read-only. Usage: compare_txt_only.py <out.tsv> (PROCESSING_RULES 62.8)"""
import csv,re,sys,hashlib
from pathlib import Path
D=Path.home()/'Downloads'
norm=lambda s: re.sub(r'\s+','',s).lower()
def stories(txt,man):
    L=txt.read_text(encoding='utf-8-sig').split('\n')
    out=[]
    with open(man,encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        for row in r:
            s=int(row.get('start_line') or row.get('start')); e=int(row.get('end_line') or row.get('end'))
            out.append(norm('\n'.join(L[s-1:e])))
    return out
T=[]  # (label, normalized story)
g=D/'data.done/gochina_2026.11.19'
for t in stories(g/'txt_merged.txt',g/'txt_merged.manifest.csv'): T.append(('gochina',t))
miss=[]
for p in sorted((D/'data.done/mc_2026.11.19/txt').rglob('*.txt')):
    m=p.with_suffix('').with_suffix('.manifest.csv') if False else p.parent/(p.stem+'.manifest.csv')
    if m.exists(): [T.append((p.name,t)) for t in stories(p,m)]
    else: miss.append(p.name); T.append((p.name,norm(p.read_text(encoding='utf-8-sig'))))
print('target stories',len(T),'files without manifest',miss)
exact={}; 
for lab,t in T: exact.setdefault(hashlib.md5(t.encode()).hexdigest(),lab)
corpus=[(lab,t) for lab,t in T]
big='\x00'.join(t for _,t in T)
res={}
def classify(n):
    h=hashlib.md5(n.encode()).hexdigest()
    if h in exact: return 'exact',exact[h]
    if len(n)>=200 and n in big: return 'contained',''
    return 'none',''
import collections
C=collections.Counter(); rows=[]
for p in sorted((D/'txt-only').rglob('*.txt')):
    if p.name=='GoChina.txt' and p.parent==D/'txt-only': continue
    n=norm(p.read_text(encoding='utf-8-sig')); k,l=classify(n); C[k]+=1; rows.append((str(p),k,l))
print('per-page files',dict(C))
# merged GoChina.txt stories
M=stories(D/'txt-only/GoChina.txt',D/'txt-only/GoChina.manifest.csv'); C2=collections.Counter(classify(n)[0] for n in M)
print('GoChina.txt stories',len(M),dict(C2))
print(collections.Counter(l for _,k,l in rows if k=='exact').most_common(5))
open(sys.argv[1],'w').write('\n'.join('\t'.join(r) for r in rows))
