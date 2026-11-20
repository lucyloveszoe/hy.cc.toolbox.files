import csv,os,sys,glob,collections,shutil
GO='--go' in sys.argv
P='/Users/hany/Documents/cc.self/hy.cc.toolbox.files/history-files-merge'
D='/Users/hany/Downloads/data.done/mc_2026.11.19'
T=D+'/txt'; MERGED=T+'/mc_merged.txt'
SP=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rem=[l.rstrip('\n').split('\t') for l in open(SP+'/txt_cand/removed.tsv',encoding='utf-8')]
EMPTY={r[1] for r in rem if r[0]=='EMPTY'}
man=[r['file'].replace('／','/') for r in csv.DictReader(open(SP+'/txt_cand/mc_merged.manifest.csv',encoding='utf-8-sig'))]
INMERGED=set(man)|{r[1] for r in rem if r[0]=='DUP'}
TAG='[txt file was empty; removed]'
cnt=collections.Counter(); unresolved=[]
bak=SP+'/bak_csv_move'
for csvp in sorted(glob.glob(D+'/html/*/*/*.csv')):
    newdir=os.path.dirname(csvp); root=os.path.basename(newdir)
    olddir=f'{P}/outputs/{root}'
    raw=open(csvp,'rb').read(); eol='\r\n' if b'\r\n' in raw else '\n'
    rows=list(csv.reader(open(csvp,encoding='utf-8-sig',newline='')))
    head=rows[0]
    if 'output' not in head: continue
    oi=head.index('output'); changed=False; need_note=False
    for r in rows[1:]:
        o=r[oi]
        if not o: continue
        a=os.path.normpath(os.path.join(olddir,o))
        if a.startswith(olddir+os.sep):
            new=newdir+a[len(olddir):]; kind='root'
        elif a.startswith(T+os.sep+root+os.sep) or a.startswith(T+os.sep):
            rel=os.path.relpath(a,T)
            # source txt rel is <root>/<file...>
            if rel in EMPTY: new=None; kind='empty'
            elif rel in INMERGED: new=MERGED; kind='merged'
            else: new=a; kind='txt-other'
        else:
            new=a; kind='other'
        if new is None:
            r[oi]=''; need_note=True; cnt[kind]+=1; r.append(TAG) if len(r)==len(head) else None; changed=True; continue
        if not os.path.exists(new): unresolved.append((root,o[:60],kind)); cnt['UNRESOLVED']+=1; continue
        rel=os.path.relpath(new,newdir)
        cnt[kind]+=1
        if rel!=o: r[oi]=rel; changed=True
    if changed:
        cnt['csv changed']+=1
        if GO:
            os.makedirs(bak,exist_ok=True); shutil.copy(csvp,f'{bak}/{os.path.basename(os.path.dirname(newdir))}__{root}__{os.path.basename(csvp)}')
            if need_note and 'note' not in head:
                head.append('note')
                for r in rows[1:]:
                    if len(r)<len(head): r.append('')
            with open(csvp,'w',encoding='utf-8-sig',newline='') as fh:
                w=csv.writer(fh,lineterminator=eol); w.writerows(rows)
print(dict(cnt)); print(unresolved[:5])
