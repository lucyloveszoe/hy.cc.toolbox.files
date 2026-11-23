#!/usr/bin/env python3 -I
"""Reads route_plan.tsv; writes route_tiers.tsv. Tier A = region word of the target region in the title;
tier B = best score >= 10 and >= 3x the second; tier C = the rest (not moved)."""
import csv,re
src=open('/Users/hany/Documents/cc.self/hy.cc.toolbox.files/history-files-merge/session_tools_2026.11.19/route_topics.py',encoding='utf-8').read().split('\n')
ns={'re':re};exec('\n'.join(src[25:60]),ns);REG=ns['REG']
rows=list(csv.DictReader(open('route_plan.tsv',encoding='utf-8'),delimiter='\t'))
A=[];B=[];C=[]
for r in rows:
    if r['basis'] not in('learned','keyword'): continue
    sc=[tuple(x.split(':')) for x in r['scores'].split(';') if x]
    best=int(sc[0][1]); sec=int(sc[1][1]) if len(sc)>1 else 0
    if any(w in r['title'] for w in REG.get(r['region'],[])): A.append(r)
    elif best>=10 and best>=3*sec: B.append(r)
    else: C.append(r)
print('A',len(A),'B',len(B),'C',len(C))
open('route_tiers.tsv','w',encoding='utf-8').write('tier\troot\tfile\tregion\n'+''.join(f"{t}\t{r['root']}\t{r['file']}\t{r['region']}\n" for t,L in(('A',A),('B',B),('C',C)) for r in L))
