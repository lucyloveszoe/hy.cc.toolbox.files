#!/usr/bin/env python3
"""Audit, de-duplicate and merge folders of html reports (PROCESSING_RULES.md sections 23, 25, 27, 28, 30-33).

Standard library only. Run it inside the project venv:

    source venv/bin/activate
    python merge_report_folders.py audit  <root> [--data-dir DIR]
    python merge_report_folders.py near   <root>
    python merge_report_folders.py dedupe <root> [--data-dir DIR] [--quarantine DIR] [--go]
    python merge_report_folders.py merge  <source-folder> <target-folder> [--backup-dir DIR] [--go]
    python merge_report_folders.py remove-source <source-folder> <target-folder> [--backup-dir DIR] [--go]
    python merge_report_folders.py repoint --old OLD --new NEW --data-dir DIR [DIR ...] [--backup-dir DIR] [--go]
    python merge_report_folders.py fix-fake <root> [--data-dir DIR] [--quarantine DIR] [--go]

Every command that changes something is a dry run unless --go is given. Nothing is ever deleted
by `dedupe` (duplicates go to a quarantine folder); `remove-source` deletes only on --go and only
after text and byte checks.

Layouts (detected from <root>):
  A  reports/<folder>/**.html + images/<folder>/**; CSVs <folder>_summary.csv and
     <folder>_images_manifest.csv in <root>.
  B  <folder>/**.html + <folder>/images/**; CSVs next to the folders (2010_07.Reports, series html).
  S  "single": reports/<report>.html + images/<report>/NNN.ext + manifest.csv, no root CSVs.

Rules: strings are compared lower-cased without whitespace; ratios are printed with two decimals.
"""
import argparse
import collections
import csv
import hashlib
import html
import os
import re
import shutil
import sys
import time

IMG_EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
FOOTER = re.compile(r'\s+-\s+([☆╉]|[^\s-]*春色).*$')          # forum footer in titles / file names
NOISE = re.compile('INCLUDEPICTURE|HYPERLINK|买春堂版权所有|本帖来源|�|\xa0|&#\\d+;|关闭注册|招财进宝|dizhidizhi'
                   '|[\x00-\x08\x0b\x0c\x0e-\x1f]')
NEAR_JACCARD, NEAR_CONTAIN, NEAR_MIN_CHARS = 0.7, 0.8, 300
NEW_SHARE = 0.6                                                   # source 8-gram share found in target


# ----------------------------------------------------------------------------- helpers
def r2(x):
    return f'{round(x, 2):.2f}'


def md5(path):
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()


def sniff(path):
    with open(path, 'rb') as fh:
        h = fh.read(12)
    return h[:3] == b'\xff\xd8\xff' or h[:8] == b'\x89PNG\r\n\x1a\n' or h[:4] == b'GIF8' or h[:2] == b'BM'


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def img_srcs(path):
    return [html.unescape(s) for s in re.findall(r'<img[^>]+src="([^"]+)"', read(path))]


def img_paths(path):
    """Absolute paths of the local images a report links (remote links are skipped)."""
    out = []
    for s in img_srcs(path):
        if re.match(r'(https?:|data:)', s):
            continue
        out.append(os.path.normpath(os.path.join(os.path.dirname(path), s.split('?')[0].split('#')[0])))
    return out


def norm_text(path):
    t = read(path)
    t = re.sub(r'<head>.*?</head>', '', t, flags=re.S)
    t = re.sub(r'<h1>.*?</h1>', '', t, flags=re.S)
    return re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]+>', '', t))).lower()


def grams(s):
    return {s[i:i + 8] for i in range(max(len(s) - 7, 0))}


def name_key(path):
    return tuple(re.sub(r'^p\d+_', '', os.path.basename(p)).lower() for p in img_paths(path))


def trim_footer(s):
    return FOOTER.sub('', s).rstrip()


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return list(csv.reader(fh))


