#!/usr/bin/env python3 -I
import csv, os, re, sys, html, shutil, collections, unicodedata, importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
GO='--go' in sys.argv
BASE=q.BASE; QR=q.QUAR+'/route'
ROOT={'上海':'上海','东北':'东北军区藏经阁','川渝':'川渝精品收藏馆','江浙':'江苏军区','山东':'山东军区冬瀌聚丽','湖南':'湖南','安徽':'安徽军区','湖北':'湖北','河南':'河南军区昔日传奇','河北':'河北','广东':'广东','广西':'广西','福建':'福建','陕西':'陕西','云南':'云南','港澳':'港澳','新疆':'新疆','贵州':'贵州','台湾':'台湾','山西':'山西','海南':'海南','甘肃':'甘肃','江西':'江西','日本':'海外','美国':'海外','俄罗斯':'海外','韩国':'海外'}
EUAF=re.compile('英国|伦敦|法国|巴黎|德国|柏林|非洲|多哥|欧洲|法兰克福|慕尼黑|阿姆斯特丹|布拉格|维也纳|米兰|罗马|巴塞罗那|马德里|欧总阅|波兰|荷兰|意大利|西班牙')
TJ=re.compile('天津|塘沽|和平区|河西区|河东区|南开区|滨海新区|北辰|西青|津南')
def body(p):
    t=open(p,encoding='utf-8',errors='replace').read(); return html.unescape(re.sub(r'<[^>]+>',' ',t))
nk=lambda s:re.sub(r'\s+','',unicodedata.normalize('NFC',s)).lower()
tiers=[r for r in csv.DictReader(open('route_tiers.tsv',encoding='utf-8'),delimiter='\t') if r['tier'] in 'AB']
m={(r['root'],r['file']):r for r in q.scan('merges')}
plan=[]
for r in tiers:
    reg=r['region']; k=(r['root'],r['file'])
    if k not in m: continue
    if reg=='京津':
        b=body(m[k]['path']); tgt='天津' if len(TJ.findall(b))>b.count('北京') else '北京军区歌舞升平'
    elif reg=='其他海外':
        tgt='欧非' if EUAF.search(body(m[k]['path'])) else '海外'
    elif reg in ROOT: tgt=ROOT[reg]
    else: continue
    assert os.path.isdir(f'{BASE}/locations/{tgt}/reports'),tgt
    plan.append((m[k],tgt))
print('to move',len(plan),collections.Counter(t for _,t in plan).most_common())
moved_paths={q.canon(r['path']) for r,_ in plan}
# link counts of every image over all reports
users=collections.defaultdict(set)
for g in ('merges','topics','locations'):
    for r in (m.values() if g=='merges' else q.scan(g)):
        for i in r['imgs']: users[i].add(q.canon(r['path']))
# target state
tstate={}
def tinfo(t):
    if t not in tstate:
        d=f'{BASE}/locations/{t}'
        tstate[t]=dict(d=d,names={nk(f) for f in os.listdir(d+'/reports')},newnames=set())
    return tstate[t]
ops=[]  # (report, tgt, newreportname, {oldimg:newimgpath})
clash=ren=reuse=0; imgcopy=0
for r,t in plan:
    ti=tinfo(t); d=ti['d']; src=r['root']
    stem=r['file'][:-5]; name=r['file']
    if nk(name) in ti['names'] or nk(name) in ti['newnames']:
        name=f'{stem[:100]} ({src}).html'; clash+=1
        assert nk(name) not in ti['names'] and nk(name) not in ti['newnames']
    ti['newnames'].add(nk(name))
    assert len(name.encode())<=240
    imap={}
    for i in r['imgs']:
        if i in imap: continue
        bn=os.path.basename(i); dst=f'{d}/images/{t}/{bn}'
        dst2=dst
        if os.path.exists(dst2) or any(dst2==v for o in ops for v in o[3].values()):
            if os.path.exists(dst2) and q.md5file(dst2)==q.md5file(i): reuse+=1
            elif any(dst2==v for o in ops for v in o[3].values()) and False: pass
            else:
                dst2=f'{d}/images/{t}/{src}__{bn}'; ren+=1
                assert not os.path.exists(dst2) or q.md5file(dst2)==q.md5file(i)
        imap[i]=dst2
    ops.append((r,t,name,imap))
# images planned in same run from different ops with same dst but other bytes?
seen={}
for r,t,n,imap in ops:
    for o,dn in imap.items():
        h=q.md5file(o)
        assert seen.setdefault(dn,h)==h,('planned clash',dn)
multi=collections.defaultdict(set)
for r,t,n,im in ops:
    for o in im: multi[o].add(t)
print('images shared across targets:',sum(1 for v in multi.values() if len(v)>1)); assert not any(len(v)>1 for v in multi.values())
print('name clashes',clash,'image renamed',ren,'reused existing',reuse)
allmoved_imgs={i for _,_,_,im in ops for i in im}
removable={i for i in allmoved_imgs if users[i]<=moved_paths}
print('images used',len(allmoved_imgs),'removable from source',len(removable),'stay (shared)',len(allmoved_imgs)-len(removable))
if not GO: print('DRY'); sys.exit()
# ---------- GO ----------
assert not os.path.exists(QR); os.makedirs(QR+'/files'); os.makedirs(QR+'/bak_csv')
srcroots={r['root'] for r,_ in plan}; tgts={t for _,t in plan}
csvs=list(q.all_csvs()); cs={}
for p in csvs:
    rows,bom,eol=q.read_csv(p)
    if rows and 'output' in rows[0]: cs[p]=[rows,bom,eol]
