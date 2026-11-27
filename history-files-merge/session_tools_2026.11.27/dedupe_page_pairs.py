"""Remove the duplicate page of each decided pair (remove -> keep), with its now-unused images, and repoint CSVs.

    python3 dedupe_page_pairs.py plan.tsv                                  dry run
    python3 dedupe_page_pairs.py plan.tsv --go --quarantine Q             act; Q must not exist yet

plan.tsv: header 'remove<TAB>keep', absolute page paths. --refs-root R (default DD): the tree whose CSVs are
  repointed and that the quarantine mirrors; the kept page may live outside it (e.g. a new set vs the library).
--img-map M: optional TSV 'removed_image<TAB>kept_image' (absolute) for user-approved near copies (img_near.py
  match, different bytes): such an unused image is quarantined and its CSV rows point to the kept version.

Per pair
  * images linked by the removed page and by no other page in its folder become unused:
      byte-identical (SHA-256) to an image the kept page links -> quarantined, mapped to that image;
      no identical copy -> quarantined, mapped to nothing (listed; the dry run shows them so they can be checked).
  * the page and its unused images move to Q (same relative paths under DD) + Q/removed_to_kept.tsv.
  * every CSV under DD: a cell resolving to a removed page -> relpath to the kept page, and that row's
    images_copied (if present) = distinct images of the kept page; a cell resolving to a removed image ->
    the kept image, or '' with ' [output file no longer in data.done]' appended to 'status' (if present).
    Original CSVs are copied to Q/csv_backup first. BOM/EOL/column order kept; non-round-tripping CSV -> stop.
  * checks: kept pages exist and every local <img src> resolves; 0 CSV cells resolve into Q's paths.
"""
import argparse
import csv
import hashlib
import html
import io
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hfm_config import DD  # noqa: E402

SRC = re.compile(r'<img[^>]*?\ssrc\s*=\s*"([^"]+)"', re.I)


def nfc(s):
    return unicodedata.normalize('NFC', s)


