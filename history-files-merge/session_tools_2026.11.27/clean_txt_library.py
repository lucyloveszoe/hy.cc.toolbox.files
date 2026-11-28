"""Clean merged txt files story by story and rebuild their manifests (PROCESSING_LOGIC 4.4, 6.2-4/7); dry run by default.

    python3 -I clean_txt_library.py <txt> [<txt> ...] [--go --backup-dir D]

<txt>.manifest.csv (sibling: name.txt -> name.manifest.csv) gives the story ranges (no, title|file, start_line,
end_line, chars). Without a manifest one is built (columns no, title, start_line, end_line, chars) with the boundary
rule of 5.3-4: a story starts at a non-blank line after a blank line (or the file start) that is directly followed by a
'作者' line; the build stops if any non-blank line falls outside a story.
Per story: garbage runs, edit stamps, zero-width / private-use / U+FFFD (clean_text_docs.spans) removed; lines that are
only '[image missing]' dropped, inline markers removed; trailing spaces stripped; 3+ blank lines -> 1; edges trimmed.
The file is rewritten (UTF-8, LF, one blank line between stories, one final newline) and the manifest recomputed
(identity column kept). Checks: same story count; per story the CJK characters equal the original's minus those of the
removed spans; an empty story stops the run."""
import csv
import io
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_text_docs import spans, cut  # noqa: E402

MISS_LINE = re.compile(r'^\s*(?:\[image missing\]\s*)+$')
MISS = re.compile(r'\s*\[image missing\]')
cjk = lambda s: sorted(re.findall(r'[㐀-鿿]', s))


def load_csv(p):
    data = open(p, 'rb').read()
    bom = data.startswith(b'\xef\xbb\xbf')
    text = data.decode('utf-8-sig')
    eol = '\r\n' if '\r\n' in text else '\n'
    return list(csv.reader(io.StringIO(text, newline=''))), bom, eol


def ranges_from_manifest(rows):
    h = rows[0]
    si, ei = h.index('start_line'), h.index('end_line')
    return h, [(int(r[si]), int(r[ei]), r) for r in rows[1:]]


def ranges_built(L):
    starts = [i for i in range(len(L) - 1) if L[i].strip() and L[i + 1].startswith('作者') and (i == 0 or not L[i - 1].strip())]
    out = []
    for k, s in enumerate(starts):
        e = (starts[k + 1] - 2) if k + 1 < len(starts) else len(L) - 1
        while e > s and not L[e].strip():
            e -= 1
        out.append((s + 1, e + 1, None))
    inside = set()
    for s, e, _ in out:
        inside.update(range(s, e + 1))
    outside = [i + 1 for i, l in enumerate(L) if l.strip() and i + 1 not in inside]
    return out, outside


def clean_story(t):
    sp = spans(t)
    t2 = cut(t, sp)
    lines = [MISS.sub('', l).rstrip() if not MISS_LINE.match(l) else None for l in t2.split('\n')]
    t3 = '\n'.join(l for l in lines if l is not None)
    t3 = re.sub(r'\n{3,}', '\n\n', t3).strip('\n')
    removed_cjk = cjk(''.join(t[a:b] for a, b in sp))
    return t3, len(sp), sum(1 for l in lines if l is None), removed_cjk


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    go = '--go' in sys.argv
    B = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
    if B in args:
        args.remove(B)
    if go:
        assert B and not os.path.exists(B)
        os.makedirs(B)
    for p in args:
        m = p[:-4] + '.manifest.csv'
        L = open(p, encoding='utf-8').read().split('\n')
        if os.path.exists(m):
            mrows, bom, eol = load_csv(m)
            h, rng = ranges_from_manifest(mrows)
            built = False
        else:
            rng, outside = ranges_built(L)
            if outside:
                print(f'{p}: cannot build manifest, {len(outside)} non-blank lines outside stories; skipped')
                continue
            h, bom, eol, built = ['no', 'title', 'start_line', 'end_line', 'chars'], True, '\n', True
        stories, nsp, nmiss, bad = [], 0, 0, []
        for s, e, r in rng:
            orig = '\n'.join(L[s - 1:e])
            new, a, b, rc = clean_story(orig)
            nsp += a
            nmiss += b
            exp = cjk(orig)
            for ch in rc:
                exp.remove(ch)
            if not new.strip() or cjk(new) != exp:
                bad.append((s, e))
            stories.append((new, r))
        out_lines, rows = [], [h]
        for k, (t, r) in enumerate(stories, 1):
            start = len(out_lines) + 1 + (1 if out_lines else 0)
            if out_lines:
                out_lines.append('')
            out_lines += t.split('\n')
            end = len(out_lines)
            if built:
                rows.append([str(k), t.split('\n')[0], str(start), str(end), str(len(t))])
            else:
                nr = list(r)
                nr[h.index('no')] = str(k)
                nr[h.index('start_line')], nr[h.index('end_line')], nr[h.index('chars')] = str(start), str(end), str(len(t))
                rows.append(nr)
        new_text = '\n'.join(out_lines) + '\n'
        changed = new_text != '\n'.join(L) or built
        print(f'{os.path.basename(p)}: stories {len(stories)} | garbage/odd spans {nsp} | [image missing] lines {nmiss} | '
              f'{"manifest built" if built else "manifest recomputed"} | changed {changed} | check failures {len(bad)}')
        if bad:
            print('   STOP: check failed for stories at lines', bad[:5])
            continue
        if not go or not changed:
            continue
        for f in (p, m):
            if os.path.exists(f):
                shutil.copy2(f, os.path.join(B, os.path.basename(os.path.dirname(f)) + '__' + os.path.basename(f)))
        open(p, 'w', encoding='utf-8', newline='\n').write(new_text)
        buf = io.StringIO()
        csv.writer(buf, lineterminator=eol).writerows(rows)
        open(m, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + buf.getvalue().encode('utf-8'))


if __name__ == '__main__':
    main()
