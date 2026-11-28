"""READ-ONLY: merged txt stories vs every html page under given dirs (8-gram share of the story found in the page)."""
import os,sys,csv,re,html
txt,man=sys.argv[1:3]; dirs=sys.argv[3:]
norm=lambda s: re.sub(r'\s+','',s).lower()
g8=lambda s:{s[i:i+8] for i in range(len(s)-7)}
L=open(txt,encoding='utf-8').read().split('\n')
new=[]
for r in csv.DictReader(open(man,encoding='utf-8-sig')):
    s='\n'.join(L[int(r['start_line'])-1:int(r['end_line'])]).split('\n')
    body=norm('\n'.join(x for x in s[1:] if not x.startswith('作者')))   # body only
    new.append((r['title'],body,g8(body)))
idx={}
for i,(_,b,G) in enumerate(new):
    for g in G:
        if hash(g)%8==0: idx.setdefault(g,set()).add(i)
best={}
for D in dirs:
  for d,_,fs in os.walk(D):
    if '_files' in d: continue
    for f in fs:
        if not f.endswith(('.html','.htm')): continue
        p=os.path.join(d,f)
        try: t=open(p,encoding='utf-8',errors='replace').read()
        except Exception: continue
        t=re.sub(r'(?s)<head>.*?</head>|<script.*?</script>|<style.*?</style>','',t)
        v=norm(html.unescape(re.sub(r'<[^>]+>','',t)))
        cnt={}
        for i in range(len(v)-7):
            g=v[i:i+8]
            if hash(g)%8==0 and g in idx:
                for j in idx[g]: cnt[j]=cnt.get(j,0)+1
        if not cnt: continue
        V=None
        for j,c in cnt.items():
            if c<3: continue
            if V is None: V=g8(v)
            sh=len(new[j][2]&V)/max(1,len(new[j][2]))
            if sh>best.get(j,(0,''))[0]: best[j]=(sh,p)
for j,(sh,p) in sorted(best.items(),key=lambda x:-x[1][0]):
    if sh>=0.6: print('%.2f'%sh,len(new[j][1]),new[j][0][:45],'=>',p.split('data.done/')[-1][:110])
print('stories',len(new),'with share>=0.90:',sum(1 for s,_ in best.values() if s>=0.9),'>=0.60:',sum(1 for s,_ in best.values() if s>=0.6))
