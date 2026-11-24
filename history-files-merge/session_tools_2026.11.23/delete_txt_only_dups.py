"""Delete files in ~/Downloads/txt-only whose content is already in the target stories.

Targets: data.done/gochina_2026.11.19/txt_merged.txt and data.done/mc_2026.11.19/txt/**/*.txt (stories cut by their manifests).
Comparison: lower-case, all whitespace removed, exact equality of the whole story.
Only .txt files that match a target story are deleted; GoChina.txt only if all its stories match (then its manifest and
the removed-list go too). Nothing else is touched. Empty sub-folders of txt-only are pruned; the root folder stays.
Run: python3 -I delete_txt_only_dups.py [--go]   (dry run without --go)
"""
import csv, os, re, sys, hashlib
from pathlib import Path
D = Path.home() / 'Downloads'; R = D / 'txt-only'; go = '--go' in sys.argv
norm = lambda s: re.sub(r'\s+', '', s).lower()
md5 = lambda s: hashlib.md5(s.encode()).hexdigest()
def stories(txt, man):
    L = txt.read_text(encoding='utf-8-sig').split('\n'); out = []
    with open(man, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            out.append(norm('\n'.join(L[int(row['start_line']) - 1:int(row['end_line'])])))
    return out
T = set()
g = D / 'data.done/gochina_2026.11.19'
T |= {md5(s) for s in stories(g / 'txt_merged.txt', g / 'txt_merged.manifest.csv')}
for p in (D / 'data.done/mc_2026.11.19/txt').rglob('*.txt'):
    m = p.parent / (p.stem + '.manifest.csv')
    if m.exists(): T |= {md5(s) for s in stories(p, m)}
print('target stories', len(T))
dele = []; keep = []
for p in sorted(R.rglob('*.txt')):
    if p == R / 'GoChina.txt': continue
    (dele if md5(norm(p.read_text(encoding='utf-8-sig'))) in T else keep).append(p)
gc = R / 'GoChina.txt'; gm = R / 'GoChina.manifest.csv'
if gc.exists():
    ok = all(md5(s) in T for s in stories(gc, gm))
    (dele if ok else keep).append(gc)
    if ok:
        for e in (gm, R / 'GoChina.removed.tsv'):
            if e.exists(): dele.append(e)
print('delete', len(dele), 'keep', len(keep))
if go:
    for p in dele: p.unlink()
    n = 0
    for d, _, _ in sorted(os.walk(R), key=lambda x: -len(x[0])):
        q = Path(d)
        if q != R and not [x for x in q.iterdir() if x.name != '.DS_Store']:
            (q / '.DS_Store').unlink(missing_ok=True); q.rmdir(); n += 1
    print('deleted', len(dele), 'empty dirs removed', n)