own={f'{BASE}/merges/{s}/{s}_summary.csv' for s in srcroots}|{f'{BASE}/merges/{s}/{s}_images_manifest.csv' for s in srcroots}
tg={f'{BASE}/locations/{t}/{t}_summary.csv' for t in tgts}|{f'{BASE}/locations/{t}/{t}_images_manifest.csv' for t in tgts}
touch=set(own)|set(tg)
oldrep={q.canon(r['path']):(t,n) for r,t,n,_ in ops}
newimg={q.canon(o):q.canon(n) for _,_,_,im in ops for o,n in im.items()}
# which CSVs need generic repoint
for p,(rows,bom,eol) in cs.items():
    if p in own or p in tg: continue
    k=rows[0].index('output')
    for r in rows[1:]:
        if len(r)>k and r[k]:
            c=q.canon(os.path.join(os.path.dirname(p),r[k]))
            if c in oldrep: touch.add(p)
            elif c in newimg and c in {q.canon(i) for i in removable}: touch.add(p)
for p in touch:
    d=QR+'/bak_csv/'+os.path.relpath(p,q.DATA); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copy2(p,d)
# 1) copy images and write reports
for r,t,name,imap in ops:
    d=f"{BASE}/locations/{t}"
    for o,n in imap.items():
        os.makedirs(os.path.dirname(n),exist_ok=True)
        if not os.path.exists(n): shutil.copy2(o,n)
        assert q.md5file(n)==q.md5file(o) if n in q.md5file.__defaults__[0] or True else 1
    txt=open(r['path'],encoding='utf-8').read(); rd=os.path.dirname(r['path'])
    def fix(mo):
        s=html.unescape(mo.group(2))
        if s.startswith(('http','data:')): return mo.group(0)
        o=q.canon(os.path.join(rd,s)); n=imap[[k for k in imap if q.canon(k)==o][0]]
        return mo.group(1)+html.escape(os.path.relpath(n,d+'/reports'),quote=True)+mo.group(3)
    txt=re.sub(r'(<img[^>]*?src=")([^"]+)(")',fix,txt)
    open(f'{d}/reports/{name}','w',encoding='utf-8',newline='').write(txt)
# 2) CSVs
def hdr_idx(h,c): return h.index(c) if c in h else -1
newrows=collections.defaultdict(list)  # target csv -> rows
for p in own:
    if p not in cs: continue
    rows,bom,eol=cs[p]; h=rows[0]; k=h.index('output'); man='status' in h; keep=[h]
    srcroot=os.path.basename(os.path.dirname(p))
    for r in rows[1:]:
        c=q.canon(os.path.join(os.path.dirname(p),r[k])) if len(r)>k and r[k] else None
        if c in oldrep and not man:
            t,n=oldrep[c]; newrows[(t,'sum')].append((h,r,f'reports/{n}')); continue
        if c in newimg and man:
            io=[i for i in newimg if i==c][0]; nn=newimg[io]; t=[t for _,t,_,im in ops if any(q.canon(x)==c for x in im)][0]
            newrows[(t,'man')].append((h,r,'images/'+os.path.relpath(nn,f'{BASE}/locations/{t}/images'))); 
            if c in {q.canon(i) for i in removable}: continue
        keep.append(r)
    cs[p][0]=keep
for (t,kind),lst in newrows.items():
    tp=f'{BASE}/locations/{t}/{t}_'+('summary.csv' if kind=='sum' else 'images_manifest.csv')
    rows,bom,eol=cs[tp]; h=rows[0]
    if kind=='sum' and 'note' not in h: h.append('note'); [x.append('') for x in rows[1:]]
    ko=h.index('output'); existing={x[ko] for x in rows[1:] if len(x)>ko}
    for sh,sr,out in lst:
        if kind=='man' and out in existing: continue
        d=dict(zip(sh,sr)); row=[d.get(c,'') for c in h]; row[ko]=out; rows.append(row); existing.add(out)
# generic repoint
allnew={}
for _,t,n,_ in ops: pass
for p,(rows,bom,eol) in cs.items():
    if p in own or p in tg: continue
    k=rows[0].index('output'); ch=False
    for r in rows[1:]:
        if len(r)>k and r[k]:
            c=q.canon(os.path.join(os.path.dirname(p),r[k]))
            if c in oldrep:
                t,n=oldrep[c]; r[k]=os.path.relpath(f'{BASE}/locations/{t}/reports/{n}',os.path.dirname(p)); ch=True
            elif c in newimg and c in {q.canon(i) for i in removable}:
                r[k]=os.path.relpath(newimg[c],os.path.dirname(p)); ch=True
    if not ch: touch.discard(p)
for p in touch:
    rows,bom,eol=cs[p]; q.write_csv(p,rows,bom,eol)
# 3) move source reports/images to quarantine
for r,_,_,_ in ops:
    dst=QR+'/files/'+os.path.relpath(r['path'],BASE); os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.move(r['path'],dst)
for i in sorted(removable):
    dst=QR+'/files/'+os.path.relpath(i,BASE); os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.move(i,dst)
with open(QR+'/moves.tsv','w',encoding='utf-8') as f:
    f.write('source\ttarget\n')
    for r,t,n,_ in ops: f.write(f"{os.path.relpath(r['path'],BASE)}\tlocations/{t}/reports/{n}\n")
print('DONE')
