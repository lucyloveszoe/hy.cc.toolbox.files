#!/usr/bin/env python3 -I
import csv, os, re, sys, html, shutil, collections, unicodedata, importlib.util
spec=importlib.util.spec_from_file_location('q','quar_exact.py'); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
GO='--go' in sys.argv
BASE=q.BASE; M=BASE+'/merges'; T=M+'/mcjt-total'; QT=q.QUAR+'/total'
nk=lambda s:re.sub(r'\s+','',unicodedata.normalize('NFC',s)).lower()
srcs=[r for r in sorted(os.listdir(M)) if r!='mcjt-total' and os.path.isdir(f'{M}/{r}')]
assert os.listdir(T)==[] 
# inventory
reports=[]; images=[]; other=[]; docman=[]
for s in srcs:
    for dp,dn,fs in os.walk(f'{M}/{s}'):
        for f in fs:
            p=os.path.join(dp,f); rel=os.path.relpath(p,f'{M}/{s}')
            if f=='.DS_Store': continue
            if re.fullmatch(r'[^/]+_(summary|images_manifest)\.csv',rel) and dp==f'{M}/{s}': continue
            if rel.startswith('reports/') and f.endswith('.html') and rel.count('/')==1: reports.append((s,p))
            elif rel.startswith('images/') and f=='manifest.csv': docman.append((s,p))
            elif rel.startswith('images/'): images.append((s,p))
            else: other.append(p)
print('roots',len(srcs),'reports',len(reports),'image files',len(images),'other files',len(other)); print(other[:10])
assert not other
# report names
used=set(); rname={}
for s,p in reports:
    f=os.path.basename(p); n=f
    if nk(n) in used:
        n=f'{f[:-5][:100]} ({s}).html'; assert nk(n) not in used
    used.add(nk(n)); rname[q.canon(p)]=n; assert len(n.encode())<=240
print('report name clashes',sum(1 for s,p in reports if rname[q.canon(p)]!=os.path.basename(p)))
# image names
iname={}; dest={}; reuse=ren=0
for s,p in images:
    bn=os.path.basename(p); par=os.path.basename(os.path.dirname(p)); n=bn if par==s else f'{par}__{bn}'
    if n in dest or nk(n) in {nk(x) for x in ()}: pass
    key=nk(n)
    if key in dest:
        if q.md5file(dest[key][1])==q.md5file(p): iname[q.canon(p)]=dest[key][0]; reuse+=1; continue
        n=f'{s}__{n}'; key=nk(n); ren+=1; assert key not in dest
    dest[key]=(n,p); iname[q.canon(p)]=n
print('image files',len(images),'unique dest',len(dest),'reused identical',reuse,'renamed',ren)
# csv rows
rows_sum=[]; rows_man=[]; hsum=['page','mode','posts_in_page','posts_saved','images_copied','unresolved_img_refs','output','note']; hman=['source_file','status','output']
repoint=0; blank=0; ext=0; dupskip=0
seen_out=set()
def newout(csvdir,o,kind):
    global repoint,ext
    if not o: return ''
    c=q.canon(os.path.join(csvdir,o))
    if c in rname: repoint+=1; return 'reports/'+rname[c]
    if c in iname: repoint+=1; return 'images/mcjt-total/'+iname[c]
    ext+=1; return os.path.relpath(os.path.join(csvdir,o),T)   # outside merges: same depth => unchanged
for s in srcs:
    for kind,fn in (('sum',f'{s}_summary.csv'),('man',f'{s}_images_manifest.csv')):
        p=f'{M}/{s}/{fn}'
        if not os.path.exists(p): continue
        rows,bom,eol=q.read_csv(p); h=rows[0]; d=os.path.dirname(p)
        for r in rows[1:]:
            dd=dict(zip(h,r)); o=newout(d,dd.get('output',''),kind)
            if o: seen_out.add(o)
            else: blank+=1
            dd['output']=o
            (rows_sum if kind=='sum' else rows_man).append([dd.get(c,'') for c in (hsum if kind=='sum' else hman)])
docinfo={}
for s_,p in docman:
    par=os.path.basename(os.path.dirname(p))
    for r in csv.DictReader(open(p,encoding='utf-8-sig')):
        ip=os.path.join(os.path.dirname(p),r['image']); n=iname[q.canon(ip)]
        rows_man.append([r['original_url'],'copied: carved from .doc (original url)','images/mcjt-total/'+n]); docinfo[par]=docinfo.get(par,0)+1
for par,cnt in docinfo.items():
    rn=[n for c,n in rname.items() if os.path.basename(c)==par+'.html']; assert len(rn)==1
    rows_sum.append([par+'.doc','doc','','',str(cnt),'','reports/'+rn[0],''])
