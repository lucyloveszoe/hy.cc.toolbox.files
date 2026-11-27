#!/usr/bin/env python3 -I
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import DD
import os,re,html,csv,io,collections,unicodedata,hashlib
ROOT=(DD+'/gochina_2026.11.19/reports_merged'); S='gochina'; PG=f'{ROOT}/{S}'; IMD=f'{PG}/images/{S}'
nfc=lambda s:unicodedata.normalize('NFC',s)
SIG={b'\xff\xd8\xff':'jpg',b'\x89PNG':'png',b'GIF8':'gif',b'BM':'bmp'}
def sniff(p):
    h=open(p,'rb').read(8)
    for k,v in SIG.items():
        if h.startswith(k): return v
    return None
pages=[f for f in os.listdir(PG) if f.endswith('.html')]
others=[f for f in os.listdir(PG) if not f.endswith('.html') and f not in('images','.DS_Store')]
print('pages',len(pages),'| other files in set folder',others,'| nested folders in set dir',[d for d in os.listdir(PG) if os.path.isdir(f'{PG}/{d}') and d!='images'])
imgs=[]; extra=[]
for dp,dn,fs in os.walk(PG+'/images'):
    for f in fs:
        p=os.path.join(dp,f)
        if f=='.DS_Store': extra.append(p); continue
        imgs.append(p)
print('files under images',len(imgs),'| .DS_Store',len(extra),'| image dir levels ok:',all(os.path.dirname(p)==IMD for p in imgs))
nonimg=[p for p in imgs if sniff(p) is None or os.path.getsize(p)==0]
print('files whose header is not an image or size 0:',len(nonimg),[os.path.relpath(p,PG)[:60] for p in nonimg[:5]])
ext_bad=[]
EXT={'jpg':('.jpg','.jpeg'),'png':('.png',),'gif':('.gif',),'bmp':('.bmp',)}
for p in imgs:
    s=sniff(p)
    if s and not p.lower().endswith(EXT[s]): ext_bad.append(p)
print('extension does not match header:',len(ext_bad),[os.path.basename(p)[:40] for p in ext_bad[:3]])
# links
ATTR=re.compile(r'<(\w+)\b[^>]*?\b(src|href)\s*=\s*"([^"]*)"',re.I)
linked=collections.Counter(); broken=[]; remote=0; other_tags=collections.Counter(); wf=0; utf=0
for f in pages:
    t=open(f'{PG}/{f}','rb').read()
    try: t=t.decode('utf-8')
    except: utf+=1; t=t.decode('utf-8','replace')
    if not t.rstrip().endswith('</html>') or t.count('<section')!=t.count('</section>'): wf+=1
    for tag,attr,v in ATTR.findall(t):
        v=html.unescape(v).strip()
        if not v or v.startswith(('#','mailto:','javascript:','data:')): continue
        if re.match(r'[a-z]+://',v,re.I) or v.startswith('//'): remote+=1; continue
        v=v.split('#')[0].split('?')[0]
        other_tags[tag.lower()]+=1
        tgt=os.path.normpath(os.path.join(PG,v))
        if os.path.exists(tgt): linked[nfc(tgt)]+=1
        else: broken.append((f[:40],v[:50]))
print('local links',dict(other_tags),'| remote',remote,'| BROKEN',len(broken),broken[:3],'| not-utf8 pages',utf,'| malformed pages',wf)
orph=[p for p in imgs if nfc(os.path.normpath(p)) not in linked]
print('orphan images (no page links them):',len(orph),[os.path.basename(p)[:40] for p in orph[:5]])
# csv
def rd(p):
    raw=open(p,'rb').read(); bom=raw.startswith(b'\xef\xbb\xbf'); return list(csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''))),bom,(b'\r\n' in raw)
sm,b1,c1=rd(f'{ROOT}/{S}_summary.csv'); mn,b2,c2=rd(f'{ROOT}/{S}_images_manifest.csv')
print('csv BOM',b1,b2,'CRLF',c1,c2,'| summary',len(sm)-1,'rows cols',sm[0],'| manifest',len(mn)-1,'rows cols',mn[0])
ko=sm[0].index('output'); outs=[r[ko] for r in sm[1:] if len(r)>ko and r[ko]]
mout=[r[mn[0].index('output')] for r in mn[1:] if r[mn[0].index('output')]]
print('summary outputs',len(outs),'missing',sum(1 for o in outs if not os.path.exists(f'{ROOT}/{o}')),'| not .html',sum(1 for o in outs if not o.endswith('.html')),'| listed >1x',sum(1 for v in collections.Counter(outs).values() if v>1))
print('pages not in summary',len(set(nfc(f'{S}/{f}') for f in pages)-set(nfc(o) for o in outs)),'| summary outputs not a page',len(set(nfc(o) for o in outs)-set(nfc(f'{S}/{f}') for f in pages)))
print('manifest outputs',len(mout),'missing',sum(1 for o in mout if not os.path.exists(f'{ROOT}/{o}')),'| distinct',len(set(mout)))
print('images not in manifest',len(set(nfc(os.path.relpath(p,ROOT)) for p in imgs)-set(nfc(o) for o in mout)),'| manifest outputs not an image file',len(set(nfc(o) for o in mout)-set(nfc(os.path.relpath(p,ROOT)) for p in imgs)))
sc=mn[0].index('status'); st=collections.Counter(r[sc].split(':')[0] for r in mn[1:]); print('manifest status',dict(st))
blank=[r for r in mn[1:] if not r[mn[0].index('output')]]; print('manifest rows with blank output',len(blank),'| of which status copied (should carry a tag):',sum(1 for r in blank if r[sc].startswith('copied') and 'no longer' not in r[sc]))
# images_copied vs distinct images per page
ic=sm[0].index('images_copied'); mism=0
for r in sm[1:]:
    if len(r)>ko and r[ko].endswith('.html') and os.path.exists(f'{ROOT}/{r[ko]}'):
        t=open(f'{ROOT}/{r[ko]}',encoding='utf-8').read(); d={html.unescape(v) for v in re.findall(r'<img[^>]*?src="([^"]+)"',t)}
        try:
            if int(r[ic] or 0)!=len(d): mism+=1
        except: mism+=1
print('summary images_copied != distinct <img> in page:',mism)
# empty dirs / ds_store
ed=[dp for dp,dn,fs in os.walk(ROOT) if not dn and not [f for f in fs if f!='.DS_Store']]; print('empty folders',ed)
