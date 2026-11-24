"""Strip the '<folder>__' prefix from page and image names in reports_merged/gochina where the stripped name is unique
(case-insensitive, counting unprefixed names). Rewrites <img src> in the pages and the `output` column of both CSVs.
Usage: python3 -I strip_prefixes.py <backup-dir> [--go]   (dry run without --go)"""
import csv,html,os,re,shutil,sys
from pathlib import Path
L=Path.home()/'Downloads/data.done/gochina_2026.11.19/reports_merged'; G=L/'gochina'; I=G/'images/gochina'
bk=Path(sys.argv[1]); go='--go' in sys.argv
def plan(d,ext=None):
    names=[p.name for p in d.iterdir() if p.is_file() and p.name!='.DS_Store' and (ext is None or p.suffix==ext)]
    cnt={}
    for n in names:
        k=(n.split('__',1)[1] if '__' in n else n).lower(); cnt[k]=cnt.get(k,0)+1
    return {n:n.split('__',1)[1] for n in names if '__' in n and cnt[n.split('__',1)[1].lower()]==1}
pm=plan(G,'.html'); im=plan(I)
print('pages to rename',len(pm),'images to rename',len(im))
if not go: sys.exit()
bk.mkdir(parents=True); (bk/'pages').mkdir()
for f in L.glob('*.csv'): shutil.copy2(f,bk/f.name)
for p in G.glob('*.html'): shutil.copy2(p,bk/'pages'/p.name)
# 1. pages: rewrite links, write under the new name
def rep(m):
    src=html.unescape(m.group(2)); n=src.rsplit('/',1)[-1]
    if src.startswith('images/gochina/') and n in im: src='images/gochina/'+im[n]
    return m.group(1)+html.escape(src,quote=True)+m.group(3)
for p in sorted(G.glob('*.html')):
    t=p.read_text(encoding='utf-8'); t2=re.sub(r'(<img[^>]+src=")([^"]+)(")',rep,t)
    new=G/pm.get(p.name,p.name)
    if new!=p:
        assert not new.exists(),new
        new.write_text(t2,encoding='utf-8'); p.unlink()
    elif t2!=t: p.write_text(t2,encoding='utf-8')
# 2. images
for o,n in im.items():
    assert not (I/n).exists(); os.rename(I/o,I/n)
# 3. CSVs
for f,pre,mp in (('gochina_summary.csv','gochina/',pm),('gochina_images_manifest.csv','gochina/images/gochina/',im)):
    raw=(L/f).read_bytes(); eol='\r\n' if b'\r\n' in raw else '\n'
    rows=list(csv.reader(open(L/f,encoding='utf-8-sig',newline=''))); oi=rows[0].index('output'); ch=0
    for r in rows[1:]:
        o=r[oi]
        if o.startswith(pre) and o[len(pre):] in mp: r[oi]=pre+mp[o[len(pre):]]; ch+=1
    with open(L/f,'w',encoding='utf-8-sig',newline='') as fh: csv.writer(fh,lineterminator=eol).writerows(rows)
    print(f,'rows changed',ch)
