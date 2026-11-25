"""Noise pass over a consolidated root (rules 4.4 + PUA): edit stamps (+ trailing garbage tokens), reply-to-see notices,
private-use characters, stray <br> runs. In place, on *.html and txt/**/*.txt. Usage: clean_noise_pass.py <root>"""
import re,os,sys,collections
R=sys.argv[1]
GAR=r'(?:[ \xa0\u3000](?:&(?:amp|quot|lt|gt|#x27|#39);|[!-;=-~]){1,2})*(?=[ \xa0\u3000]*(?:[\n<]|$|[^\x00-\x7f]))'
STAMP=re.compile(r'\[?\s*本帖最[后後]由[^<\n]{1,60}?[于於][^<\n]{1,40}?[编編][辑輯]\s*\]?'+GAR)
REPLY=re.compile(r'本帖[隐隱]藏的[内內](?:容需要[回]?[复復]才可以[浏瀏][览覽])?')
PUA=re.compile('[-]')
c=collections.Counter()
for dp,_,fn in os.walk(R):
    for f in fn:
        p=os.path.join(dp,f)
        isH=f.endswith('.html'); isT=f.endswith('.txt') and os.sep+'txt'+os.sep in p and not f.startswith('141.')
        if not(isH or isT): continue
        t=o=open(p,encoding='utf-8').read()
        t,a=STAMP.subn('',t); c['stamp']+=a
        t,b=REPLY.subn('',t); c['reply']+=b
        t,d=PUA.subn('',t); c['pua']+=d
        if isH: t=re.sub(r'(?:<br\s*/?>\s*){3,}','<br><br>',t); t=re.sub(r'(?:<br\s*/?>\s*)+(?=</section>)','',t)
        else: t='\n'.join(l.rstrip() for l in t.split('\n')); t=re.sub(r'\n{3,}','\n\n',t)
        if t!=o: open(p,'w',encoding='utf-8',newline='').write(t); c['files']+=1
print(dict(c))
