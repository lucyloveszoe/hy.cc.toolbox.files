"""Copy the reports/images of a layout-A root into the flat layout B (PROCESSING_RULES 40.5).
Usage: python3 -I flatten_set.py <layout-A root> <dest root> <set> [--go]
dest/<set>_summary.csv, dest/<set>_images_manifest.csv, dest/<set>/<folder>__<page>.html, dest/<set>/images/<set>/<folder>__<image>.
Links are written raw (html.escape, never percent-encoded). Rows without an output are not carried over."""
import re,sys,csv,html,shutil
from pathlib import Path
src=Path(sys.argv[1]); dest=Path(sys.argv[2]); S=sys.argv[3]; go='--go' in sys.argv
def newname(rel):            # rel relative to reports/ or images/ ; first dir = old folder
    return rel.parts[0]+'__'+rel.parts[-1]
pages={}; names={}
for p in sorted((src/'reports').rglob('*.html')):
    n=newname(p.relative_to(src/'reports')); assert n.lower() not in names,('clash',n); names[n.lower()]=p; pages[p]=n
imgs={}; inames={}
for p in sorted(f for f in (src/'images').rglob('*') if f.is_file() and f.name!='.DS_Store'):
    n=newname(p.relative_to(src/'images')); assert n.lower() not in inames,('clash',n); inames[n.lower()]=p; imgs[p.resolve()]=n
assert all(len(n.encode())<=255 for n in list(pages.values())+list(imgs.values()))
print('pages',len(pages),'images',len(imgs))
if not go: sys.exit()
if dest.exists(): sys.exit('dest exists')
(dest/S/'images'/S).mkdir(parents=True)
for p,n in pages.items():
    t=p.read_text(encoding='utf-8')
    def rep(m):
        tgt=(p.parent/html.unescape(m.group(2))).resolve()
        return m.group(1)+html.escape(f'images/{S}/{imgs[tgt]}',quote=True)+m.group(3)
    t=re.sub(r'(<img[^>]+src=")([^"]+)(")',rep,t)
    (dest/S/n).write_text(t,encoding='utf-8')
for p,n in imgs.items(): shutil.copy2(p,dest/S/'images'/S/n)
bypage={str(p.relative_to(src)):n for p,n in pages.items()}
byimg={str(Path(p).resolve().relative_to(src.resolve())):n for p,n in imgs.items()}
kept={'summary':0,'manifest':0}; dropped={'summary':0,'manifest':0}
for kind,suffix,mp,pre in (('summary','_summary.csv',bypage,f'{S}/'),('manifest','_images_manifest.csv',byimg,f'{S}/images/{S}/')):
    rows_out=[];head=None
    for f in sorted(src.glob('*'+suffix)):
        raw=f.read_bytes(); eol='\r\n' if b'\r\n' in raw else '\n'
        rows=list(csv.reader(open(f,encoding='utf-8-sig',newline='')))
        head=rows[0]; oi=head.index('output')
        for r in rows[1:]:
            if not r[oi]: dropped[kind]+=1; continue
            r[oi]=pre+mp[r[oi]]; rows_out.append(r); kept[kind]+=1
    with open(dest/f'{S}{suffix}','w',encoding='utf-8-sig',newline='') as fh:
        w=csv.writer(fh,lineterminator='\n'); w.writerow(head); w.writerows(rows_out)
print('csv rows kept',kept,'dropped (no output)',dropped)
