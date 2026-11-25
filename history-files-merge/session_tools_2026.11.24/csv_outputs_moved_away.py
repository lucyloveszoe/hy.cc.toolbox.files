"""CSV `output` cells that point at content moved out of the root (images.only/, txt/): blank them, append
' [output file no longer in data.done]' to `status` when the column exists (12.4). Keeps BOM/EOL. Usage: <root> <backup dir> [--go]"""
import csv,glob,os,sys,shutil
R,BK=sys.argv[1],sys.argv[2];GO='--go' in sys.argv;os.chdir(R);n=0
for f in sorted(glob.glob('*.csv')):
    raw=open(f,'rb').read();eol='\r\n' if b'\r\n' in raw else '\n'
    rows=list(csv.reader(open(f,encoding='utf-8-sig',newline='')));h=rows[0]
    if 'output' not in h: continue
    oi=h.index('output');si=h.index('status') if 'status' in h else None;ch=0
    for r in rows[1:]:
        if r[oi] and not os.path.exists(r[oi]) and r[oi].split('/')[0] in('images.only','txt'):
            r[oi]=''
            if si is not None and 'no longer' not in r[si]: r[si]+=' [output file no longer in data.done]'
            ch+=1
    n+=ch
    if ch and GO:
        os.makedirs(BK,exist_ok=True);shutil.copy2(f,os.path.join(BK,f))
        with open(f,'w',encoding='utf-8-sig',newline='') as o: csv.writer(o,lineterminator=eol).writerows(rows)
print('rows',n)
