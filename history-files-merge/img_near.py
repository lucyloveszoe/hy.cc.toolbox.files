#!/usr/bin/env python3
"""Find resized / re-saved / recompressed copies of the same picture (READ-ONLY; never deletes or moves anything).

Byte-identical copies are handled elsewhere (SHA-256, img_merge.py). This tool covers what SHA-256 cannot: the same
photo saved at another size, JPEG quality, or format. No PIL needed: macOS `sips` makes a 16x16 thumbnail, the BMP
is parsed with the standard library.

Method
  1. Walk the roots, header-sniff (jpg/png/gif/bmp), read pixel size from the header, SHA-256 (distinct files only).
  2. 16x16 grey thumbnail via `sips` pyramid 128>32>16 (parallel, cached in --cache so a re-run only handles new files).
  3. dHash (240 bits: left pixel > right pixel). Candidate pairs = images that share one of 12 exact 20-bit bands
     (LSH, so no O(n^2) scan). Very flat images (blank/black/white) and over-full buckets are skipped and counted.
  4. A pair is accepted only if ALL hold: aspect ratio within 8 %, Hamming distance <= --max-dist (default 18 of 240),
     the mean absolute difference of the two mean-centred thumbnails <= --mad (default 4.00 of 255), and the worst 4x4
     block of that difference <= --block (default 6.80). Frames of one video (same room, moved subject) pass the
     global test but fail the block test. Calibrated on real library pictures: true re-saves/resizes max mad 2.08,
     max block 6.55, max Hamming 17; different
     frames of one video measured block 7.0-7.7 / Hamming 21-23 or worse. Consecutive frames seconds apart are the limit of a
     16x16 fingerprint: treat `review` rows as suggestions and look at them; only `high` is near-certain.
  5. Pairs are linked into components, then groups are cut greedily: keeper = most pixels, then most bytes, then
     shortest path; a candidate must match the KEEPER directly (no A~B~C chains).

Output (TSV, one row per file of a group; every number rounded to 2 decimals):
  group, role (keep|candidate), path, width, height, bytes, area_vs_keeper, mad_vs_keeper, hamming_vs_keeper, blockmax_vs_keeper,
  relation (keeper | same-size-resave | resized), confidence (high: mad<=2, hamming<=8, block<=3; else review),
  same_bytes_as (other paths with identical SHA-256, ' | ' joined)
Candidates are only SUGGESTIONS. Before deleting any candidate check: it is not linked by a report that the keeper
is not part of, view one pair of each relation by eye, and use quarantine + removed_to_kept.tsv as in PROCESSING_LOGIC.

Usage:  python3 img_near.py <root> [<root> ...] [--out near_images.tsv] [--cache near_cache.json]
                            [--max-dist 18] [--mad 4] [--block 6.8] [--min-side 64] [--workers 8]
"""
import argparse
import collections
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
SKIP = {'.DS_Store', 'Thumbs.db'}
T = 16                      # thumbnail side
PYRAMID = (128, 32, 16)     # sips resize steps; the last one is T
CACHE_VERSION = 2           # bump when the thumbnail method changes
BANDS, BAND_BITS = 12, 20   # 240 bits = 12 x 20


def r2(x):
    return round(float(x), 2)


