#!/usr/bin/env python3 -I
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD
import os,re,html,csv,io,collections,unicodedata
H=(DD+'/mc_2026.11.19/html')
nfc=lambda s:unicodedata.normalize('NFC',os.path.normpath(s))
SIG={b'\xff\xd8\xff':('.jpg','.jpeg'),b'\x89PNG':('.png',),b'GIF8':('.gif',),b'BM':('.bmp',)}
def sniff(p):
    h=open(p,'rb').read(8)
    for k,v in SIG.items():
        if h.startswith(k): return v
def rd(p):
    raw=open(p,'rb').read(); return list(csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''))),raw.startswith(b'\xef\xbb\xbf'),b'\r\n' in raw
ATTR=re.compile(r'<(\w+)\b[^>]*?\b(src|href)\s*=\s*"([^"]*)"',re.I)
roots=[(g,r) for g in ('merges','topics','locations') for r in sorted(os.listdir(f'{H}/{g}')) if os.path.isdir(f'{H}/{g}/{r}')]
# pass 1: pages + links for all roots (global linked set)
info={}; linked=collections.Counter(); T=collections.Counter()
for g,r in roots:
    d=f'{H}/{g}/{r}'; rp=d+'/reports'
    pages=[f for f in os.listdir(rp) if f.endswith('.html')] if os.path.isdir(rp) else []
    others=[f for f in (os.listdir(rp) if os.path.isdir(rp) else []) if not f.endswith('.html') and f!='.DS_Store']
    broken=0; remote=0; bad=0; n=0
    for f in pages:
        raw=open(f'{rp}/{f}','rb').read()
        try: t=raw.decode('utf-8')
        except: bad+=1; t=raw.decode('utf-8','replace')
        if not t.rstrip().endswith('</html>') or t.count('<section')!=t.count('</section>'): bad+=1
        for tag,attr,v in ATTR.findall(t):
            v=html.unescape(v).strip()
            if not v or v.startswith(('#','mailto:','javascript:','data:')): continue
            if re.match(r'[a-z]+://',v,re.I) or v.startswith('//'): remote+=1; continue
            v=v.split('#')[0].split('?')[0]; n+=1
            tg=os.path.normpath(os.path.join(rp,v))
            if os.path.exists(tg): linked[nfc(tg)]+=1
            else: broken+=1
    info[(g,r)]=dict(pages=pages,others=others,broken=broken,remote=remote,bad=bad,links=n,rp=rp)
rows=[]; tot=collections.Counter(); issues=[]
for g,r in roots:
    d=f'{H}/{g}/{r}'; i=info[(g,r)]
    imgs=[]; fake=extm=0; ds=0
    for dp,_,fs in os.walk(d+'/images') if os.path.isdir(d+'/images') else []:
        for f in fs:
            if f=='.DS_Store': ds+=1; continue
            if f=='manifest.csv': continue
            p=os.path.join(dp,f); imgs.append(p); s=sniff(p)
            if s is None or os.path.getsize(p)==0: fake+=1
            elif not p.lower().endswith(s): extm+=1
    orph=[p for p in imgs if nfc(p) not in linked]
    # csv
    sp=f'{d}/{r}_summary.csv'; mp=f'{d}/{r}_images_manifest.csv'; cs=dict(sum_rows=0,man_rows=0,miss=0,notpage=0,dup_page=0,pg_nolist=0,img_nolist=0,ic=0,bom=True,crlf=False)
    if os.path.exists(sp) and os.path.exists(mp):
        sm,b1,c1=rd(sp); mn,b2,c2=rd(mp); cs['bom']=b1 and b2; cs['crlf']=c1 or c2
        ko=sm[0].index('output'); km=mn[0].index('output'); cs['sum_rows']=len(sm)-1; cs['man_rows']=len(mn)-1
        so=[x[ko] for x in sm[1:] if len(x)>ko and x[ko]]; mo=[x[km] for x in mn[1:] if len(x)>km and x[km]]
        cs['miss']=sum(1 for o in so+mo if not os.path.exists(os.path.normpath(os.path.join(d,o))))
        pgs={nfc(f'{i["rp"]}/{f}') for f in i['pages']}
        sres=[nfc(os.path.join(d,o)) for o in so if o.endswith('.html')]
        cs['notpage']=sum(1 for o in so if not o.endswith('.html') and o.startswith('reports/'))
        cs['dup_page']=sum(1 for v in collections.Counter(sres).values() if v>1)
        cs['pg_nolist']=len(pgs-set(sres))
        mres={nfc(os.path.join(d,o)) for o in mo}
        cs['img_nolist']=len({nfc(p) for p in imgs}-mres)
        ic=sm[0].index('images_copied') if 'images_copied' in sm[0] else None
        if ic is not None:
            for x in sm[1:]:
                if len(x)>ko and x[ko].endswith('.html') and os.path.exists(os.path.join(d,x[ko])):
                    t=open(os.path.join(d,x[ko]),encoding='utf-8').read(); dd={html.unescape(v) for v in re.findall(r'<img[^>]*?src="([^"]+)"',t)}
                    try:
                        if int(x[ic] or 0)!=len(dd): cs['ic']+=1
                    except: cs['ic']+=1
    else: cs['missing_csv']=True
    row=dict(g=g,r=r,pages=len(i['pages']),imgs=len(imgs),links=i['links'],broken=i['broken'],remote=i['remote'],bad=i['bad'],others=len(i['others']),fake=fake,extm=extm,orph=len(orph),**cs)
    rows.append(row)
    for k in ('broken','remote','bad','others','fake','extm','orph','miss','notpage','pg_nolist','img_nolist','ic','missing_csv'):
        if row.get(k): issues.append((g,r,k,row[k]))
    for k in ('pages','imgs','links','broken','orph','sum_rows','man_rows','miss'): tot[k]+=row.get(k,0)
    if not row['bom'] or row['crlf']: issues.append((g,r,'csv format',(row['bom'],row['crlf'])))
print('roots',len(rows),dict(tot))
for g in ('merges','topics','locations'):
    L=[x for x in rows if x['g']==g]; print(f'{g}: roots {len(L)} pages {sum(x["pages"] for x in L)} images {sum(x["imgs"] for x in L)} links {sum(x["links"] for x in L)} broken {sum(x["broken"] for x in L)} orphans {sum(x["orph"] for x in L)}')
print('roots with an issue:',len({(a,b) for a,b,_,_ in issues})); [print('  ',x) for x in issues]
print('dup summary pages (expected for repointed duplicates):',sum(x['dup_page'] for x in rows))
ed=[os.path.relpath(dp,H) for dp,dn,fs in os.walk(H) if not dn and not [f for f in fs if f!='.DS_Store']]; print('empty folders',ed)
print('roots without reports/:',[ (x['g'],x['r']) for x in rows if x['pages']==0])
