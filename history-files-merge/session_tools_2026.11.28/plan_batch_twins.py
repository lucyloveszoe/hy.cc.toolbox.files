"""READ-ONLY planner: group in-batch exact/subset twins from a new_vs_library.py TSV (<base>/nvl.tsv, new roots under <base>/out/) into remove->keep pairs for dedupe_page_pairs.py; keeper = most images, longest text, then root priority PRI (edit per batch). Usage: plan_batch_twins.py <base>"""
import csv,sys,collections
SP=sys.argv[1]
rows=list(csv.DictReader(open(SP+'/nvl.tsv',encoding='utf-8'),delimiter='\t'))
info={r['page']:(int(r['imgs'] or 0),int(r['chars'] or 0)) for r in rows}
PRI=['春风楼','寻凤阁','金屋藏娇','shlf','aishanghai','爱上海同城对对碰交友网']
root=lambda p: p.split('/out/')[1].split('/')[0]
par={}
def f(x):
    par.setdefault(x,x)
    while par[x]!=x: x=par[x]
    return x
for r in rows:
    if r['class'] in('exact','same-images-tiny-diff','subset','superset') and '/out/' in r['match']:
        a,b=f(r['page']),f(r['match'])
        if a!=b: par[a]=b
groups=collections.defaultdict(list)
for x in list(par): groups[f(x)].append(x)
keyf=lambda p:(-info[p][0],-info[p][1],PRI.index(root(p)),p)
plan=[]
for g in groups.values():
    g=sorted(set(g),key=keyf); plan+=[(x,g[0]) for x in g[1:]]
    if len(g)>2: print('group',len(g),[ (root(x),info[x]) for x in g])
print('groups',len(groups),'removals',len(plan)); print(collections.Counter((root(a),root(b)) for a,b in plan))
with open(SP+'/plan_batch.tsv','w',encoding='utf-8') as o:
    o.write('remove\tkeep\n'); [o.write(f'{a}\t{b}\n') for a,b in plan]