print('doc folders',docinfo)
print('summary rows',len(rows_sum),'manifest rows',len(rows_man),'blank outputs',blank,'outside-merges outputs',ext,'dup image rows skipped',dupskip)
# every moved image / report referenced by a manifest/summary row
man_out={r[2] for r in rows_man if r[2]}; sum_out={r[6] for r in rows_sum if r[6]}
print('images without manifest row',sum(1 for k,(n,p) in dest.items() if 'images/mcjt-total/'+n not in man_out),
      '| reports without summary row',sum(1 for n in rname.values() if 'reports/'+n not in sum_out))
# other CSVs pointing into merges
extra=0
for p in q.all_csvs():
    if p.startswith(M+'/') and os.path.dirname(p)!=M and os.path.basename(os.path.dirname(p)) in srcs: continue
    rows,_,_=q.read_csv(p)
    if not rows or 'output' not in rows[0]: continue
    k=rows[0].index('output')
    for r in rows[1:]:
        if len(r)>k and r[k] and (q.canon(os.path.join(os.path.dirname(p),r[k])) in rname or q.canon(os.path.join(os.path.dirname(p),r[k])) in iname): extra+=1
print('rows in other CSVs pointing into moved files',extra)
if not GO: print('DRY'); sys.exit()
# GO
assert not os.path.exists(QT); os.makedirs(QT+'/orig_reports'); os.makedirs(QT+'/csv')
for s in srcs:
    for fn in os.listdir(f'{M}/{s}'):
        if fn.endswith('.csv'):
            os.makedirs(f'{QT}/csv/{s}',exist_ok=True); shutil.copy2(f'{M}/{s}/{fn}',f'{QT}/csv/{s}/{fn}')
os.makedirs(T+'/reports'); os.makedirs(T+'/images/mcjt-total')
for key,(n,p) in dest.items(): shutil.copy2(p,f'{T}/images/mcjt-total/{n}'); assert q.md5file(f'{T}/images/mcjt-total/{n}')==q.md5file(p)
for s,p in reports:
    txt=open(p,encoding='utf-8').read(); rd=os.path.dirname(p)
    def fix(mo):
        v=html.unescape(mo.group(2))
        if v.startswith(('http','data:')): return mo.group(0)
        return mo.group(1)+html.escape('../images/mcjt-total/'+iname[q.canon(os.path.join(rd,v))],quote=True)+mo.group(3)
    txt=re.sub(r'(<img[^>]*?src=")([^"]+)(")',fix,txt)
    open(f'{T}/reports/{rname[q.canon(p)]}','w',encoding='utf-8',newline='').write(txt)
def wr(path,h,rows):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,lineterminator='\n'); w.writerow(h); w.writerows(rows)
wr(f'{T}/mcjt-total_summary.csv',hsum,rows_sum); wr(f'{T}/mcjt-total_images_manifest.csv',hman,rows_man)
# generic repoint of other CSVs
for p in q.all_csvs():
    if os.path.dirname(p).startswith(T) : continue
    if os.path.basename(os.path.dirname(p)) in srcs and p.startswith(M+'/'): continue
    rows,bom,eol=q.read_csv(p)
    if not rows or 'output' not in rows[0]: continue
    k=rows[0].index('output'); ch=False
    for r in rows[1:]:
        if len(r)>k and r[k]:
            c=q.canon(os.path.join(os.path.dirname(p),r[k]))
            nw=('reports/'+rname[c]) if c in rname else ('images/mcjt-total/'+iname[c]) if c in iname else None
            if nw: r[k]=os.path.relpath(f'{T}/{nw}',os.path.dirname(p)); ch=True
    if ch:
        d=QT+'/csv_other/'+os.path.relpath(p,q.DATA); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copy2(p,d); q.write_csv(p,rows,bom,eol)
# retire sources: originals -> quarantine, source csvs -> removed (copies saved)
for s,p in reports:
    d=f'{QT}/orig_reports/{s}/'+os.path.basename(p); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.move(p,d)
for s,p in images: os.remove(p) if os.path.exists(f'{T}/images/mcjt-total/{iname[q.canon(p)]}') else None
for s_,p in docman:
    d=QT+'/doc_manifests/'+os.path.basename(os.path.dirname(p))+'.manifest.csv'; os.makedirs(os.path.dirname(d),exist_ok=True); shutil.move(p,d)
for s in srcs:
    for fn in os.listdir(f'{M}/{s}'):
        if fn.endswith('.csv'): os.remove(f'{M}/{s}/{fn}')
print('DONE')
