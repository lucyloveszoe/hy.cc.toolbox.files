#!/usr/bin/env python3 -I
import os,re,sys,shutil,collections
GO='--go' in sys.argv
B='/Users/hany/Downloads/data.done/mc_2026.11.19/html'; KEY='以下内容需要回复才能看到'; BK='/Users/hany/Downloads/backup.placeholder.2026.11.22'
BR=r'<br\s*/?>'
full=re.compile(r'(?P<pre>(?:'+BR+r'\s*)+)'+KEY+r'(?P<post>(?:\s*'+BR+r')*)',re.I)
CJ=re.compile(r'[一-鿿]')
def fix(t):
    def r(m):
        end=t[m.end():m.end()+12].lstrip()
        return '' if end.startswith('</') else '<br><br>'
    n=0
    def sub(m):
        nonlocal n; n+=1; return r(m)
    t2=full.sub(sub,t)
    k=t2.count(KEY)
    if k: t2=re.sub(r'[ \t]*'+KEY,'',t2); n+=k
    return t2,n
files=occ=bad=inline=0; changed=[]
for dp,_,fs in os.walk(B):
    for f in fs:
        if not f.endswith('.html'): continue
        p=os.path.join(dp,f); t=open(p,encoding='utf-8').read()
        if KEY not in t: continue
        t2,n=fix(t)
        # safety: removed CJK must be exactly n copies of KEY; nothing else changes (img / a / title count)
        before=collections.Counter(CJ.findall(t)); after=collections.Counter(CJ.findall(t2)); rem=before-after
        exp=collections.Counter(KEY*n)
        ok = rem==exp and not (after-before) and KEY not in t2 and t.count('<img')==t2.count('<img') and t.count('<section')==t2.count('<section') and t2.rstrip().endswith('</html>')==t.rstrip().endswith('</html>')
        if not ok: bad+=1; print('CHECK FAILED',os.path.relpath(p,B)); continue
        files+=1; occ+=n; changed.append((p,t2))
print('files',files,'occurrences',occ,'failed checks',bad)
if not GO or bad: print('DRY' if not GO else 'ABORT (failed checks)'); sys.exit()
assert not os.path.exists(BK)
for p,t2 in changed:
    d=BK+'/'+os.path.relpath(p,B); os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copy2(p,d)
    open(p,'w',encoding='utf-8',newline='').write(t2)
print('DONE; backup',BK)