def write_csv(path, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        csv.writer(fh, lineterminator='\r\n').writerows(rows)


def all_csvs(data_dir):
    """Every summary / manifest CSV under data_dir with an `output` column."""
    found = []
    for root, _dirs, files in os.walk(data_dir):
        if os.sep + 'txt' in root or os.sep + 'doc' in root or os.sep + 'pdf' in root:
            continue
        for f in files:
            if f.endswith(('_summary.csv', '_images_manifest.csv')):
                p = os.path.join(root, f)
                if 'output' in read_csv(p)[0]:
                    found.append(p)
    return sorted(found)


class Root:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        if os.path.isdir(os.path.join(self.path, 'reports')):
            has_csv = any(f.endswith('.csv') for f in os.listdir(self.path))
            self.layout = 'A' if has_csv else 'S'
        else:
            self.layout = 'B'
        if self.layout == 'A':
            base = os.path.join(self.path, 'reports')
            self.folders = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
        elif self.layout == 'S':
            self.folders = ['(single)']
        else:
            self.folders = sorted(d for d in os.listdir(self.path) if os.path.isdir(os.path.join(self.path, d)))

    def htmls(self, folder):
        j = os.path.join
        if self.layout == 'A':
            return sorted(walk(j(self.path, 'reports', folder), '.html'))
        if self.layout == 'S':
            return sorted(walk(j(self.path, 'reports'), '.html'))
        return sorted(walk(j(self.path, folder), '.html'))

    def images(self, folder):
        j = os.path.join
        base = {'A': j(self.path, 'images', folder), 'S': j(self.path, 'images'), 'B': j(self.path, folder)}[self.layout]
        return sorted(p for p in walk(base, None) if not p.endswith(('.html', '.DS_Store', 'manifest.csv')))

    def csv_path(self, folder, kind):
        return os.path.join(self.path, f'{folder}_{kind}.csv')


def walk(base, ext):
    out = []
    for root, _dirs, files in os.walk(base):
        for f in files:
            if f == '.DS_Store' or (ext and not f.endswith(ext)):
                continue
            out.append(os.path.join(root, f))
    return out


def unique_images(path):
    return len({os.path.basename(p) for p in img_paths(path)})


# ----------------------------------------------------------------------------- duplicate logic
def exact_groups(files):
    groups = collections.defaultdict(list)
    for f in files:
        groups[(norm_text(f), name_key(f))].append(f)
    return [sorted(v) for v in groups.values() if len(v) > 1]


def near_pairs(files):
    seen = {}
    for f in files:
        seen.setdefault((norm_text(f), name_key(f)), f)
    items = [(f, grams(t)) for (t, _k), f in seen.items() if len(t) >= NEAR_MIN_CHARS]
    pairs = []
    for i, (a, ga) in enumerate(items):
        for c, gc in items[i + 1:]:
            inter = len(ga & gc)
            if not inter:
                continue
            j = inter / len(ga | gc)
            if j > NEAR_JACCARD and inter / min(len(ga), len(gc)) > NEAR_CONTAIN:
                pairs.append((j, a, c))
    return sorted(pairs, reverse=True)


def image_hashes(path):
    return {md5(p) for p in img_paths(path) if os.path.exists(p)}


# ----------------------------------------------------------------------------- audit
def cmd_audit(args):
    root = Root(args.root)
    data_dir = os.path.abspath(args.data_dir or os.path.dirname(root.path))
    issues = collections.Counter()
    all_html, all_img = [], []
    print(f'root {root.path}  layout {root.layout}')
    for d in root.folders:
        hs, ims = root.htmls(d), set(root.images(d))
        linked, broken, remote, malformed, noise = set(), 0, 0, 0, 0
        for f in hs:
            t = read(f)
            if t.count('<section') != t.count('</section>') or not t.rstrip().endswith('</html>'):
                malformed += 1
            noise += bool(NOISE.search(t))
            for s in img_srcs(f):
                if re.match(r'(https?:|data:)', s):
                    remote += 1
            for p in img_paths(f):
                linked.add(p)
                broken += not os.path.exists(p)
        nonimg = [p for p in ims if not p.lower().endswith(IMG_EXT)]
        fake = [p for p in ims if p not in nonimg and not sniff(p)]
        orphans = len(ims - linked)
        print(f'{d}: html {len(hs)} images {len(ims)} broken {broken} remote {remote} orphans {orphans} '
              f'malformed {malformed} non-image-ext {len(nonimg)} FAKE-header {len(fake)} noise {noise}')
        for k, v in (('broken', broken), ('remote', remote), ('orphans', orphans), ('malformed', malformed),
                     ('non-image-ext', len(nonimg)), ('fake-header', len(fake))):
            issues[k] += v
        for p in fake[:3]:
            print('   FAKE', p)
        if root.layout != 'S':
            audit_csvs(root, d, hs, ims, issues)
        all_html += hs
        all_img += sorted(ims)
    if root.layout == 'S':
        bad = 0
        for f in all_html:
            stem = os.path.basename(f)[:-5]
            d = os.path.join(root.path, 'images', stem)
            files = sorted(x for x in os.listdir(d) if x not in ('manifest.csv', '.DS_Store')) if os.path.isdir(d) else None
            mp = os.path.join(d, 'manifest.csv')
            rows = read_csv(mp) if files is not None and os.path.exists(mp) else None
            if files is None or rows is None or sorted(r[0] for r in rows[1:]) != files:
                bad += 1
        print(f'per-report manifests: {len(all_html)} reports, inconsistent {bad}')
        issues['single manifests inconsistent'] += bad
    eg = exact_groups(all_html)
    nr = near_pairs(all_html)
    hashes = collections.defaultdict(list)
    for p in all_img:
        hashes[md5(p)].append(p)
    ig = [v for v in hashes.values() if len(v) > 1]
    print(f'TOTAL html {len(all_html)} images {len(all_img)} | exact-duplicate groups {len(eg)} '
          f'(extra {sum(len(v) - 1 for v in eg)}) | near pairs {len(nr)} | identical-image groups {len(ig)} '
          f'(extra {sum(len(v) - 1 for v in ig)})')
    issues['exact-duplicate groups'] += len(eg)
    # all CSVs in data_dir: every output must exist
    n = miss = 0
    for p in all_csvs(data_dir):
        rows = read_csv(p)
        oi = rows[0].index('output')
        for x in rows[1:]:
            if len(x) > oi and x[oi]:
                n += 1
                if not os.path.exists(os.path.join(os.path.dirname(p), x[oi])):
                    miss += 1
                    if miss <= 5:
                        print('   MISSING', os.path.relpath(p, data_dir), x[oi][-60:])
    print(f'all CSVs under {data_dir}: outputs {n} missing {miss}')
    issues['csv outputs missing (all CSVs)'] += miss
    empties = []
    for r, ds, fs in os.walk(root.path):
        if not ds and not [x for x in fs if x != '.DS_Store']:
            empties.append(os.path.relpath(r, root.path))
    print('empty folders:', empties or 'none')
    issues['empty folders'] += len(empties)
    found = {k: v for k, v in issues.items() if v}
    print('ISSUES:', found or 'none')
    return 1 if found else 0


def audit_csvs(root, d, hs, ims, issues):
    for kind in ('summary', 'images_manifest'):
        p = root.csv_path(d, kind)
        if not os.path.exists(p):
            print('   MISSING CSV', os.path.basename(p))
            issues['missing csv'] += 1
            continue
        with open(p, 'rb') as fh:
            bom = fh.read(3) == b'\xef\xbb\xbf'
        rows = read_csv(p)
        hd = rows[0]
        oi = hd.index('output')
        outs = [os.path.join(root.path, r[oi]) for r in rows[1:] if len(r) > oi and r[oi]]
        outs = [os.path.normpath(o) for o in outs]
        miss = sum(not os.path.exists(o) for o in outs)
        ragged = sum(len(r) != len(hd) for r in rows[1:])
        keys = collections.Counter(r[0] for r in rows[1:])
        dupkey = sum(v - 1 for v in keys.values() if v > 1)
        extra = ''
        if kind == 'summary':
            hset = {os.path.normpath(h) for h in hs}
            not_in = len(hset - set(outs))
            mismatch = sum(1 for r in rows[1:] if r[1] == 'html' and r[oi].endswith('.html')
                           and os.path.exists(os.path.normpath(os.path.join(root.path, r[oi])))
                           and str(unique_images(os.path.normpath(os.path.join(root.path, r[oi])))) != r[4])
            extra = f' html-not-in-summary {not_in} images_copied-mismatch {mismatch}'
            issues['html-not-in-summary'] += not_in
            issues['images_copied-mismatch'] += mismatch
        else:
            not_in = len({os.path.normpath(i) for i in ims} - set(outs))
            untagged = sum(1 for r in rows[1:] if r[1].startswith('copied') and not r[oi]
                           and 'no longer' not in r[1] and 'not a picture' not in r[1])
            extra = f' images-not-in-manifest {not_in} untagged-copied-without-output {untagged}'
            issues['images-not-in-manifest'] += not_in
            issues['untagged copied without output'] += untagged
        print(f'   {os.path.basename(p)}: rows {len(rows) - 1} bom {bom} ragged {ragged} missing-output {miss} '
              f'dup-key {dupkey}{extra}')
        issues['csv missing output'] += miss
        issues['ragged rows'] += ragged
        issues['no BOM'] += (not bom)


# ----------------------------------------------------------------------------- near
def cmd_near(args):
    root = Root(args.root)
    files = [f for d in root.folders for f in root.htmls(d)]
    pairs = near_pairs(files)
    print(f'{len(pairs)} near pairs (>= {NEAR_MIN_CHARS} chars, Jaccard > {NEAR_JACCARD}, containment > {NEAR_CONTAIN})')
    for j, a, c in pairs:
        ha, hc = image_hashes(a), image_hashes(c)
        print(f'J={r2(j)} "{os.path.basename(a)[:24]}"[{len(ha)} imgs] vs "{os.path.basename(c)[:24]}"[{len(hc)} imgs] | '
              f'common {len(ha & hc)} only-1st {len(ha - hc)} only-2nd {len(hc - ha)} | '
              f'text {len(norm_text(a))}/{len(norm_text(c))}')
    print('Classify by hand: no common image = different posts; byte-contained and not longer = removable; '
          'mixed = keep both (section 31).')
    return 0


# ----------------------------------------------------------------------------- dedupe
def cmd_dedupe(args):
    root = Root(args.root)
    data_dir = os.path.abspath(args.data_dir or os.path.dirname(root.path))
    files = [f for d in root.folders for f in root.htmls(d)]
    groups = exact_groups(files)
    priority = {name: i for i, name in enumerate(args.priority.split(',') if args.priority else [])}

    def folder_of(f):
        rel = os.path.relpath(f, root.path).split(os.sep)
        return rel[1] if root.layout == 'A' else rel[0]

    plan, held = [], []
    for g in groups:
        g.sort(key=lambda f: (-unique_images(f), -len(os.path.basename(f)), priority.get(folder_of(f), 99), f))
        keep = g[0]
        for r in g[1:]:
            plan.append((r, keep))
    use = collections.defaultdict(set)
    for f in files:
        for p in img_paths(f):
            use[p].add(f)
    removed = {r for r, _ in plan}
    move = {}
    final = []
    for r, k in plan:
        ri, ki = img_paths(r), img_paths(k)
        diff = [(a, b) for a, b in zip(ri, ki) if os.path.exists(a) and os.path.exists(b) and md5(a) != md5(b)]
        if diff or len(ri) != len(ki):
            held.append((r, k, len(diff)))
            continue
        final.append((r, k))
        for a, b in zip(ri, ki):
            if use[a] <= removed:
                move[a] = b
    print(f'exact-duplicate groups {len(groups)}, reports to remove {len(final)}, images to quarantine {len(move)}')
    for r, k in final:
        print(f'  remove {os.path.relpath(r, root.path)[:60]} | keep {os.path.relpath(k, root.path)[:60]}')
    for r, k, n in held:
        print(f'  HELD (images differ in bytes: {n}) {os.path.relpath(r, root.path)[:60]} -> compare quality first (section 28)')
    if not args.go:
        print('dry run; add --go to quarantine')
        return 0
    quarantine = os.path.abspath(args.quarantine or os.path.join(data_dir, '_quarantine_' + time.strftime('%Y%m%d_%H%M%S')))
    os.makedirs(quarantine, exist_ok=False)
    rmap = {r: k for r, k in final}
    allmap = {**rmap, **move}
    csvs = all_csvs(data_dir)
    bdir = os.path.join(quarantine, '_csv_backup')
    for c in csvs:
        dst = os.path.join(bdir, os.path.relpath(c, data_dir))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(c, dst)
    n = repoint_csvs(csvs, allmap, rmap)
    log = []
    for src in list(rmap) + list(move):
        dst = os.path.join(quarantine, os.path.relpath(src, data_dir))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        log.append(f'{os.path.relpath(src, data_dir)}\t->kept\t{os.path.relpath(allmap[src], data_dir)}')
    for d in sorted(walk_dirs(root.path)):                      # per-report image folders left with only manifest.csv
        left = [x for x in os.listdir(d) if x != '.DS_Store']
        if left == ['manifest.csv']:
            dst = os.path.join(quarantine, os.path.relpath(d, data_dir))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(d, dst)
            log.append(f'{os.path.relpath(d, data_dir)}\t->emptied')
    with open(os.path.join(quarantine, 'removed_to_kept.tsv'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(log))
    print(f'quarantined {len(rmap)} reports + {len(move)} images -> {quarantine}; CSV rows repointed {n}')
    print('now run: audit; delete the quarantine only on the user\'s word after a byte check (section 31).')
    return 0


def walk_dirs(base):
    out = []
    for r, ds, _fs in os.walk(base):
        out += [os.path.join(r, d) for d in ds]
    return out


def repoint_csvs(csvs, allmap, report_map):
    total = 0
    for c in csvs:
        rows = read_csv(c)
        oi = rows[0].index('output')
        issum = c.endswith('_summary.csv')
        folder = os.path.dirname(os.path.abspath(c))
        changed = 0
        for x in rows[1:]:
            if len(x) <= oi or not x[oi]:
                continue
            full = os.path.normpath(os.path.join(folder, x[oi]))
            if full in allmap:
                x[oi] = os.path.relpath(allmap[full], folder)
                changed += 1
                if issum and full in report_map and len(x) > 4:
                    x[4] = str(unique_images(report_map[full]))
        if changed:
            write_csv(c, rows)
            total += changed
    return total


# ----------------------------------------------------------------------------- merge
def folder_reports(folder):
    return sorted(walk(folder, '.html'))


def classify(source, target):
    """Compare every report of `source` with all reports of the target root (not the source itself)."""
    tgt_root = os.path.dirname(os.path.abspath(target))
    src_abs = os.path.abspath(source)
    pool = {}
    for d in sorted(os.listdir(tgt_root)):
        p = os.path.join(tgt_root, d)
        if os.path.isdir(p) and os.path.abspath(p) != src_abs:
            for f in folder_reports(p):
                pool[f] = (norm_text(f), name_key(f))
    pgrams = {f: grams(t) for f, (t, _k) in pool.items()}
    exact, near, new = [], [], []
    for f in folder_reports(source):
        t, k = norm_text(f), name_key(f)
        if any(t == tt and k == kk for tt, kk in pool.values()):
            exact.append(f)
            continue
        x = grams(t)
        share, best = max(((len(x & y) / max(len(x), 1), p) for p, y in pgrams.items()), default=(0.0, None))
        if share > NEW_SHARE:
            near.append((f, best, share))
        else:
            new.append(f)
            pool[f] = (t, k)
            pgrams[f] = x
    return exact, near, new


def cmd_merge(args):
    source, target = os.path.abspath(args.source), os.path.abspath(args.target)
    sf, tf = os.path.basename(source), os.path.basename(target)
    sroot, troot = os.path.dirname(source), os.path.dirname(target)
    exact, near, new = classify(source, target)
    dest = {}
    for f in new:
        rel = os.path.relpath(f, source)
        d, b = os.path.split(rel)
        dest[f] = os.path.join(target, d, trim_footer(b[:-5]) + '.html')
    clashes = [d for d in dest.values() if os.path.exists(d)]
    if len(set(dest.values())) != len(dest) or clashes:
        print('NAME CLASH, stop:', clashes[:5])
        return 1
    need = {}
    for f in new:
        for p in img_paths(f):
            need[os.path.relpath(p, os.path.join(source, 'images', sf))] = p
    print(f'source {sf} -> target {tf}: exact duplicates {len(exact)} (skipped), near {len(near)} (listed, not copied), '
          f'new {len(new)} (copy), images to copy {len(need)}')
    for f, best, share in near:
        print(f'  NEAR share={r2(share)} imgs {unique_images(f)} vs {unique_images(best)} '
              f'"{os.path.basename(f)[:30]}" ~ "{os.path.basename(best)[:30]}": decide by hand (section 23 step 3)')
    if not args.go:
        print('dry run; add --go to copy')
        return 0
    backup = os.path.abspath(args.backup_dir or os.path.join(troot, '_merge_backup_' + time.strftime('%Y%m%d_%H%M%S')))
    os.makedirs(backup, exist_ok=False)
    for kind in ('summary', 'images_manifest'):
        p = os.path.join(troot, f'{tf}_{kind}.csv')
        if os.path.exists(p):
            shutil.copy2(p, backup)
    for f in new:                                               # reports: links and footer rewritten
        t = read(f).replace(f'images/{sf}/', f'images/{tf}/')
        t = re.sub(r'(<title>|<h1>)(.*?)(</title>|</h1>)',
                   lambda m: m.group(1) + trim_footer(m.group(2)) + m.group(3), t, flags=re.S)
        os.makedirs(os.path.dirname(dest[f]), exist_ok=True)
        with open(dest[f], 'w', encoding='utf-8', newline='') as fh:
            fh.write(t)
    for rel, p in need.items():                                 # images: copy, identical if present
        dst = os.path.join(target, 'images', tf, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            if md5(dst) != md5(p):
                print('  WARNING different bytes under the same name:', dst)
        else:
            shutil.copy2(p, dst)
    merge_csvs(sroot, troot, sf, tf, source, target, dest, exact, near)
    print(f'copied. CSV backups in {backup}. Run: audit {troot}')
    return 0


def merge_csvs(sroot, troot, sf, tf, source, target, dest, exact, near):
    spath, mpath = os.path.join(sroot, f'{sf}_summary.csv'), os.path.join(sroot, f'{sf}_images_manifest.csv')
    tspath, tmpath = os.path.join(troot, f'{tf}_summary.csv'), os.path.join(troot, f'{tf}_images_manifest.csv')
    if not (os.path.exists(spath) and os.path.exists(tspath)):
        print('  (no summary CSVs: rows not merged)')
        return
    s_rows, t_rows = read_csv(spath), read_csv(tspath)
    if 'note' not in t_rows[0] and 'note' in s_rows[0]:
        t_rows[0].append('note')
        for r in t_rows[1:]:
            r.append('')
    width = len(t_rows[0])
    have = {r[0] for r in t_rows[1:]}
    oi = s_rows[0].index('output')
    outmap = {os.path.relpath(f, sroot): os.path.relpath(d, troot) for f, d in dest.items()}
    skipped = {os.path.relpath(f, sroot): 'exact duplicate of an existing report (skipped)' for f in exact}
    skipped.update({os.path.relpath(f, sroot): 'near duplicate of an existing report (skipped)' for f, _b, _s in near})
    for r in s_rows[1:]:
        if r[0] in have:
            continue
        r = r + [''] * (width - len(r))
        if r[oi] in outmap:
            r[oi] = outmap[r[oi]]
        elif r[oi] in skipped:
            r[width - 1 if 'note' in t_rows[0] else oi] = skipped[r[oi]]
            r[oi] = ''
        else:
            r[oi] = ''
        t_rows.append(r[:width])
    write_csv(tspath, t_rows)
    if os.path.exists(mpath) and os.path.exists(tmpath):
        m_src, m_tgt = read_csv(mpath), read_csv(tmpath)
        used = {os.path.basename(p) for f in dest for p in img_paths(f)}
        have_out = {x[2] for x in m_tgt[1:]}
        for r in m_src[1:]:
            if r[2] and os.path.basename(r[2]) in used:
                out = os.path.join(tf, 'images', tf, os.path.basename(r[2]))
                if out not in have_out:
                    m_tgt.append([r[0], r[1], out])
                    have_out.add(out)
        write_csv(tmpath, m_tgt)


def cmd_remove_source(args):
    source, target = os.path.abspath(args.source), os.path.abspath(args.target)
    sf = os.path.basename(source)
    sroot, troot = os.path.dirname(source), os.path.dirname(target)
    pool = [f for d in os.listdir(troot) for f in folder_reports(os.path.join(troot, d))
            if os.path.isdir(os.path.join(troot, d)) and os.path.abspath(os.path.join(troot, d)) != source]
    pgrams = [grams(norm_text(f)) for f in pool]
    pimg = set()
    for d in os.listdir(troot):
        p = os.path.join(troot, d)
        if os.path.isdir(p) and os.path.abspath(p) != source:
            pimg |= {md5(x) for x in walk(p, None) if x.lower().endswith(IMG_EXT)}
    miss_r = []
    for f in folder_reports(source):
        x = grams(norm_text(f))
        if not x or max(len(x & y) / len(x) for y in pgrams) < 0.9:
            miss_r.append(f)
    imgs_src = [x for x in walk(source, None) if x.lower().endswith(IMG_EXT)]
    miss_i = [x for x in imgs_src if md5(x) not in pimg]
    print(f'{sf}: reports {len(folder_reports(source))} not covered (< 0.90) {len(miss_r)} | images {len(imgs_src)} without identical copy {len(miss_i)}')
    if miss_r or miss_i:
        print('NOT SAFE to remove; first items:', [os.path.basename(x)[:30] for x in (miss_r + miss_i)[:5]])
        return 1
    if not args.go:
        print('safe; dry run, add --go to delete the source folder and its two CSVs')
        return 0
    backup = os.path.abspath(args.backup_dir or os.path.join(sroot, '_remove_backup_' + time.strftime('%Y%m%d_%H%M%S')))
    os.makedirs(backup, exist_ok=False)
    for kind in ('summary', 'images_manifest'):
        p = os.path.join(sroot, f'{sf}_{kind}.csv')
        if os.path.exists(p):
            shutil.copy2(p, backup)
    with open(os.path.join(backup, 'deleted_files.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(os.path.relpath(x, sroot) for x in walk(source, None)))
    shutil.rmtree(source)
    for kind in ('summary', 'images_manifest'):
        p = os.path.join(sroot, f'{sf}_{kind}.csv')
        if os.path.exists(p):
            os.remove(p)
    print(f'deleted {source} and its CSVs; backup and file list in {backup}')
    return 0


# ----------------------------------------------------------------------------- repoint (section 36)
def cmd_repoint(args):
    """Repair CSV `output` paths after a report folder was moved or renamed."""
    old, new = os.path.abspath(args.old), os.path.abspath(args.new)
    dirs = [os.path.abspath(d) for d in args.data_dir]
    csvs = sorted({c for d in dirs for c in all_csvs(d)})
    plan = {}
    unresolved = []
    for c in csvs:
        rows = read_csv(c)
        oi = rows[0].index('output')
        folder = os.path.dirname(c)
        base = old if os.path.commonpath([folder, new]) == new else folder   # a moved CSV is read against its old folder
        changed = 0
        for x in rows[1:]:
            if len(x) <= oi or not x[oi] or os.path.exists(os.path.normpath(os.path.join(folder, x[oi]))):
                continue
            full = os.path.normpath(os.path.join(base, x[oi]))
            cand = new + full[len(old):] if full.startswith(old + os.sep) else full
            if os.path.exists(cand):
                x[oi] = os.path.relpath(cand, folder)
                changed += 1
            else:
                unresolved.append((c, x[oi]))
        if changed:
            plan[c] = (rows, changed)
    print(f'CSV files {len(csvs)}: {len(plan)} need repair, rows to repoint {sum(n for _r, n in plan.values())}, '
          f'unresolved {len(unresolved)}')
    for c, (_r, n) in plan.items():
        print(f'  {os.path.relpath(c, os.path.commonpath(dirs))}: {n}')
    for c, o in unresolved[:5]:
        print('  UNRESOLVED', os.path.basename(c), o[-60:])
    if not args.go:
        print('dry run; add --go to write (CSVs are copied to --backup-dir first)')
        return 0
    backup = os.path.abspath(args.backup_dir or os.path.join(os.path.dirname(new), '_repoint_backup_' + time.strftime('%Y%m%d_%H%M%S')))
    os.makedirs(backup, exist_ok=False)
    for c, (rows, _n) in plan.items():
        shutil.copy2(c, os.path.join(backup, hashlib.md5(c.encode()).hexdigest() + '_' + os.path.basename(c)))
        write_csv(c, rows)
    print(f'repointed; originals in {backup}')
    return 1 if unresolved else 0


# ----------------------------------------------------------------------------- fix-fake (section 30)
def cmd_fix_fake(args):
    """Image files that are really error pages: tag in report, tag in CSVs, move the file to a quarantine."""
    root = Root(args.root)
    data_dir = os.path.abspath(args.data_dir or os.path.dirname(root.path))
    reports = [f for d in root.folders for f in root.htmls(d)]
    fakes = [p for d in root.folders for p in root.images(d) if p.lower().endswith(IMG_EXT) and not sniff(p)]
    linked = collections.defaultdict(list)
    for f in reports:
        for p in img_paths(f):
            linked[p].append(f)
    print(f'{len(fakes)} image files with a non-image header')
    for p in fakes:
        print(f'  {os.path.getsize(p)} B {os.path.relpath(p, root.path)[:70]} linked by {len(linked[p])} report(s)')
    if not fakes or not args.go:
        if fakes:
            print('dry run; add --go to replace the tags with [image missing], tag the CSV rows and quarantine the files')
        return 0
    quarantine = os.path.abspath(args.quarantine or os.path.join(data_dir, '_quarantine_fake_' + time.strftime('%Y%m%d_%H%M%S')))
    os.makedirs(quarantine, exist_ok=False)
    csvs = all_csvs(data_dir)
    for c in csvs:
        dst = os.path.join(quarantine, '_csv_backup', os.path.relpath(c, data_dir))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(c, dst)
    fake_set = set(fakes)
    for p in fakes:
        name = os.path.basename(p)
        for f in linked[p]:
            t = read(f)
            pat = '|'.join(re.escape(n) for n in {name, html.escape(name)})
            t2, n = re.subn(r'<img[^>]*(?:' + pat + r')[^>]*>', '[image missing]', t)
            if n:
                with open(f, 'w', encoding='utf-8', newline='') as fh:
                    fh.write(t2)
    for c in csvs:
        rows = read_csv(c)
        oi = rows[0].index('output')
        folder = os.path.dirname(c)
        changed = False
        for x in rows[1:]:
            if len(x) <= oi or not x[oi]:
                continue
            full = os.path.normpath(os.path.join(folder, x[oi]))
            if full in fake_set and c.endswith('_images_manifest.csv'):
                x[oi] = ''
                x[1] = x[1] + ' [image file was not a picture]'
                changed = True
            elif c.endswith('_summary.csv') and len(x) > 4 and x[4].isdigit() and int(x[4]) > 0:
                k = sum(1 for p in fakes if full in linked[p])
                if k:
                    x[4] = str(max(0, int(x[4]) - k))
                    changed = True
        if changed:
            write_csv(c, rows)
    for p in fakes:
        dst = os.path.join(quarantine, os.path.relpath(p, data_dir))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(p, dst)
    print(f'fixed {len(fakes)} files; quarantine {quarantine} (delete it only on the user\'s word)')
    return 0


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('audit', help='links, orphans, headers, CSVs, duplicates, empty folders')
    a.add_argument('root')
    a.add_argument('--data-dir', help='folder whose CSVs are all checked (default: parent of root)')
    a.set_defaults(fn=cmd_audit)
    n = sub.add_parser('near', help='list near-duplicate pairs with image containment')
    n.add_argument('root')
    n.set_defaults(fn=cmd_near)
    d = sub.add_parser('dedupe', help='quarantine exact duplicate reports (dry run unless --go)')
    d.add_argument('root')
    d.add_argument('--data-dir')
    d.add_argument('--quarantine')
    d.add_argument('--priority', help='comma-separated folder names, kept first on ties')
    d.add_argument('--go', action='store_true')
    d.set_defaults(fn=cmd_dedupe)
    m = sub.add_parser('merge', help='copy new reports of one folder into another (dry run unless --go)')
    m.add_argument('source')
    m.add_argument('target')
    m.add_argument('--backup-dir')
    m.add_argument('--go', action='store_true')
    m.set_defaults(fn=cmd_merge)
    r = sub.add_parser('remove-source', help='delete a merged source folder after text and byte checks')
    r.add_argument('source')
    r.add_argument('target')
    r.add_argument('--backup-dir')
    r.add_argument('--go', action='store_true')
    r.set_defaults(fn=cmd_remove_source)
    p = sub.add_parser('repoint', help='repair CSV outputs after a folder was moved or renamed (dry run unless --go)')
    p.add_argument('--old', required=True, help='old absolute path of the moved folder')
    p.add_argument('--new', required=True, help='new absolute path of the moved folder')
    p.add_argument('--data-dir', nargs='+', required=True, help='folders whose CSVs are scanned (include the new location)')
    p.add_argument('--backup-dir')
    p.add_argument('--go', action='store_true')
    p.set_defaults(fn=cmd_repoint)
    ff = sub.add_parser('fix-fake', help='fix image files that are error pages (dry run unless --go)')
    ff.add_argument('root')
    ff.add_argument('--data-dir')
    ff.add_argument('--quarantine')
    ff.add_argument('--go', action='store_true')
    ff.set_defaults(fn=cmd_fix_fake)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