def sniff(b):
    if b[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if b[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if b[:3] == b'GIF':
        return 'gif'
    if b[:2] == b'BM':
        return 'bmp'
    return None


def dims(b, kind):
    """(width, height) from the header, or None."""
    try:
        if kind == 'png':
            return struct.unpack('>II', b[16:24])
        if kind == 'gif':
            return struct.unpack('<HH', b[6:10])
        if kind == 'bmp':
            w, h = struct.unpack('<ii', b[18:26])
            return w, abs(h)
        if kind == 'jpg':
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                n = struct.unpack('>H', b[i + 2:i + 4])[0]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack('>HH', b[i + 5:i + 9])
                    return w, h
                i += 2 + n
    except (struct.error, IndexError):
        pass
    return None


def thumb(path):
    """16x16 grey values (list of 256 ints) via sips, or None.
    Pyramid 128 -> 32 -> 16: a single big jump (e.g. 1065x1891 -> 16x16) aliases, so the same photo at half size got a
    different hash (Hamming 57); the pyramid brought it to 2-17 (tested on real library pictures)."""
    with tempfile.TemporaryDirectory() as td:
        cur = path
        for k, side in enumerate(PYRAMID):
            last = k == len(PYRAMID) - 1
            out = os.path.join(td, 's%d.%s' % (k, 'bmp' if last else 'png'))
            r = subprocess.run(['sips', '-z', str(side), str(side), '-s', 'format', 'bmp' if last else 'png',
                                cur, '--out', out], capture_output=True)
            if r.returncode != 0 or not os.path.exists(out):
                return None
            cur = out
        d = open(cur, 'rb').read()
    try:
        off = struct.unpack('<I', d[10:14])[0]
        w, h = struct.unpack('<ii', d[18:26])
        bpp = struct.unpack('<H', d[28:30])[0]
        if w != T or abs(h) != T or bpp not in (24, 32):
            return None
        bp = bpp // 8
        stride = (w * bp + 3) // 4 * 4
        rows = []
        for y in range(T):
            ry = (T - 1 - y) if h > 0 else y          # bottom-up unless height < 0
            row = d[off + ry * stride: off + ry * stride + w * bp]
            rows.append([int(0.114 * row[x * bp] + 0.587 * row[x * bp + 1] + 0.299 * row[x * bp + 2] + 0.5)
                         for x in range(w)])
        return [v for r_ in rows for v in r_]
    except (struct.error, IndexError):
        return None


def dhash(g):
    bits = 0
    for y in range(T):
        for x in range(T - 1):
            bits = (bits << 1) | (1 if g[y * T + x] > g[y * T + x + 1] else 0)
    return bits


def mad(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    return sum(abs((x - ma) - (y - mb)) for x, y in zip(a, b)) / len(a)


def blockmax(a, b):
    """Worst 4x4-pixel block (of the 16x16 thumbnail) of the mean-centred absolute difference. A re-save changes every
    block a little; a different frame of one scene (moved subject, same room) changes a few blocks a lot."""
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    best = 0.0
    for by in range(0, T, 4):
        for bx in range(0, T, 4):
            d = sum(abs((a[y * T + x] - ma) - (b[y * T + x] - mb)) for y in range(by, by + 4) for x in range(bx, bx + 4))
            best = max(best, d / 16)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('roots', nargs='+')
    ap.add_argument('--out', default='near_images.tsv')
    ap.add_argument('--cache', default='near_cache.json')
    ap.add_argument('--max-dist', type=int, default=18)
    ap.add_argument('--mad', type=float, default=4.0)
    ap.add_argument('--block', type=float, default=6.8)
    ap.add_argument('--min-side', type=int, default=64, help='ignore pictures whose longer side is smaller (icons)')
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args()

    # 1. walk, sniff, sha256 (distinct content only)
    by_sha = collections.OrderedDict()   # sha -> dict(paths, w, h, bytes, kind)
    fake = 0
    total = 0
    for root in a.roots:
        for dp, dn, fn in os.walk(root):
            dn.sort()
            for f in sorted(fn):
                if f in SKIP or os.path.splitext(f)[1].lower() not in EXT:
                    continue
                p = os.path.join(dp, f)
                try:
                    b = open(p, 'rb').read()
                except OSError:
                    continue
                total += 1
                k = sniff(b)
                if not k:
                    fake += 1
                    continue
                s = hashlib.sha256(b).hexdigest()
                if s in by_sha:
                    by_sha[s]['paths'].append(p)
                    continue
                wh = dims(b, k)
                by_sha[s] = {'paths': [p], 'wh': wh, 'bytes': len(b), 'kind': k}
    print('files', total, '| distinct content', len(by_sha), '| fake (not pictures)', fake)

    items = [(s, v) for s, v in by_sha.items() if v['wh'] and max(v['wh']) >= a.min_side]
    small = len(by_sha) - len(items)

    # 2. thumbnails (cached by sha256 -> thumb)
    cache = {}
    if os.path.exists(a.cache):
        cache = json.load(open(a.cache))
        if cache.get('_v') != CACHE_VERSION:
            cache = {}
    todo = [(s, v) for s, v in items if s not in cache]  # '_v' is never a sha
    if todo:
        print('thumbnails to make', len(todo), '(cached', len(items) - len(todo), ')')
        with ThreadPoolExecutor(a.workers) as ex:
            for (s, v), g in zip(todo, ex.map(lambda sv: thumb(sv[1]['paths'][0]), todo)):
                cache[s] = g
        cache['_v'] = CACHE_VERSION
        json.dump(cache, open(a.cache, 'w'))
    live, flat, nothumb = [], 0, 0
    for s, v in items:
        g = cache.get(s)
        if not g:
            nothumb += 1
            continue
        mean = sum(g) / len(g)
        if (sum((x - mean) ** 2 for x in g) / len(g)) ** 0.5 < 4.0:     # flat: blank / solid colour
            flat += 1
            continue
        live.append((s, v, g, dhash(g)))
    print('compared', len(live), '| skipped: smaller than min-side', small, ', flat', flat, ', no thumbnail', nothumb)

    # 3. LSH candidates
    mask = (1 << BAND_BITS) - 1
    buckets = collections.defaultdict(list)
    for i, (_, _, _, h) in enumerate(live):
        for b in range(BANDS):
            buckets[(b, (h >> (b * BAND_BITS)) & mask)].append(i)
    pairs, big = set(), 0
    for ids in buckets.values():
        if len(ids) < 2:
            continue
        if len(ids) > 300:
            big += 1
            continue
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                pairs.add((ids[x], ids[y]))
    print('candidate pairs', len(pairs), '| over-full buckets skipped', big)

    # 4. verify. match(i, j) is the ONLY acceptance test and is also applied keeper-vs-candidate (no chains: A~B and
    #    B~C does not put A and C in one group, because similar frames of one video chain easily).
    def match(i, j):
        (si, vi, gi, hi), (sj, vj, gj, hj) = live[i], live[j]
        if abs((vi['wh'][0] / vi['wh'][1]) / (vj['wh'][0] / vj['wh'][1]) - 1) > 0.08:
            return None
        ham = bin(hi ^ hj).count('1')
        if ham > a.max_dist:
            return None
        m = mad(gi, gj)
        if m > a.mad:
            return None
        bm = blockmax(gi, gj)
        if bm > a.block:
            return None
        return ham, m, bm

    par = list(range(len(live)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for i, j in pairs:
        if match(i, j):
            par[find(i)] = find(j)
    comps = collections.defaultdict(list)
    for i in range(len(live)):
        comps[find(i)].append(i)

    def key(i):
        v = live[i][1]
        return (-(v['wh'][0] * v['wh'][1]), -v['bytes'], len(v['paths'][0]), v['paths'][0])
    groups = []                                  # groups = [(keeper, [(candidate, ham, mad, blockmax)])]
    for comp in comps.values():
        rest = sorted(comp, key=key)
        if len(rest) < 2:
            continue
        while len(rest) > 1:
            k = rest[0]
            cand = [(i, *r) for i in rest[1:] for r in [match(k, i)] if r]
            if cand:
                groups.append((k, cand))
            used = {k} | {c[0] for c in cand}
            rest = [i for i in rest if i not in used]
    groups.sort(key=lambda g: key(g[0]))

    # 5. write
    nrows = ncand = 0
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write('\t'.join(['group', 'role', 'path', 'width', 'height', 'bytes', 'area_vs_keeper', 'mad_vs_keeper',
                             'hamming_vs_keeper', 'blockmax_vs_keeper', 'relation', 'confidence', 'same_bytes_as']) + '\n')
        for n, (k, cand) in enumerate(groups, 1):
            kv = live[k][1]
            kw, kh = kv['wh']
            fh.write('\t'.join(str(x) for x in [n, 'keep', kv['paths'][0], kw, kh, kv['bytes'], r2(1), '', '', '',
                                                'keeper', '', ' | '.join(kv['paths'][1:])]) + '\n')
            nrows += 1
            for i, ham, m, bm in cand:
                v = live[i][1]
                w, h = v['wh']
                rel = 'same-size-resave' if (w, h) == (kw, kh) else 'resized'
                conf = 'high' if (m <= 2 and ham <= 8 and bm <= 3) else 'review'
                fh.write('\t'.join(str(x) for x in [n, 'candidate', v['paths'][0], w, h, v['bytes'], r2(w * h / (kw * kh)),
                                                    r2(m), ham, r2(bm), rel, conf, ' | '.join(v['paths'][1:])]) + '\n')
                nrows += 1
                ncand += 1
    hi = sum(1 for _, c in groups for x in c if x[1] <= 8 and x[2] <= 2 and x[3] <= 3)
    print('confidence high', hi, '| review', ncand - hi)
    print('groups', len(groups), '| candidates', ncand, '| rows', nrows, '| written', a.out)
    print('READ-ONLY: nothing was deleted or moved.')


if __name__ == '__main__':
    sys.exit(main())
