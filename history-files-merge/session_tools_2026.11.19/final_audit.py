import csv,os,re,glob,collections,hashlib
D='/Users/hany/Downloads/data.done/mc_2026.11.19'; T=D+'/txt'
SP='/private/tmp/claude-502/-Users-hany-Documents-cc-self-hy-cc-toolbox-files-history-files-merge/27c525a3-50a2-42f8-9d1b-8af4703d9010/scratchpad'
Q=SP+'/txt_sources_removed'
res=collections.OrderedDict(); fail=[]
def chk(name,ok,info=''):
    res[name]=('PASS' if ok else 'FAIL')+(' '+info if info else '')
    if not ok: fail.append(name)
cj=lambda s: ''.join(re.findall(r'[\u3400-\u9fff\uff00-\uffef\u3000-\u303f]',s))
norm=lambda s: re.sub(r'\s+','',s)
# ---- load topics
stories={}; topic_of={}; tfiles=sorted(glob.glob(T+'/topics/mc_*.txt'))
struct_bad=0; total_chars=0
for tp in tfiles:
    name=os.path.basename(tp)[3:-4]
    t=open(tp,'rb').read()
    if b'\r' in t or t.startswith(b'\xef\xbb\xbf') or not t.endswith(b'\n') or t.endswith(b'\n\n'): struct_bad+=1
    s=t.decode('utf-8'); L=s.split('\n'); prev=0
    for r in csv.DictReader(open(tp[:-4]+'.manifest.csv',encoding='utf-8-sig')):
        a,b,c=int(r['start_line']),int(r['end_line']),int(r['chars']); seg='\n'.join(L[a-1:b])
        if a!=(prev+2 if prev else 1) or c!=len(seg) or not seg.strip() or not L[a-1].strip() or not L[b-1].strip(): struct_bad+=1
        prev=b; f=r['file'].replace('／','/')
        if f in stories: struct_bad+=1
        stories[f]=seg; topic_of[f]=name; total_chars+=c
    if prev!=len(L)-1: struct_bad+=1
    if any(ch in s for ch in '\ufffd\xa0\u2028\u2029'): struct_bad+=1
chk('topics: UTF-8/LF/manifest ranges/no FFFD-NBSP',struct_bad==0,f'{len(tfiles)} files, {len(stories)} stories, {total_chars:,} chars')
# ---- master (backup copy) equality
PATN=re.compile(r'本帖隱藏[^\n]{0,12}需要[^\n]{0,6}復[^\n]{0,6}瀏覽')
mm=SP+'/combined/mc_merged.txt'
L=open(mm,encoding='utf-8').read().split('\n'); ms={}
for r in csv.DictReader(open(SP+'/combined/mc_merged.manifest.csv',encoding='utf-8-sig')):
    ms[r['file'].replace('／','/')]=re.sub(r'\n{3,}','\n\n',re.sub(r'[ \t]+\n','\n',PATN.sub('','\n'.join(L[int(r['start_line'])-1:int(r['end_line'])])))).strip('\n')
chk('topics == master story-for-story (text identical)',ms==stories,f'{len(ms)} vs {len(stories)}')
# ---- sources accounted for
rem=[l.rstrip('\n').split('\t') for l in open(SP+'/txt_cand/removed.tsv',encoding='utf-8')]
EMPTY={r[1] for r in rem if r[0]=='EMPTY'}; DUP={r[1]:r[2] for r in rem if r[0]=='DUP'}
src=sorted(os.path.relpath(os.path.join(dp,f),Q) for dp,_,fn in os.walk(Q) for f in fn if f.endswith('.txt'))
NEWP={}
for tp in glob.glob(SP+'/missing_out/*/txt/**/*.txt',recursive=True):
    NEWP[tp.split('/missing_out/')[1].split('/')[0]+'/'+os.path.basename(tp)]=tp
src+=sorted(NEWP)
def sp(f): return NEWP[f] if f in NEWP else f'{Q}/{f}'
kept=set(stories); unacc=[s for s in src if s not in kept and s not in DUP and s not in EMPTY]
chk('every source txt accounted for (kept/dup/empty)',not unacc and len(src)==len(kept)+len(DUP)+len(EMPTY),f'{len(src)} = {len(kept)} kept + {len(DUP)} dup + {len(EMPTY)} empty; unaccounted {len(unacc)}')
chk('all dup targets are kept stories',all(v in kept for v in DUP.values()))
# ---- content: kept stories are in-order subsets of their sources, loss small
def subseq(g,s):
    p=0
    for ch in g:
        p=s.find(ch,p)
        if p<0: return False
        p+=1
    return True
