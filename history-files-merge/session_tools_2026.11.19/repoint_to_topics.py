import csv,os,sys,glob,collections,shutil
GO='--go' in sys.argv
P='/Users/hany/Documents/cc.self/hy.cc.toolbox.files/history-files-merge'
D='/Users/hany/Downloads/data.done/mc_2026.11.19'; T=D+'/txt'
SP=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
route={r['file'].replace('／','/'):r['topic'] for r in csv.DictReader(open(T+'/topics/routing_report.csv',encoding='utf-8-sig'))}
dup={l.split('\t')[1]:l.rstrip('\n').split('\t')[2] for l in open(SP+'/txt_cand/removed.tsv',encoding='utf-8') if l.startswith('DUP')}
cnt=collections.Counter(); bad=[]
for csvp in sorted(glob.glob(D+'/html/*/*/*.csv')):
    newdir=os.path.dirname(csvp); root=os.path.basename(newdir); grp=os.path.basename(os.path.dirname(newdir))
    rows=list(csv.reader(open(csvp,encoding='utf-8-sig',newline='')))
    head=rows[0]
    if 'output' not in head: continue
    oi=head.index('output')
    if not any(r[oi].endswith('mc_merged.txt') for r in rows[1:] if len(r)>oi): continue
    bk=f'{SP}/bak_csv_move/{grp}__{root}__{os.path.basename(csvp)}'
    brows=list(csv.reader(open(bk,encoding='utf-8-sig',newline='')))
    assert len(brows)==len(rows) or True
    bmap={}
    for b in brows[1:]: bmap.setdefault(b[0],[]).append(b)
    olddir=f'{P}/outputs/{root}'; changed=False
    for i,r in enumerate(rows[1:],1):
        if len(r)<=oi or not r[oi].endswith('mc_merged.txt'): continue
        b=brows[i] if i<len(brows) and brows[i][0]==r[0] else None
        if b is None: bad.append((root,r[0][:30],'row mismatch')); cnt['row mismatch']+=1; continue
        a=os.path.normpath(os.path.join(olddir,b[oi])); rel=os.path.relpath(a,T)
        story=rel if rel in route else dup.get(rel)
        if story is None or story not in route: bad.append((root,rel[:50],'no story')); cnt['no story']+=1; continue
        tf=f'{T}/topics/mc_{route[story]}.txt'
        if not os.path.exists(tf): bad.append((root,route[story],'no topic file')); cnt['no topic file']+=1; continue
        r[oi]=os.path.relpath(tf,newdir); changed=True; cnt['repointed']+=1; cnt['topic:'+route[story]]+=1
    if changed and GO:
        os.makedirs(SP+'/bak_csv_topics',exist_ok=True); shutil.copy(csvp,f'{SP}/bak_csv_topics/{grp}__{root}__{os.path.basename(csvp)}')
        eol='\r\n' if b'\r\n' in open(csvp,'rb').read() else '\n'
        with open(csvp,'w',encoding='utf-8-sig',newline='') as fh: csv.writer(fh,lineterminator=eol).writerows(rows)
print(dict(collections.Counter({k:v for k,v in cnt.items() if not k.startswith('topic:')}))); print('top topics',[(k[6:],v) for k,v in cnt.most_common(40) if k.startswith('topic:')][:6]); print(bad[:5])
