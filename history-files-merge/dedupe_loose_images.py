#!/usr/bin/env python3
"""De-duplicate a folder of loose image sets (PROCESSING_RULES.md section 37).

Standard library only; run inside the project venv:

    source venv/bin/activate
    python dedupe_loose_images.py <root>                              # dry run (default)
    python dedupe_loose_images.py <root> --quarantine DIR --go        # move duplicates to DIR (never deletes)

A *set* is a folder that holds images. Exact duplicates are found by md5 over the image files
(`.jpg .jpeg .png .bmp .gif .tif .tiff`; `.DS_Store` and `Thumbs.db` are ignored).

1. Whole folders fully contained in another folder (sorted by image count, kept sets first) are removed, but only
   when the folder holds nothing but images and cache files (otherwise it is listed as held back).
2. Extra copies of a picture inside one kept folder (same bytes, different names) are removed; the first name in
   sorted order stays.
3. Pictures shared by sets that each also have unique pictures are left alone (reported only).

Every moved file is checked against its kept copy before it is moved. A removed -> kept TSV is written into the
quarantine. Delete the quarantine only after repeating the byte check.
"""
import argparse
import collections
import hashlib
import os
import shutil
import sys
import time

IMG = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff')
CACHE = ('Thumbs.db', '.DS_Store')


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sniff(path):
    with open(path, 'rb') as fh:
        h = fh.read(12)
    return (h[:3] == b'\xff\xd8\xff' or h[:8] == b'\x89PNG\r\n\x1a\n' or h[:4] == b'GIF8' or h[:2] == b'BM'
            or h[:4] in (b'II*\x00', b'MM\x00*'))


def scan(root):
    sets, everything = {}, collections.defaultdict(list)
    for r, _ds, fs in os.walk(root):
        for f in fs:
            everything[r].append(f)
        im = [f for f in fs if f.lower().endswith(IMG)]
        if im:
            sets[r] = {os.path.join(r, f): md5(os.path.join(r, f)) for f in im}
    return sets, everything


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root')
    ap.add_argument('--quarantine')
    ap.add_argument('--go', action='store_true')
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    sets, everything = scan(root)
    fake = [p for d in sets.values() for p in d if not sniff(p)]
    hs = {r: set(d.values()) for r, d in sets.items()}
    order = sorted(sets, key=lambda r: (-len(hs[r]), -len(r), r))
    kept, removable = [], {}
    for r in order:
        host = next((k for k in kept if hs[r] <= hs[k]), None)
        if host:
            removable[r] = host
        else:
            kept.append(r)
    held = []
    for r in list(removable):
        other = [f for f in everything[r] if not f.lower().endswith(IMG) and f not in CACHE]
        sub = [x for x in everything if x.startswith(r + os.sep)]
        if other or sub:
            held.append((r, other or ['has sub-folders']))
            del removable[r]
    n_files = sum(len(sets[r]) for r in removable)
    n_bytes = sum(os.path.getsize(p) for r in removable for p in sets[r])
    print(f'{len(sets)} image folders, {sum(len(d) for d in sets.values())} images, fake headers {len(fake)}')
    print(f'whole folders contained in another folder: {len(removable)} ({n_files} images, {n_bytes / 1e6:.2f} MB), '
          f'held back {len(held)}')
    for r, k in list(removable.items())[:8]:
        print(f'  {os.path.relpath(r, root)[:50]} ({len(sets[r])}) is contained in {os.path.relpath(k, root)[:50]} ({len(sets[k])})')
    for r, o in held:
        print('  HELD', os.path.relpath(r, root), o[:3])
    within = []
    for r in kept:
        if r in removable:
            continue
        seen = {}
        for p, h in sorted(sets[r].items()):
            if h in seen:
                within.append((p, seen[h]))
            else:
                seen[h] = p
    print(f'extra copies of a picture inside one kept folder: {len(within)} '
          f'({sum(os.path.getsize(p) for p, _ in within) / 1e6:.2f} MB)')
    groups = collections.defaultdict(list)
    for r, d in sets.items():
        if r in removable:
            continue
        for p, h in d.items():
            groups[h].append(p)
    shared = [v for v in groups.values() if len({os.path.dirname(x) for x in v}) > 1]
    print(f'pictures shared by several kept folders (left alone): {len(shared)} groups')
    if not args.go:
        print('dry run; add --go (and --quarantine DIR) to move the duplicates')
        return 0
    quarantine = os.path.abspath(args.quarantine or os.path.join(os.path.dirname(root), '_quarantine_images_' + time.strftime('%Y%m%d_%H%M%S')))
    os.makedirs(quarantine, exist_ok=False)
    log = []
    for r, k in removable.items():
        kb = {h: p for p, h in sets[k].items()}
        for p, h in sets[r].items():
            assert h in kb and md5(kb[h]) == h
            log.append(f'{os.path.relpath(p, root)}\t->same as\t{os.path.relpath(kb[h], root)}')
        dst = os.path.join(quarantine, os.path.relpath(r, root))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(r, dst)
    for p, keep in within:
        assert md5(p) == md5(keep)
        dst = os.path.join(quarantine, os.path.relpath(p, root))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(p, dst)
        log.append(f'{os.path.relpath(p, root)}\t->same as\t{os.path.relpath(keep, root)}')
    with open(os.path.join(quarantine, 'removed_to_kept.tsv'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(log))
    print(f'moved {len(log)} images to {quarantine}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
