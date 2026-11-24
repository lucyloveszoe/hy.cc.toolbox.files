import re,csv,html,shutil,sys,hashlib
from pathlib import Path
L=Path.home()/'Downloads/data.done/gochina_2026.11.19/reports_merged'; G=L/'gochina'; I=G/'images/gochina'
Q=Path(sys.argv[1]); go='--go' in sys.argv
pre='GoChina_2005_07_'; mid='綜合論壇 - 【圖文報告】阿平連三月出征 7-22 第三夜 阿平不舉___殘念.html'
a=G/(pre+'III__'+mid); b=G/(pre+'V__'+mid); assert a.is_file() and b.is_file()
im=lambda p:[html.unescape(i).rsplit('/',1)[-1] for i in re.findall(r'<img[^>]+src="([^"]+)"',p.read_text(encoding='utf-8'))]
ia,ib=im(a),im(b); assert len(ia)==len(ib)
sha=lambda n:hashlib.sha256((I/n).read_bytes()).hexdigest()
diff=[(x,y,(I/x).stat().st_size,(I/y).stat().st_size) for x,y in zip(ia,ib) if sha(x)!=sha(y)]
print('III images',len(ia),'differing from V',diff)
assert all(s2>=s1 for _,_,s1,s2 in diff),'V picture smaller'
used=set()
for p in G.glob('*.html'):
    if p!=a: used|=set(im(p))
dele=[n for n in set(ia) if n not in used]; print('images only III uses',len(dele),'| shared with other pages',len(set(ia))-len(dele))
if not go: sys.exit()
(Q/'images').mkdir(parents=True); shutil.copy2(L/'gochina_summary.csv',Q/'s.csv'); shutil.copy2(L/'gochina_images_manifest.csv',Q/'m.csv')
shutil.move(str(a),str(Q/a.name))
for n in dele: shutil.move(str(I/n),str(Q/'images'/n))
for f,pfx,gone in (('gochina_summary.csv','gochina/',{a.name}),('gochina_images_manifest.csv','gochina/images/gochina/',set(dele))):
    raw=(L/f).read_bytes(); eol='\r\n' if b'\r\n' in raw else '\n'
    rows=list(csv.reader(open(L/f,encoding='utf-8-sig',newline=''))); oi=rows[0].index('output')
    out=[rows[0]]+[r for r in rows[1:] if not (r[oi].startswith(pfx) and r[oi][len(pfx):] in gone)]
    with open(L/f,'w',encoding='utf-8-sig',newline='') as fh: csv.writer(fh,lineterminator=eol).writerows(out)
    print(f,'rows removed',len(rows)-len(out))