def links(page):
    t = open(page, encoding='utf-8', errors='replace').read()
    out = []
    for s in SRC.findall(t):
        v = html.unescape(s)
        if re.match(r'^(?:[a-z][a-z0-9+.-]*:|//)', v, re.I):
            continue
        out.append(nfc(os.path.normpath(os.path.join(os.path.dirname(page), v))))
    return out


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def load_csv(p):
    data = open(p, 'rb').read()
    bom = data.startswith(b'\xef\xbb\xbf')
    text = data.decode('utf-8-sig')
    eol = '\r\n' if '\r\n' in text else '\n'
    rows = list(csv.reader(io.StringIO(text, newline='')))

    def dump(rs):
        buf = io.StringIO()
        csv.writer(buf, lineterminator=eol).writerows(rs)
        return (b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8')
    if dump(rows) != data:
        return None, None
    return rows, dump


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plan')
    ap.add_argument('--go', action='store_true')
    ap.add_argument('--quarantine')
    ap.add_argument('--img-map')
    ap.add_argument('--refs-root', default=DD)
    a = ap.parse_args()
    if a.go and (not a.quarantine or os.path.exists(a.quarantine)):
        sys.exit('--go needs --quarantine that does not exist yet')
    R = os.path.abspath(a.refs_root)
    pairs = [l.split('\t') for l in open(a.plan, encoding='utf-8').read().splitlines()[1:] if l.strip()]
    pairs = [(nfc(r), nfc(k)) for r, k in pairs]

    page_map, img_map, no_copy = {}, {}, []
    extra = {}
    if a.img_map:
        for l in open(a.img_map, encoding='utf-8').read().splitlines()[1:]:
            if l.strip():
                x, y = l.split('\t')
                extra[nfc(x)] = nfc(y)
                if not os.path.isfile(y):
                    sys.exit(f'img-map target missing: {y}')
    for r, k in pairs:
        for p in (r, k):
            if not os.path.isfile(p):
                sys.exit(f'missing: {p}')
        d = os.path.dirname(r)
        others = set()
        for f in os.listdir(d):
            p = nfc(os.path.join(d, f))
            if f.lower().endswith(('.html', '.htm')) and p != r:
                others.update(links(p))
        kept_by_sha = {}
        for q in links(k):
            if os.path.isfile(q):
                kept_by_sha.setdefault(sha(q), q)
        page_map[r] = k
        before = len(img_map)
        for q in dict.fromkeys(links(r)):
            if q in others or not os.path.isfile(q):
                continue
            kq = kept_by_sha.get(sha(q)) or extra.get(q)
            img_map[q] = kq
            if kq is None:
                no_copy.append(q)
        print(f'remove {os.path.relpath(r, R)}\n   keep {os.path.basename(k)}; unused images: '
              f'{len(img_map) - before}')
    print(f'pages to quarantine {len(page_map)}; images to quarantine {len(img_map)} '
          f'(identical copy or approved near copy in kept page {len(img_map) - len(no_copy)}, no copy {len(no_copy)})')
    for q in no_copy:
        print(f'   no identical copy: {os.path.relpath(q, R)} ({os.path.getsize(q)} bytes)')

    gone = {**{p: v for p, v in page_map.items()}, **img_map}
    edits = []
    for d, _, fs in os.walk(R):
        for f in fs:
            if not f.lower().endswith('.csv'):
                continue
            p = os.path.join(d, f)
            raw = open(p, 'rb').read()
            if not any(os.path.basename(g).encode() in raw for g in gone):
                continue
            rows, dump = load_csv(p)
            if rows is None:
                sys.exit(f'csv does not round-trip, stopped: {p}')
            h = rows[0]
            ic = h.index('images_copied') if 'images_copied' in h else None
            st = h.index('status') if 'status' in h else None
            n = 0
            for row in rows[1:]:
                for i, cell in enumerate(row):
                    v = cell.strip()
                    if not v or ('/' not in v and not v.lower().endswith(('.html', '.htm'))):
                        continue
                    t = nfc(os.path.normpath(os.path.join(d, v)))
                    if t in page_map:
                        k = page_map[t]
                        row[i] = os.path.relpath(k, d)
                        if ic is not None and ic != i:
                            row[ic] = str(len(set(links(k))))
                        n += 1
                    elif t in img_map:
                        k = img_map[t]
                        if k:
                            row[i] = os.path.relpath(k, d)
                        else:
                            row[i] = ''
                            if st is not None and st != i:
                                row[st] = row[st] + ' [output file no longer in data.done]'
                        n += 1
            if n:
                edits.append((p, dump(rows), n))
    for p, _, n in edits:
        print(f'   csv {n:4d} cells  {os.path.relpath(p, R)}')
    if not a.go:
        print('dry run; add --go --quarantine <new dir>')
        return

    os.makedirs(a.quarantine)
    for p, _, _ in edits:
        dst = os.path.join(a.quarantine, 'csv_backup', os.path.relpath(p, R))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
    with open(os.path.join(a.quarantine, 'removed_to_kept.tsv'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('removed\tkept\n')
        for g, k in gone.items():
            fh.write(f'{os.path.relpath(g, R)}\t{os.path.relpath(k, R) if k else ""}\n')
    for g in gone:
        dst = os.path.join(a.quarantine, os.path.relpath(g, R))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(g, dst)
    for p, data, _ in edits:
        with open(p, 'wb') as fh:
            fh.write(data)

    broken = sum(1 for k in set(page_map.values()) for q in links(k) if not os.path.isfile(q))
    stale = 0
    for d, _, fs in os.walk(R):
        for f in fs:
            if f.lower().endswith('.csv'):
                p = os.path.join(d, f)
                for row in csv.reader(open(p, encoding='utf-8-sig', newline='')):
                    for cell in row:
                        if cell.strip() and nfc(os.path.normpath(os.path.join(d, cell.strip()))) in gone:
                            stale += 1
    still = sum(1 for g in gone if os.path.exists(g))
    print(f'quarantined {len(gone)}; still in place {still}; broken img links in kept pages {broken}; '
          f'csv cells pointing into quarantine {stale}; quarantine {a.quarantine}')


if __name__ == '__main__':
    main()
