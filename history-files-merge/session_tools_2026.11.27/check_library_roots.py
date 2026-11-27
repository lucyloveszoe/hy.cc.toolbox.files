"""READ-ONLY check of library roots in the flat layout <root>/{reports/*.html, images/<root>/*, <root>_summary.csv,
<root>_images_manifest.csv} (merge_report_folders.py audit does not recognise this layout and prints html 0).

    python3 check_library_roots.py <root dir> [<root dir> ...]

Per root: pages, images, broken local <img src> (html-unescaped, NFC), remote <img src>, unused images (no page of the
root links them), pages missing from the summary, summary/manifest outputs that do not exist, images not named by any
manifest output, malformed pages (no </html> or unbalanced <section>).
"""
import csv, html, os, re, sys, unicodedata
SRC = re.compile(r'<img[^>]*?\ssrc="([^"]+)"', re.I)
nfc = lambda p: unicodedata.normalize('NFC', os.path.normpath(p))
bad_total = 0
for R in sys.argv[1:]:
    R = os.path.abspath(R); name = os.path.basename(R)
    pages = [os.path.join(R, 'reports', f) for f in os.listdir(os.path.join(R, 'reports')) if f.lower().endswith(('.html', '.htm'))]
    idir = os.path.join(R, 'images')
    imgs = {nfc(os.path.join(d, f)) for d, _, fs in os.walk(idir) for f in fs if f != '.DS_Store'}
    linked = set(); broken = remote = malformed = 0
    for p in pages:
        t = open(p, encoding='utf-8', errors='replace').read()
        if '</html>' not in t.lower() or t.count('<section') != t.count('</section>'): malformed += 1
        for s in SRC.findall(t):
            v = html.unescape(s)
            if re.match(r'^(?:https?:|//)', v, re.I): remote += 1; continue
            if v.startswith('data:'): continue
            q = nfc(os.path.join(os.path.dirname(p), v))
            if os.path.isfile(q): linked.add(q)
            else: broken += 1
    def outs(csvname):
        p = os.path.join(R, csvname)
        if not os.path.exists(p): return None
        return [nfc(os.path.join(R, r['output'])) for r in csv.DictReader(open(p, encoding='utf-8-sig', newline='')) if (r.get('output') or '').strip()]
    so = outs(f'{name}_summary.csv') or []; mo = outs(f'{name}_images_manifest.csv') or []
    miss_out = sum(1 for o in so + mo if not os.path.exists(o))
    not_in_summary = sum(1 for p in pages if nfc(p) not in set(so))
    unused = len(imgs - linked)
    not_in_manifest = len(imgs - set(mo))
    bad = broken + remote + malformed + miss_out + not_in_summary + unused
    bad_total += bad
    print(f'{name}: pages {len(pages)} images {len(imgs)} broken {broken} remote {remote} malformed {malformed} unused-images {unused} '
          f'pages-not-in-summary {not_in_summary} missing-outputs {miss_out} images-not-in-manifest {not_in_manifest}')
print('TOTAL problems', bad_total)
