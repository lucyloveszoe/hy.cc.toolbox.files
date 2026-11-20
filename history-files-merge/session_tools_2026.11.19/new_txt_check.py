import os,re,sys,csv,glob,hashlib,collections
sys.argv=['x','/dev/null']
src=open('/private/tmp/claude-502/-Users-hany-Documents-cc-self-hy-cc-toolbox-files-history-files-merge/27c525a3-50a2-42f8-9d1b-8af4703d9010/scratchpad/tools/txt_build.py',encoding='utf-8').read()
exec(src.split("tot=collections.Counter(); items=[]")[0])
SP='/private/tmp/claude-502/-Users-hany-Documents-cc-self-hy-cc-toolbox-files-history-files-merge/27c525a3-50a2-42f8-9d1b-8af4703d9010/scratchpad'
# existing library
lib={}
for tp in glob.glob(T+'/topics/mc_*.txt'):
    L=open(tp,encoding='utf-8').read().split('\n')
    for r in csv.DictReader(open(tp[:-4]+'.manifest.csv',encoding='utf-8-sig')):
        lib[r['file']]='\n'.join(L[int(r['start_line'])-1:int(r['end_line'])])
libh={hashlib.md5(norm(v).lower().encode()).hexdigest():k for k,v in lib.items()}
def grams(s,n=8): s=norm(s); return {s[i:i+n] for i in range(0,max(1,len(s)-n+1))}
news=[]
for tp in sorted(glob.glob(SP+'/missing_out/*/txt/**/*.txt',recursive=True)):
    root=tp.split('/missing_out/')[1].split('/')[0]
    t,_=tidy(open(tp,encoding='utf-8').read()); lines=t.split('\n')
    body=norm(''.join(l for l in lines[1:] if not l.startswith('作者')))
    news.append(dict(file=f"{root}／{os.path.basename(tp)}",text=t,body=body,h=hashlib.md5(norm(t).lower().encode()).hexdigest()))
c=collections.Counter(); keep=[]; seen={}
for n in news:
    if not n['body']: c['empty']+=1; continue
    if n['h'] in libh: c['exact dup of library']+=1; continue
    if n['h'] in seen: c['dup within new']+=1; continue
    seen[n['h']]=1
    g=grams(n['text']); best=0
    # near-duplicate vs library: containment of new text 8-grams in a library story (same first 12 chars only, cheap)
    title=norm(n['text'].split('\n')[0])[:12]
    for k,v in lib.items():
        if norm(v.split('\n')[0])[:12]==title:
            best=max(best,len(g&grams(v))/max(1,len(g)))
    n['near']=round(best,2); keep.append(n)
    c['new (near>0.9 vs same-title)' if best>0.9 else 'new']+=1
print(dict(c),'of',len(news))
import json; json.dump([{k:n[k] for k in ('file','text','near')} for n in keep],open(SP+'/new_stories.json','w',encoding='utf-8'),ensure_ascii=False)
