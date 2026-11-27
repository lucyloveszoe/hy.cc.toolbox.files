"""Find reports in GoChina.consolidated that already exist in the library (exact: text + image SHA-256 sequence).
Usage: python3 -I report_vs_library.py <plan.json>   (read-only; writes the plan)"""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from hfm_config import PROJ
import re,sys,json,hashlib,html
from pathlib import Path
D=Path.home()/'Downloads/data.done'
C=Path((PROJ+'/outputs/GoChina.consolidated'))
norm=lambda s: re.sub(r'\s+','',re.sub(r'<[^>]+>','',re.sub(r'(?s)<head>.*?</head>|<h1>.*?</h1>','',s))).lower()
cache={}
def sha(p):
    k=str(p)
    if k not in cache:
        try: cache[k]=hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError: cache[k]='missing:'+p.name
    return cache[k]
def sig(p):
    t=p.read_text(encoding='utf-8',errors='replace')
    imgs=[(p.parent/html.unescape(i)) for i in re.findall(r'<img[^>]+src="([^"]+)"',t)]
    imgs=[i for i in imgs if 'http' not in str(i)[:0]]
    return hashlib.md5(norm(t).encode()).hexdigest(),tuple(sha(i) for i in imgs),imgs
lib={};libtxt={}
for root in (D/'gochina_2026.11.19/reports_merged',D/'mc_2026.11.19/html'):
    for p in root.rglob('*.html'):
        h,s,_=sig(p); lib.setdefault((h,s),str(p)); libtxt.setdefault(h,str(p))
print('library reports',len(lib),'distinct text',len(libtxt),file=sys.stderr)
plan={'exact':[],'text_only':[],'none':0}
for p in sorted((C/'reports').rglob('*.html')):
    h,s,imgs=sig(p)
    if (h,s) in lib: plan['exact'].append([str(p),lib[(h,s)]])
    elif h in libtxt and len(norm(p.read_text(encoding='utf-8')))>=50: plan['text_only'].append([str(p),libtxt[h],len(imgs)])
    else: plan['none']+=1
json.dump(plan,open(sys.argv[1],'w'),ensure_ascii=False)
print('exact',len(plan['exact']),'text-only',len(plan['text_only']),'unique',plan['none'])
