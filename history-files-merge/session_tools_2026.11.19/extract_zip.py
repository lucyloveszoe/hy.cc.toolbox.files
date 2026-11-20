"""Extract one zip into its own new empty dir. Usage: extract_zip.py <zip> <dest>"""
import sys, zipfile, os, unicodedata
from pathlib import Path

def fixname(info):
    n = info.filename
    if not (info.flag_bits & 0x800):
        raw = n.encode('cp437', errors='strict') if all(ord(c) < 256 for c in n) else None
        if raw is not None:
            for enc in ('gbk', 'big5hkscs'):
                try:
                    n = raw.decode(enc); break
                except Exception:
                    pass
    return n.replace('\\', '/')

def main(z, dest):
    dest = Path(dest).resolve()
    if dest.exists() and any(dest.iterdir()):
        sys.exit(f'dest not empty: {dest}')
    dest.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(z)
    nfile = skipped = 0
    for info in zf.infolist():
        n = fixname(info)
        if n.endswith('/'):
            (dest / n).mkdir(parents=True, exist_ok=True); continue
        target = (dest / n).resolve()
        if not str(target).startswith(str(dest) + os.sep):
            skipped += 1; print('SKIP traversal', n); continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, 'wb') as out:
            while True:
                b = src.read(1 << 20)
                if not b: break
                out.write(b)
        nfile += 1
    print(f'{os.path.basename(z)}: {nfile} files, {skipped} skipped')

main(sys.argv[1], sys.argv[2])
