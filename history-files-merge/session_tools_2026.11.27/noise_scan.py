"""READ-ONLY noise scan over html (visible text) and txt of one or more roots (PROCESSING_LOGIC 10-4).

    python3 -I noise_scan.py <root> [<root> ...]

Counts known noise patterns per file and lists lines that repeat in >= 8 files (forum boilerplate candidates)."""
import os,re,html,sys,collections,unicodedata
roots=sys.argv[1:]
PAT={'watermark':r'买春堂版权所有|maichun','edit stamp':r'本帖最[后後]由|編輯\s*$|编辑\s*$|最後編輯|最后编辑','reply notice':r'回[复覆]才能|隐藏|隱藏|需要积分|需要積分|如果您要查看','image missing':r'\[image missing\]','INCLUDEPICTURE':r'INCLUDEPICTURE|HYPERLINK',
 'nbsp':' ','u2028':'[  ]','fffd':'�','pua':'[-]','zero-width':'[​-‏‪-‮⁠﻿]','control':'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','&#N;':r'&#\d+;|&#x[0-9a-f]+;',
 'fdzone':r'FDZone|fdzone','attach':r'下載次數|下载次数|上傳|附件|KB\)|kb\)','quote':r'引用|原帖由|發表於|发表于','sig':r'^\s*-{3,}|簽名|签名'}
hits=collections.Counter(); files=collections.Counter(); lines=collections.Counter(); n=0
for R in roots:
    for d,_,fs in os.walk(R):
        for f in fs:
            p=os.path.join(d,f)
            if f.endswith('.html'):
                t=open(p,encoding='utf-8').read(); t=re.sub(r'(?is)<head.*?</head>','',t)
                parts=re.split(r'(<[^>]*>)',t); txt='\n'.join(html.unescape(x) for x in parts if not x.startswith('<'))
                raw=''.join(x for x in parts if not x.startswith('<'))
            elif f.endswith('.txt'):
                txt=raw=open(p,encoding='utf-8').read()
            else: continue
            n+=1
            for k,v in PAT.items():
                c=len(re.findall(v,raw if k=='&#N;' else txt,re.M|re.I))
                if c: hits[k]+=c; files[k]+=1
            for l in set(x.strip() for x in txt.split('\n')):
                if 2<=len(l)<=80: lines[l]+=1
print('files',n)
for k in PAT: print(f'  {k:15} hits {hits[k]:5} files {files[k]}')
print('lines in >=8 files:')
for l,c in lines.most_common(40):
    if c>=8: print(f'  {c:4} {l[:70]!r}')
