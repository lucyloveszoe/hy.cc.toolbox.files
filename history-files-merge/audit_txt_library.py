#!/usr/bin/env python3
"""Audit a txt library: folders of <name>.txt + <name>.manifest.csv (PROCESSING_RULES.md sections 19 and 35).

Standard library only; run inside the project venv:

    source venv/bin/activate
    python audit_txt_library.py <library-dir> [<library-dir> ...]      # e.g. .../txt/locations .../txt/series
    python audit_txt_library.py <txt-dir> --fix-crlf [--go]              # only fix: manifests CRLF -> LF

Read-only unless --fix-crlf --go is given. Exit code 1 when a structural problem is found.

Checks per pair: both files exist; txt UTF-8, LF, no BOM, ends with exactly one newline; manifest with BOM, LF and
the expected header (locations: no,file,start_line,end_line,chars; series: part,title,source_file,
source_start_line,source_end_line,start_line,end_line,chars); numbering 1..N; first story at line 1; end >= start;
stories exactly one blank line apart; last story ends on the last line; chars == len('\\n'.join(lines[start-1:end]));
no story starts or ends on a blank line; every non-empty line covered.
Informational: noise (U+FFFD, NBSP, &#NNN;, INCLUDEPICTURE, HYPERLINK, spam phrases, control and private-use
characters), duplicate stories (md5 of the whitespace-free, lower-cased text), titles that differ from the first line.
Strings are compared lower-cased without whitespace.
"""
import argparse
import collections
import csv
import glob
import hashlib
import os
import re
import sys

LOC = ['no', 'file', 'start_line', 'end_line', 'chars']
SER = ['part', 'title', 'source_file', 'source_start_line', 'source_end_line', 'start_line', 'end_line', 'chars']
NOISE = {
    'U+FFFD': '�', 'NBSP': '\xa0', '&#NNN;': r'&#\d+;', 'INCLUDEPICTURE': 'INCLUDEPICTURE',
    'HYPERLINK': 'HYPERLINK', '本帖来源': '本帖来源', '买春堂版权所有': '买春堂版权所有', '招财进宝': '招财进宝',
    '关闭注册': '关闭注册', 'control char': '[\x00-\x08\x0b\x0c\x0e-\x1f  ]',
    'private-use char': '[-]',
}


def squash(s):
    return re.sub(r'\s+', '', s).lower()


def audit_dir(folder, totals, hashes, problems):
    pairs = sorted(glob.glob(os.path.join(folder, '*.txt')))
    stories = 0
    for t in pairs:
        name = os.path.basename(t)
        m = t[:-4] + '.manifest.csv'
        if not os.path.exists(m):
            problems.append((name, 'no manifest'))
            continue
        iss = []
        with open(t, 'rb') as fh:
            raw = fh.read()
        with open(m, 'rb') as fh:
            mraw = fh.read()
        try:
            txt = raw.decode('utf-8')
        except UnicodeDecodeError:
            problems.append((name, 'not utf-8'))
            continue
        if raw[:3] == b'\xef\xbb\xbf':
            iss.append('txt BOM')
        if b'\r' in raw:
            iss.append('txt CR')
        if not txt.endswith('\n') or txt.endswith('\n\n'):
            iss.append('txt must end with exactly one newline')
        if mraw[:3] != b'\xef\xbb\xbf':
            iss.append('manifest without BOM')
        if b'\r' in mraw:
            iss.append('manifest CRLF')
        with open(m, encoding='utf-8-sig', newline='') as fh:
            rows = list(csv.reader(fh))
        hd, body = rows[0], rows[1:]
        if hd not in (LOC, SER):
            iss.append('header ' + ','.join(hd))
        ser = hd == SER
        lines = txt.split('\n')[:-1] if txt.endswith('\n') else txt.split('\n')
        covered, prev = set(), None
        for i, r in enumerate(body, 1):
            if len(r) != len(hd):
                iss.append(f'ragged row {i}')
                continue
            a, b, c = (int(r[5]), int(r[6]), int(r[7])) if ser else (int(r[2]), int(r[3]), int(r[4]))
            if int(r[0]) != i:
                iss.append(f'numbering at {i}')
            if b < a:
                iss.append(f'end < start at {i}')
            if i == 1 and a != 1:
                iss.append('first story not at line 1')
            if prev is not None and a != prev + 2:
                iss.append(f'stories not one blank line apart before {i}')
            seg = lines[a - 1:b]
            if len('\n'.join(seg)) != c:
                iss.append(f'chars at {i}')
            if seg and (not seg[0].strip() or not seg[-1].strip()):
                iss.append(f'blank edge at {i}')
            covered |= set(range(a, b + 1))
            prev = b
            hashes[hashlib.md5(squash('\n'.join(seg)).encode()).hexdigest()].append(f'{name}#{i}')
            title = r[1] if ser else r[1][:-4]
            if seg and squash(title.replace('／', '/')) != squash(seg[0]):
                totals['titles differing from the first line'] += 1
        if body and prev != len(lines):
            iss.append('last story not on the last line')
        if [i for i, l in enumerate(lines, 1) if l.strip() and i not in covered]:
            iss.append('uncovered lines')
        for label, pat in NOISE.items():
            n = len(re.findall(pat, txt))
            if n:
                totals['noise: ' + label] += n
        totals['stories'] += len(body)
        stories += len(body)
        if iss:
            problems.append((name, '; '.join(iss)))
    return len(pairs), stories


def fix_crlf(folders, go):
    todo = [m for f in folders for m in sorted(glob.glob(os.path.join(f, '*.manifest.csv')))
            if b'\r' in open(m, 'rb').read()]
    print(f'manifests with CRLF: {len(todo)}')
    if go:
        for m in todo:
            with open(m, 'rb') as fh:
                b = fh.read()
            with open(m, 'wb') as fh:
                fh.write(b.replace(b'\r\n', b'\n').replace(b'\r', b'\n'))
        print('converted to LF (BOM kept)')
    elif todo:
        print('dry run; add --go')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folders', nargs='+')
    ap.add_argument('--fix-crlf', action='store_true')
    ap.add_argument('--go', action='store_true')
    args = ap.parse_args()
    folders = [os.path.abspath(f) for f in args.folders]
    if args.fix_crlf:
        fix_crlf(folders, args.go)
        return
    totals, hashes, problems = collections.Counter(), collections.defaultdict(list), []
    for f in folders:
        pairs, stories = audit_dir(f, totals, hashes, problems)
        print(f'{os.path.basename(f)}: {pairs} txt/manifest pairs, {stories} stories')
    dups = [v for v in hashes.values() if len(v) > 1]
    print(f'stories {totals["stories"]} | duplicate stories {len(dups)}')
    for v in dups[:10]:
        print('  duplicate:', v)
    for k in sorted(k for k in totals if k not in ('stories',)):
        print(f'{k}: {totals[k]}')
    print('structural problems:', len(problems))
    for n, i in problems[:25]:
        print('  ', n, '|', i[:160])
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
