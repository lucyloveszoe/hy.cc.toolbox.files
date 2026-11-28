"""Make the txt and docx files of a raw archive human readable (PROCESSING_LOGIC 4.4): dry run by default.

    python3 -I clean_text_docs.py <archive dir> [--go --backup-dir D]

Removed (txt and docx alike):
  * Discuz anti-copy garbage runs: >= 5 tokens of 1-2 printable ASCII chars separated by spaces, >= 60 % of them
    'jammer-like' (contain a symbol, or letter+digit), at least one symbol, > 2 distinct tokens, not a '- - -' rule
    (keeps rating codes 'kj sw xt ml', spaced phone numbers, separators)
  * Discuz edit stamps '本帖最后由 X 于 <date> 编辑'
  * zero-width / bidi characters, private-use characters, U+FFFD
txt only: decoded strictly (UTF-16 BOM, UTF-8, GB18030, Big5-HKSCS) and written as UTF-8 without BOM, LF line ends,
  trailing spaces stripped, 3+ blank lines -> 1, one final newline.
docx: word/document.xml (+ headers/footers/footnotes) is edited paragraph by paragraph: the text of all <w:t> runs of a
  paragraph is joined, the spans above are found in the joined text, and exactly those characters are removed from
  their runs (formatting, pictures and everything else untouched). The zip is rewritten with the same members, order
  and compression. Check: textutil text after == text before with only the removed spans gone (CJK unchanged).
.doc (binary Word) is never edited; files with hits are listed.
"""
import html
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile

RUN = re.compile(r'(?:[!-~]{1,2}[  ]+){4,}[!-~]{1,2}')
STAMP = re.compile(r'\[?\s*本帖最[后後]由\s*\S{1,30}\s*[于於][^\n ]{1,40}?[编編][辑輯]\s*\]?')
ODD = re.compile('[​-‏‪-‮⁠﻿-�]')


def jammerish(tok):
    return bool(re.search(r'[^\w\s]', tok) or re.fullmatch(r'[A-Za-z]\d|\d[A-Za-z]', tok))


def spans(t):
    out = []
    for m in RUN.finditer(t):
        toks = m.group(0).split()
        punct = sum(bool(re.search(r'[^\w\s]', x)) for x in toks)
        if (len(toks) >= 5 and sum(map(jammerish, toks)) >= 0.6 * len(toks) and punct >= 1 and len(set(toks)) > 2
                and not all(x in '-=*_.~' for x in toks)):
            a = m.start()
            while a > 0 and t[a - 1] in '  　':      # the space that led into the run goes too
                a -= 1
            out.append((a, m.end()))
    out += [(m.start(), m.end()) for m in STAMP.finditer(t)]
    out += [(m.start(), m.end()) for m in ODD.finditer(t)]
    out.sort()
    merged = []
    for a, b in out:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def cut(t, sp):
    keep, pos = [], 0
    for a, b in sp:
        keep.append(t[pos:a])
        pos = b
    keep.append(t[pos:])
    return ''.join(keep)


def decode(b):
    if b.startswith((b'\xff\xfe', b'\xfe\xff')):
        return b.decode('utf-16'), 'utf-16'
    if b.startswith(b'\xef\xbb\xbf'):
        return b[3:].decode('utf-8'), 'utf-8-bom'
    for e in ('utf-8', 'gb18030', 'big5hkscs'):
        try:
            return b.decode(e), e
        except UnicodeDecodeError:
            pass
    return None, None


def clean_txt(b):
    t, enc = decode(b)
    if t is None:
        return None, enc, 0
    sp = spans(t)
    t2 = cut(t, sp).replace('\r\n', '\n').replace('\r', '\n')
    t2 = '\n'.join(l.rstrip() for l in t2.split('\n'))
    t2 = re.sub(r'\n{3,}', '\n\n', t2).strip('\n') + '\n'
    return t2.encode('utf-8'), enc, len(sp)


T_RUN = re.compile(r'(<w:t(?:\s[^>]*)?>)([^<]*)(</w:t>)')
PARA = re.compile(r'<w:p[ >].*?</w:p>', re.S)


