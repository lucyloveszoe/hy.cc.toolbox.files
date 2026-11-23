#!/usr/bin/env python3 -I
import csv,os,re,html,hashlib,sys,unicodedata
GO='--go' in sys.argv
D='/Users/hany/Downloads/data.done'; F=D+'/至2014年旅行记录'; FZ='/Users/hany/Downloads/data.frozen/Reports.series-2026.11.17/'
S='/Users/hany/Downloads/data/2018.06.18_report_word_doc_txt_imgs/'
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
dn={r['path']:r for r in csv.DictReader(open('compare_done.tsv',encoding='utf-8'),delimiter='\t')}
fz={r['path'].replace(S,''):r for r in csv.DictReader(open('compare_src.tsv',encoding='utf-8'),delimiter='\t') if r['origin']=='至2014年旅行记录'}
def lv(b): return 3 if b.startswith(('same text','text >=0.90')) else 0
texts=[]; imgs=[]
for p,d in dn.items():
    f=fz.get(p)
    if lv(d['bucket']) or (f and lv(f['bucket'])):
        src=('done',d['best']) if lv(d['bucket']) else ('frozen',f['best'])
        texts.append((p,src))
    if d['bucket']=='image: already in data.done': imgs.append((p,d['best']))
print('text files',len(texts),'| images',len(imgs))
# pages in the folder and what they link
owned=set()
for dp,_,fs in os.walk(F):
    for fn in fs:
        if fn.lower().endswith(('.htm','.html')):
            raw=open(os.path.join(dp,fn),'rb').read(); t=raw.decode('utf-8','ignore')+raw.decode('gb18030','ignore')
            for v in re.findall(r'(?:src|href)\s*=\s*["\']?([^"\' >]+)',t,re.I):
                v=html.unescape(v).split('#')[0].split('?')[0]
                if v and not re.match(r'[a-z]+:',v,re.I): owned.add(unicodedata.normalize('NFC',os.path.normpath(os.path.join(dp,v))))
plan=[]; skipped=[]
for p,(where,best) in texts:
    fp=D+'/'+p
    ref=(FZ if where=='frozen' else D+'/')+best
    if not os.path.exists(fp): skipped.append((p,'missing')); continue
    assert os.path.exists(ref),('match target missing',ref)
    plan.append((fp,f'{where}:{best}'))
for p,best in imgs:
    fp=D+'/'+p; ref=D+'/'+best
    if not os.path.exists(fp): skipped.append((p,'missing')); continue
    assert os.path.exists(ref) and sha(ref)==sha(fp),('no identical copy',p)
    if unicodedata.normalize('NFC',os.path.normpath(fp)) in owned or '_files/' in fp: skipped.append((p,'linked by a saved page')); continue
    plan.append((fp,'data.done:'+best))
print('to delete',len(plan),'| skipped',skipped)
print('MB',sum(os.path.getsize(p) for p,_ in plan)/1e6)
for p,b in plan[:8]: print('  ',os.path.relpath(p,F)[:60],'<-',b[:60])
if not GO: print('DRY'); sys.exit()
open('del39_log.tsv','w',encoding='utf-8').write('removed\tkept/matched\n'+''.join(f'{os.path.relpath(p,D)}\t{b}\n' for p,b in plan))
for p,_ in plan: os.remove(p)
gone=0
for dp,dn_,fs in os.walk(F,topdown=False):
    if dp==F: continue
    ls=os.listdir(dp)
    if not ls or ls==['.DS_Store']:
        if ls: os.remove(dp+'/.DS_Store')
        os.rmdir(dp); gone+=1
print('DONE; empty folders removed',gone)
