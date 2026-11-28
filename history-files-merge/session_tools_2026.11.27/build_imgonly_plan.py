"""READ-ONLY: classify every file in <root>/images.only of new layout-A roots -> plan.json for imgonly_into_flat.py.

    python3 -I build_imgonly_plan.py <plan.json> <library dir> [<library dir> ...] -- <new root> [<new root> ...]

kind per file (PROCESSING_LOGIC 4.1, 4.3, 5.2, 6.1.10):
  fake          header is not jpg/png/gif/bmp (HTML error page, 0 bytes)
  ui            <= 150 px on the long side or < 8 KB (smilies, icons, avatars, buttons)
  in-library    same SHA-256 as a file under a library dir      ('existing' = that path)
  in-new-report same SHA-256 as an image a new report links      ('existing' = that path, <root>/images/...)
  dup-in-batch  same SHA-256 as an earlier images.only file of this batch
  new           anything else
Library files are hashed only when their size equals the size of a candidate (fast)."""
import hashlib
import json
import os
import subprocess
import sys

IMG = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def sniff(p):
    b = open(p, 'rb').read(8)
    if b.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if b.startswith(b'\x89PNG'):
        return 'png'
    if b.startswith(b'GIF8'):
        return 'gif'
    if b.startswith(b'BM'):
        return 'bmp'
    return ''


def dims(p):
    out = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', p], capture_output=True, text=True).stdout
    w = h = 0
    for line in out.splitlines():
        if 'pixelWidth' in line:
            w = int(line.split()[-1])
        if 'pixelHeight' in line:
            h = int(line.split()[-1])
    return w, h


def main():
    out = sys.argv[1]
    i = sys.argv.index('--')
    libs, roots = sys.argv[2:i], [os.path.abspath(r) for r in sys.argv[i + 1:]]
    cands = []
    for R in roots:
        for d, _, fs in os.walk(os.path.join(R, 'images.only')):
            for f in sorted(fs):
                if f == '.DS_Store' or f.lower() == 'thumbs.db':
                    continue
                cands.append(os.path.join(d, f))
    sizes = {os.path.getsize(p) for p in cands}
    lib_by_sha = {}
    for L in libs:
        for d, _, fs in os.walk(L):
            for f in fs:
                if not f.lower().endswith(IMG):
                    continue
                p = os.path.join(d, f)
                try:
                    if os.path.getsize(p) in sizes:
                        lib_by_sha.setdefault(sha(p), p)
                except OSError:
                    pass
    rep_by_sha = {}
    for R in roots:
        for d, _, fs in os.walk(os.path.join(R, 'images')):
            for f in fs:
                p = os.path.join(d, f)
                if os.path.getsize(p) in sizes:
                    rep_by_sha.setdefault(sha(p), p)
    plan, seen, stats = [], set(), {}
    for p in cands:
        s, n = sha(p), os.path.getsize(p)
        root = next(R for R in roots if p.startswith(R + os.sep))
        w, h = dims(p) if sniff(p) else (0, 0)
        x = {'path': p, 'root': root, 'sha': s, 'bytes': n, 'w': w, 'h': h}
        if not sniff(p) or n == 0:
            x['kind'] = 'fake'
        elif max(w, h) <= 150 or n < 8 * 1024:
            x['kind'] = 'ui'
        elif s in lib_by_sha:
            x['kind'], x['existing'] = 'in-library', lib_by_sha[s]
        elif s in rep_by_sha:
            x['kind'], x['existing'] = 'in-new-report', rep_by_sha[s]
        elif s in seen:
            x['kind'] = 'dup-in-batch'
        else:
            x['kind'] = 'new'
        seen.add(s)
        stats[x['kind']] = stats.get(x['kind'], 0) + 1
        plan.append(x)
    json.dump(plan, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('files', len(plan), stats, '| library images hashed (size match)', len(lib_by_sha))


if __name__ == '__main__':
    main()