def clean_xml(xml):
    n = 0

    def para(m):
        nonlocal n
        p = m.group(0)
        runs = list(T_RUN.finditer(p))
        if not runs:
            return p
        texts = [html.unescape(r.group(2)) for r in runs]
        joined = ''.join(texts)
        sp = spans(joined)
        if not sp:
            return p
        n += len(sp)
        drop = set()
        for a, b in sp:
            drop.update(range(a, b))
        out, pos, k = [], 0, 0
        for r, tx in zip(runs, texts):
            new = ''.join(ch for i, ch in enumerate(tx, start=k) if i not in drop)
            k += len(tx)
            out.append(p[pos:r.start()])
            open_tag = r.group(1)
            if new != new.strip() and 'xml:space' not in open_tag:
                open_tag = open_tag[:-1] + ' xml:space="preserve">'
            out.append(open_tag + html.escape(new, quote=False) + r.group(3))
            pos = r.end()
        out.append(p[pos:])
        return ''.join(out)
    return PARA.sub(para, xml), n


def docx_text(path):
    return subprocess.run(['textutil', '-convert', 'txt', '-stdout', '-encoding', 'UTF-8', path],
                          capture_output=True).stdout.decode('utf-8', 'replace')


def clean_docx(path, out_path):
    zin = zipfile.ZipFile(path)
    total = 0
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if re.fullmatch(r'word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml', info.filename):
                x, n = clean_xml(data.decode('utf-8'))
                if n:
                    data = x.encode('utf-8')
                    total += n
            zout.writestr(info, data)
    if total:
        open(out_path, 'wb').write(buf.getvalue())
    return total


def cjk(s):
    return sorted(re.findall(r'[㐀-鿿]', s))


def main():
    A = sys.argv[1]
    go = '--go' in sys.argv
    B = sys.argv[sys.argv.index('--backup-dir') + 1] if '--backup-dir' in sys.argv else None
    if go:
        assert B and not os.path.exists(B)
        os.makedirs(B)
    stats = {'txt rewritten': 0, 'txt re-encoded to UTF-8': 0, 'txt spans removed': 0, 'docx changed': 0,
             'docx spans removed': 0, 'undecodable txt': 0, 'docx check failed': 0}
    doc_hits = []
    tmp = os.path.join(B or '/tmp', '_tmp.docx') if go else None
    for d, _, fs in os.walk(A):
        for f in sorted(fs):
            p = os.path.join(d, f)
            ext = os.path.splitext(f)[1].lower()
            if ext == '.txt':
                b = open(p, 'rb').read()
                nb, enc, n = clean_txt(b)
                if nb is None:
                    stats['undecodable txt'] += 1
                    print('   UNDECODABLE', os.path.relpath(p, A))
                    continue
                if nb != b:
                    stats['txt rewritten'] += 1
                    stats['txt re-encoded to UTF-8'] += enc not in ('utf-8',)
                    stats['txt spans removed'] += n
                    if go:
                        dst = os.path.join(B, os.path.relpath(p, A))
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(p, dst)
                        open(p, 'wb').write(nb)
            elif ext == '.docx' and not f.startswith('~$'):
                before = docx_text(p)
                if not spans(before):
                    continue
                if not go:
                    stats['docx changed'] += 1
                    stats['docx spans removed'] += len(spans(before))
                    continue
                n = clean_docx(p, tmp)
                if not n:
                    continue
                after = docx_text(tmp)
                if cjk(after) != cjk(cut(before, spans(before))) or len(after) >= len(before):
                    stats['docx check failed'] += 1
                    print('   CHECK FAILED, left unchanged:', os.path.relpath(p, A))
                    os.remove(tmp)
                    continue
                dst = os.path.join(B, os.path.relpath(p, A))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(p, dst)
                shutil.move(tmp, p)
                stats['docx changed'] += 1
                stats['docx spans removed'] += n
            elif ext == '.doc':
                t = docx_text(p)
                k = len([s for s in spans(t) if not ODD.fullmatch(t[s[0]:s[1]])])
                if k:
                    doc_hits.append((os.path.relpath(p, A), k))
    print(stats, '(written)' if go else '(dry run)')
    for p, k in doc_hits:
        print(f'   .doc not edited (binary): {p} - {k} garbage spans')


if __name__ == '__main__':
    main()
