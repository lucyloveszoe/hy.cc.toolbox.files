"""Move the flat set into the library root (reports_merged/gochina) and append its CSV rows. Usage: <csv-backup-dir>"""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import PROJ
import csv,os,shutil,sys
from pathlib import Path
F=Path((PROJ+'/outputs/GoChina.flat'))
L=Path.home()/'Downloads/data.done/gochina_2026.11.19/reports_merged'
bk=Path(sys.argv[1]); bk.mkdir(parents=True)
for n in ('gochina_summary.csv','gochina_images_manifest.csv'): shutil.copy2(L/n,bk/n)
pages=sorted((F/'gochina').glob('*.html')); imgs=sorted(p for p in (F/'gochina/images/gochina').iterdir() if p.is_file())
assert not any((L/'gochina'/p.name).exists() for p in pages) and not any((L/'gochina/images/gochina'/p.name).exists() for p in imgs)
for p in pages: shutil.move(str(p),str(L/'gochina'/p.name))
for p in imgs: shutil.move(str(p),str(L/'gochina/images/gochina'/p.name))
for n in ('gochina_summary.csv','gochina_images_manifest.csv'):
    new=list(csv.reader(open(F/n,encoding='utf-8-sig',newline='')))[1:]
    raw=(L/n).read_bytes(); assert raw.endswith(b'\n') and b'\r\n' not in raw
    with open(L/n,'a',encoding='utf-8',newline='') as fh: csv.writer(fh,lineterminator='\n').writerows(new)
    print(n,'appended',len(new))
for d,_,_ in sorted(os.walk(F/'gochina'),key=lambda x:-len(x[0])):
    q=Path(d)
    if not [x for x in q.iterdir() if x.name!='.DS_Store']: (q/'.DS_Store').unlink(missing_ok=True); q.rmdir()
print('moved',len(pages),'pages',len(imgs),'images')