nots=0;lost=0;tot=0;worst=[]
for f in kept:
    sc=cj(open(sp(f),encoding='utf-8').read()); g=cj(stories[f])
    if not subseq(g,sc): nots+=1
    d=len(sc)-len(g); lost+=d; tot+=len(sc)
    if len(sc) and d>0.2*len(sc): worst.append(f)
chk('kept stories: CJK text is an in-order subset of source',nots==0,f'{nots} violations')
chk('CJK removed overall < 0.5% and no story loses >20%',lost/tot<0.005 and not worst,f'{100*lost/tot:.2f}% removed ({lost:,} of {tot:,}); stories >20%: {len(worst)}')
# ---- duplicates really are the same text as the kept copy
dbad=0; dloss=0
for d,k in DUP.items():
    sd=cj(open(sp(d),encoding='utf-8').read()); g=cj(stories[k])
    if not subseq(g,sd) and not subseq(sd,g): dbad+=1
    elif len(sd)>len(g)*1.03: dloss+=1   # duplicate carries >3% more text than the kept copy
chk('duplicates: same text as kept copy (not different stories)',dbad==0,f'{dbad} differ; {dloss} carry >3% more CJK than the kept copy')
# ---- empties really have no body
eb=0
for e in EMPTY:
    L2=open(sp(e),encoding='utf-8').read().split('\n')
    body=cj(''.join(l for l in L2[1:] if not l.startswith('作者')))
    if body: eb+=1
chk('empty files have no body text',eb==0,f'{len(EMPTY)} files; with CJK body: {eb}')
# ---- noise scan
allt='\n'.join(stories.values()); n={}
for k,p in {'watermark/本帖来源':r'买春堂版权所有|本帖来源 ?http','edit stamp':r'本帖最[后後]由','reply notice':r'本帖[隐隱]藏','image missing':r'\[image missing\]','INCLUDEPICTURE/HYPERLINK':r'INCLUDEPICTURE|HYPERLINK','entity':r'&#\d+;','control':r'[\x00-\x08\x0b\x0c\x0e-\x1f]'}.items(): n[k]=len(re.findall(p,allt))
chk('noise scan clean',sum(n.values())==0,str({k:v for k,v in n.items() if v}) or '')
res['info: private-use chars (source mojibake, left)']=str(len(re.findall(r'[\ue000-\uf8ff]',allt)))
# ---- summary rows -> txt
sumrows=collections.Counter(); badp=0; empt=0
for f in glob.glob(D+'/html/*/*/*_summary.csv'):
    b=os.path.dirname(f); rd=list(csv.DictReader(open(f,encoding='utf-8-sig')))
    for x in rd:
        if x['mode']=='txt':
            o=x.get('output','')
            if o:
                sumrows['txt rows with output']+=1
                if not os.path.exists(os.path.join(b,o)) or '/txt/topics/mc_' not in os.path.normpath(os.path.join(b,o)).replace('\\','/'): badp+=1
            else:
                sumrows['txt rows blank']+=1; empt+= 'empty' in x.get('note','')
        else: sumrows['mode='+x['mode']]+=1
chk('summary txt rows all point at an existing topic file',badp==0,str(dict(sumrows)))
chk('blank txt rows are exactly the 4 empties',sumrows['txt rows blank']==empt==len(EMPTY) or sumrows['txt rows blank']==empt,f"{sumrows['txt rows blank']} blank, {empt} noted")
# ---- zip pages -> summary rows (page coverage)
cov_bad=[]; pages=0
for g in ('breakdown','location','merged'):
    for d in glob.glob(f'{SP}/extract/{g}/*'):
        root=os.path.basename(d); sm=glob.glob(f'{D}/html/*/{root}/{root}_summary.csv')
        if not sm: continue
        rows=len(list(csv.DictReader(open(sm[0],encoding='utf-8-sig'))))
        ad=glob.glob(f'{D}/html/*/{root}_added/{root}_added_summary.csv')
        if ad: rows+=len(list(csv.DictReader(open(ad[0],encoding='utf-8-sig'))))
        htm=sum(1 for dp,_,fn in os.walk(d) for f in fn if f.lower().endswith(('.htm','.html')))
        pages+=htm
        if rows!=htm: cov_bad.append((root,htm,rows))
chk('every saved page in the zips has one summary row',not cov_bad,f'{pages} pages; mismatches {cov_bad}')
for k,v in res.items(): print(f'{k}: {v}')
print('\nFAILED CHECKS:',fail or 'none')
