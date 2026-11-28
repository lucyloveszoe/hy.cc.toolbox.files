"""Process saved forum pages (.htm + *_files) into txt / html reports / images.

Usage: python process_html_posts.py <source_folder> [...] [-o OUTDIR]

For every .htm under the source folder (Discuz-style threads: one <table id="pidNNN"> per post):
  * the page has images in the primary post or in any reply
        -> outputs/reports/<folder>/<rel path>.html   primary post + every reply that has images
           outputs/images/<folder>/p<NN>_<name>       only the images of those posts (copied)
  * no images anywhere
        -> outputs/txt/<folder>/<rel path>.txt        primary post text only
  * noise (maichun watermark + garbage tokens) is removed from all text.
  * pages without pid tables (other layouts) are listed as 'unsupported' for manual review.
Originals are never modified. A summary.csv is written to outputs/<folder>_summary.csv.
"""
import argparse
import csv
import html
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

from clean_doc_noise import clean
from htmltree import Node, decode_file, parse

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
BLOCK = {"p", "div", "tr", "li", "blockquote", "table", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "center", "fieldset", "dd", "dt"}
PH_L, PH_R = "", ""
ROUTED: dict = {}  # source image path -> destination path
UNRESOLVED: list = []  # image refs (jpg/png/bmp) whose file was not found, per page


def text_of(n: Node) -> str:
    return "".join(c if isinstance(c, str) else text_of(c) for c in n.children)


def is_ad(n: Node) -> bool:
    """Ads and anti-copy garbage: elements hidden by CSS (font-size:0, display:none,
    visibility:hidden) or white-on-white ASCII-only text (no CJK)."""
    i = n.attrs.get("id", "")
    st = n.attrs.get("style", "").replace(" ", "").lower()
    if i.startswith("ad_") or "overture" in i:
        return True
    if "jammer" in n.cls():  # Discuz X anti-copy garbage (<font class="jammer">, hidden by the site CSS)
        return True
    if "display:none" in st or "visibility:hidden" in st or re.search(r"font-size:0(px|pt)?(;|$)", st):
        return True
    if re.search(r"(^|;)color:(#fff(fff)?|white)(;|$)", st):
        return not re.search(r"[\u3000-\u9fff\uff00-\uffef]", text_of(n))
    return False


def find_img(page: Path, node: Node):
    src = unquote(node.attrs.get("src", "").split("?")[0]).replace("\\", "/")
    if re.match(r"^[a-z]+://", src, re.I):
        return None
    ext = Path(src).suffix.lower()
    # broken saved names (`L&amp`, `x&amp(1).1]`): no real extension; accepted only if the file sniffs as an image
    broken = ext not in IMG_EXT and not re.fullmatch(r"\.[a-z0-9]{2,5}", ext) and bool(Path(src).name)
    if ext not in IMG_EXT and not broken:
        return None
    r = _find_img(page, src)
    if r is not None and broken and sniff(r) not in IMG_EXT:
        return None
    return r


def _find_img(page: Path, src: str):
    cands = [page.parent / src, page.with_suffix("").parent / (page.stem + "_files") / Path(src).name]
    for c in cands:
        if c.is_file():
            return c
    # file names whose non-ASCII part was decoded differently: match on the ASCII remainder
    key = re.sub(r"[^\x00-\x7f]", "", Path(src).name)
    if key and key != Path(src).name:
        own = [page.parent / Path(src).parent, cands[1].parent]
        fz = {f for d in own if d.is_dir() for f in d.iterdir()
              if f.is_file() and re.sub(r"[^\x00-\x7f]", "", f.name) == key}
        if len(fz) == 1:
            return fz.pop()
    # the saved *_files folder may have been renamed: accept a unique basename match in sibling folders
    hits = [f for d in page.parent.glob("*_files") for f in [d / Path(src).name] if f.is_file()]
    if len(hits) > 1 and len({h.read_bytes() for h in hits}) == 1:
        return hits[0]  # same file saved under several (renamed) folders
    if len(hits) == 1:
        return hits[0]
    if not hits:
        # folder saved without the `_files` suffix: same-prefix sibling folder (>= 6 chars shared)
        sf = Path(src).parent.name
        pre = [d for d in page.parent.iterdir() if d.is_dir() and not d.name.endswith("_files")
               and len(d.name) >= 6 and (sf.startswith(d.name[:6]) or d.name.startswith(sf[:6]) and sf)
               and d.name[:6] == (sf or page.stem)[:6]]
        hits = [d / Path(src).name for d in pre if (d / Path(src).name).is_file()]
        if len(hits) == 1:
            return hits[0]
    return None


def render(n: Node, page: Path, imgs: list) -> str:
    out = []
    for c in n.children:
        if isinstance(c, str):
            out.append(re.sub(r"[ \t\r\n 　]+", " ", c))
            continue
        if is_ad(c):
            # a font-size:0 wrapper does not hide an <img>: keep the pictures, drop the hidden text
            if re.search(r"font-size:0", c.attrs.get("style", "").replace(" ", "").lower()) \
                    and "display:none" not in c.attrs.get("style", "").replace(" ", "").lower():
                for im in c.walk():
                    if im.tag == "img":
                        p = find_img(page, im)
                        if p:
                            imgs.append(p)
                            out.append(f"{PH_L}{len(imgs) - 1}{PH_R}")
            continue
        if c.tag == "br":
            out.append("\n")
        elif c.tag == "img":
            p = find_img(page, c)
            if p:
                imgs.append(p)
                out.append(f"{PH_L}{len(imgs) - 1}{PH_R}")
            elif Path(unquote(c.attrs.get("src", "")).split("?")[0]).suffix.lower() in IMG_EXT:
                UNRESOLVED.append(c.attrs.get("src", ""))
                out.append("\n[image missing]\n")  # file not saved in the source
        else:
            blk = c.tag in BLOCK
            out.append("\n" if blk else "")
            out.append(render(c, page, imgs))
            out.append("\n" if blk else "")
    return "".join(out)


EDIT_STAMP = re.compile(r"\[\s*本帖最[后後]由[^\]\n]*?[于於][^\]\n]*?[编編][辑輯]\s*\]")
REPLY_NOTICE = re.compile(r"本帖[隐隱]藏的[内內]容需要[回]?[复復]才可以[浏瀏][览覽]")


SPAM_FORUM = re.compile(r"(?:ＭＣ军团（招財進寶）\[关闭注册\]\s*)?军团,\s*招财进宝,?\s*(?:华人[信性]息网站第一)?[!-~\u00a0 ]*")


def tidy(s: str) -> str:
    s, _ = clean(s)
    s = SPAM_FORUM.sub("", s)  # PROCESSING_RULES 4.1 variant 2
    s = EDIT_STAMP.sub("", s)
    s = REPLY_NOTICE.sub("", s)
    s = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
    s = re.sub(r"[\x1c-\x1f]", "\n", s)  # file/group/record/unit separators used as line breaks
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1b\x7f\ufffd]", "", s)
    s = s.replace("\u2028", "\n").replace("\u2029", "\n").replace("\u00a0", " ")
    lines = [re.sub(r" {2,}", " ", ln).strip() for ln in s.split("\n")]
    s = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def get_posts(root: Node, page: Path):
    posts = []
    for t in root.walk():
        if t.tag == "table" and re.match(r"pid\d+$", t.attrs.get("id", "")):
            author = next((re.sub(r"\s+", " ", text_of(c)).strip() for c in t.walk()
                           if c.tag == "cite"), "")
            body = next((c for c in t.walk() if "postmessage" in c.cls()), None)
            if body is None:  # older Discuz: pid table, body = div.t_msgfont / id=postmessage_N
                body = next((c for c in t.walk() if "t_msgfont" in c.cls()
                             or c.attrs.get("id", "").startswith("postmessage_")), None)
            imgs: list = []
            txt = tidy(render(body, page, imgs)) if body is not None else ""
            posts.append({"author": author, "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (k) Discuz poll/special threads: post tables carry no pid id; body = div.postmessage
    for t in root.walk():
        if t.tag == "div" and "postmessage" in t.cls():
            imgs = []
            posts.append({"author": "", "text": tidy(render(t, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # other layouts: (a) xici-style threads, one <td class="doc_txt"> per post
    for t in root.walk():
        if t.tag == "td" and "doc_txt" in t.cls():
            imgs = []
            posts.append({"author": "", "text": tidy(render(t, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (c) older Discuz: one <div class="t_msgfont"> per post
    for t in root.walk():
        if t.tag == "div" and "t_msgfont" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            # attachment lists sit beside (not inside) the message div
            tb = t.parent
            while tb is not None and tb.tag != "table":
                tb = tb.parent
            if tb is not None:
                inside = {id(x) for x in t.walk()}
                for at in tb.walk():
                    if at.tag == "div" and "t_attachlist" in at.cls() and id(at) not in inside:
                        txt = (txt + "\n" + tidy(render(at, page, imgs))).strip()
            posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (d) bt-download pages: the body is the first <td bgcolor=#ffffee colspan=2>
    for t in root.walk():
        if (t.tag == "td" and t.attrs.get("bgcolor", "").lower() == "#ffffee"
                and t.attrs.get("colspan") == "2"):
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
                break
    if posts:
        return posts
    # (e) PHPWind: <div id="read_tpc|read_NNN" class="tpc_content"> per post
    for t in root.walk():
        if t.tag == "div" and "tpc_content" in t.cls() and re.match(r"read_(tpc|\d+)$", t.attrs.get("id", "")):
            imgs = []
            posts.append({"author": "", "text": tidy(render(t, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (f) phpBB: <span class="postbody"> per post; author = last <span class="name">,
    #     date = last <span class="gensmall"> starting with 發表於
    author = date = ""
    for t in root.walk():
        if t.tag not in ("span", "td"):
            continue
        if t.tag == "span" and "name" in t.cls():
            author = re.sub(r"\s+", " ", text_of(t)).strip()
        elif "postbody" in t.cls():
            imgs = []
            posts.append({"author": f"{author} ({date})" if date else author,
                          "text": tidy(render(t, page, imgs)), "imgs": imgs})
        else:
            txt = re.sub(r"\s+", " ", text_of(t)).strip()
            m = re.match(r"發表於[:：]\s*(.*?)(?:\s*文章主題.*)?$", txt) if len(txt) < 100 else None
            if m:
                date = m.group(1)
    if posts:
        return posts
    # (g) vBulletin: <table id="postNNN">, author = a.bigusername, body = first td.alt1
    for t in root.walk():
        if t.tag == "table" and re.match(r"post\d+$", t.attrs.get("id", "")):
            author = next((re.sub(r"\s+", " ", text_of(c)).strip() for c in t.walk()
                           if c.tag == "a" and "bigusername" in c.cls()), "")
            body = next((c for c in t.walk() if c.tag == "td" and "alt1" in c.cls()), None)
            if body is not None:
                imgs = []
                posts.append({"author": author, "text": tidy(render(body, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (h) Qzone blog (<div id="blogDetailDiv">) and plain <div id="content"> pages (author = first p.author)
    for key in ("blogDetailDiv", "content"):
        for t in root.walk():
            if t.tag == "div" and t.attrs.get("id") == key:
                author = next((re.sub(r"\s+", " ", text_of(c)).strip() for c in t.walk()
                               if c.tag == "p" and "author" in c.cls()), "")
                imgs = []
                posts.append({"author": author, "text": tidy(render(t, page, imgs)), "imgs": imgs})
                break
        if posts:
            return posts
    # (q) crazys.net model pages, long form: every <td> whose <font> holds "<i>於 … 發表|回應</i>" is one post
    for t in root.walk():
        if t.tag == "td" and any(isinstance(c, Node) and c.tag == "font" and any(
                i.tag == "i" and re.search(r"於.{0,40}(發表|回應)", text_of(i)) for i in c.walk()) for c in t.children):
            author = next((re.sub(r"\s+", " ", text_of(c)).strip() for c in t.walk() if c.tag == "b"), "")
            imgs = []
            posts.append({"author": author, "text": tidy(render(t, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (i) crazys.net model pages: first <td> holding "<b>author</b> 於 ... 發表" is the primary post
    for t in root.walk():
        if t.tag == "td" and re.search(r"於.{0,40}發表", text_of(t)) and len(text_of(t)) < 200:
            author = next((re.sub(r"\s+", " ", text_of(c)).strip() for c in t.walk() if c.tag == "b"), "")
            imgs = []
            posts.append({"author": author, "text": tidy(render(t, page, imgs)), "imgs": imgs})
            break
    if posts:
        return posts
    # (j) tiexue (铁血) threads: one <td class="txt4"> per post
    for t in root.walk():
        if t.tag == "td" and "txt4" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (l) DCForum (myredbook): <a name=N><b>author</b></a> header row; body = td valign=top width=100%
    for t in root.walk():
        if t.tag == "a" and re.fullmatch(r"\d+", t.attrs.get("name", "")):
            author = re.sub(r"\s+", " ", text_of(t)).strip()
            tb = t.parent
            while tb is not None and tb.tag != "table":
                tb = tb.parent
            if tb is None:
                continue
            m = re.search(r"\d{1,2}-[A-Za-z]{3}-\d{2},\s*[\d:]+\s*[AP]M", re.sub(r"[\s\xa0]+", " ", text_of(tb)))
            body = next((c for c in tb.walk() if c.tag == "td" and c.attrs.get("width") == "100%"
                         and c.attrs.get("valign", "").lower() == "top"), None)
            if body is not None:
                imgs = []
                posts.append({"author": f"{author} ({m.group(0)})" if m else author,
                              "text": tidy(render(body, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (m) PHPWind variants without ids: <div class="tpc_content"> per post (yhsn.net)
    for t in root.walk():
        if t.tag in ("div", "span", "td") and "tpc_content" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (n) Dvbbs (assad.net.cn): body = <div id="textstyle_N">, author = last <span class="username">
    author = ""
    for t in root.walk():
        if t.tag == "span" and "username" in t.cls():
            author = re.sub(r"\s+", " ", text_of(t)).strip()
        elif t.tag == "div" and t.attrs.get("id", "").startswith("textstyle_"):
            imgs = []
            posts.append({"author": author, "text": tidy(render(t, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (o) mop.com (猫扑) threads: div.show_postor (author, date) followed by div.show_txt
    author = ""
    for t in root.walk():
        if t.tag == "div" and "show_postor" in t.cls():
            author = re.sub(r"\s+", " ", text_of(t)).strip()
            author = re.sub(r"\s*\[[^\]]*\]", "", author).strip()
        elif t.tag == "div" and "show_txt" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": author, "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (p) dtiblog category pages: one <div class="body"> per entry
    for t in root.walk():
        if t.tag == "div" and "body" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (r) tiexue variant: one <div class="main_body"> per post (a <div class="reply"> wraps a copy; skipped)
    for t in root.walk():
        if t.tag == "div" and "main_body" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (s) Blogger <div class="post-body"> per entry; WordPress <div class="content"> inside <div id="post-N">
    for t in root.walk():
        if t.tag == "div" and "post-body" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    for t in root.walk():
        if t.tag == "div" and re.match(r"post-\d+$", t.attrs.get("id", "")):
            body = next((c for c in t.walk() if c.tag == "div" and "content" in c.cls()), None)
            if body is not None:
                imgs = []
                txt = tidy(render(body, page, imgs))
                if txt or imgs:
                    posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (t) vBulletin-like without ids: <table class="posttable">, body = first td.alt1
    for t in root.walk():
        if t.tag == "table" and "posttable" in t.cls():
            body = next((c for c in t.walk() if c.tag == "td" and "alt1" in c.cls()), None)
            if body is not None:
                imgs = []
                txt = tidy(render(body, page, imgs))
                if txt or imgs:
                    posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (v) div.divBody blog posts (东莞厚街桑拿坐台小姐内部照片): the innermost divBody holding the pictures
    for t in root.walk():
        if t.tag == "div" and t.cls() == ["divBody"]:
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (w) old PlayChina/Discuz 2.x boards (GoChina sets): <a name=pidNNN> + table; the body is the
    #     <td valign=top> that holds <span class=bold><span class=smalltxt>subject</span></span>;
    #     author = first span.bold of the sibling author cell; the signature sits in another <tr>
    for t in root.walk():
        if t.tag == "td" and t.attrs.get("valign", "").lower() == "top" and any(
                isinstance(c, Node) and c.tag == "span" and "bold" in c.cls()
                and any(isinstance(g, Node) and g.tag == "span" and "smalltxt" in g.cls() for g in c.children)
                for c in t.children):
            author = ""
            inside = {id(x) for x in t.walk()}
            anc = t.parent
            while anc is not None and not author:
                if anc.tag == "tr":
                    for sp in anc.walk():
                        if sp.tag == "span" and "bold" in sp.cls() and id(sp) not in inside:
                            author = re.sub(r"\s+", " ", text_of(sp)).strip()
                            break
                anc = anc.parent
            imgs = []
            posts.append({"author": author, "text": tidy(render(t, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (x) vBulletin 2.x (gochina8 showthread.php): <td valign=top> whose first <p> holds "第N篇" (post number)
    #     and the subject; the following <p> elements are the body; author = first <b> of the sibling cell
    for t in root.walk():
        if t.tag != "td":
            continue
        ps = [c for c in t.children if isinstance(c, Node) and c.tag == "p"]
        if not ps or not re.search(r"第\s*\d+\s*篇", text_of(ps[0])):
            continue
        author = ""
        inside = {id(x) for x in t.walk()}
        anc = t.parent
        while anc is not None and not author:
            if anc.tag == "tr":
                for b in anc.walk():
                    if b.tag == "b" and id(b) not in inside:
                        author = re.sub(r"\s+", " ", text_of(b)).strip()
                        break
            anc = anc.parent
        imgs = []
        txt = tidy("\n".join(render(p, page, imgs) for p in ps[1:]))
        posts.append({"author": author, "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (y) LB5000 boards (topic.cgi: chinapapago, t-sucker, newchina169): a <td valign=top width=160> member cell
    #     (author = its first <b>, text has 總發言數/威望/頭銜) next to the body cell = the cell with the most text
    for t in root.walk():
        if (t.tag == "td" and t.attrs.get("valign", "").lower() == "top" and t.attrs.get("width", "").isdigit() and int(t.attrs["width"]) >= 150
                and re.search(r"發言數|威望|頭銜|总发言|头衔", text_of(t))):
            tb = t.parent
            while tb is not None and tb.tag != "table":
                tb = tb.parent
            if tb is None:
                continue
            inside = {id(x) for x in t.walk()}
            best, bestn = None, -1
            for td in tb.walk():
                if td.tag != "td" or id(td) in inside:
                    continue
                if any(isinstance(c, Node) and c.tag == "table" for c in td.children):
                    continue
                n = len(re.sub(r"\s+", "", text_of(td)))
                if n > bestn:
                    best, bestn = td, n
            author = next((re.sub(r"\s+", " ", text_of(b)).strip() for b in t.walk() if b.tag == "b"), "")
            if best is not None:
                imgs = []
                posts.append({"author": author, "text": tidy(render(best, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (z) phpBB 2.0.0 viewtopic (zh-family, chinacafe): one <tr> per post = author cell (註冊時間|Joined) + body cell
    for tr in root.walk():
        if tr.tag != "tr":
            continue
        tds = [c for c in tr.children if isinstance(c, Node) and c.tag == "td"]
        if len(tds) != 2 or not re.search(r"註冊時間|注册时间|Joined", text_of(tds[0])):
            continue
        if any(x.tag == "table" for c in tds for x in c.walk()):
            continue
        author = next((re.sub(r"\s+", " ", text_of(x)).strip() for x in tds[0].walk()
                       if x.tag in ("span", "b") and ("largetext" in x.cls() or x.tag == "b")), "")
        imgs = []
        posts.append({"author": author, "text": tidy(render(tds[1], page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (aa) TOM news article pages (news.tom.com): the article is the <td class="text"> with the most text
    cands = [t for t in root.walk() if t.tag == "td" and "text" in t.cls()]
    if cands and root.walk and any(t.tag == "div" and t.attrs.get("id") == "tomhead" for t in root.walk()):
        t = max(cands, key=lambda c: len(text_of(c)))
        imgs = []
        txt = tidy(render(t, page, imgs))
        if txt:
            posts.append({"author": "", "text": txt, "imgs": imgs})
        if posts:
            return posts
    # (ac) Discuz 4.x/5.x "altbg" boards (mcjt_old/mcjt_02/mcjt_html_04): one <tr> per post with two <td>:
    #      author cell (a.bold|span.bold + span.smalltxt user info) and the body cell
    for tr in root.walk():
        if tr.tag != "tr":
            continue
        tds = [c for c in tr.children if isinstance(c, Node) and c.tag == "td"]
        if len(tds) != 2:
            continue
        a = tds[0]
        bold = next((x for x in a.children if isinstance(x, Node) and x.tag in ("a", "span") and "bold" in x.cls()), None)
        if bold is None or not any(isinstance(x, Node) and x.tag == "span" and "smalltxt" in x.cls() for x in a.children):
            continue
        imgs = []
        posts.append({"author": re.sub(r"\s+", " ", text_of(bold)).strip(),
                      "text": tidy(render(tds[1], page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (ad) Tianya (天涯社区) threads: one <div class="post"> per post (replies included)
    for t in root.walk():
        if t.tag == "div" and "post" in t.cls() and not any(
                c.tag == "p" and c.attrs.get("id", "").startswith("post_content_") for c in t.walk()):
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (ae) forum pages with <div class="xcontent"> per post ("N楼 date 个人资料短消息…" header line)
    for t in root.walk():
        if t.tag == "div" and "xcontent" in t.cls():
            imgs = []
            txt = tidy(render(t, page, imgs))
            txt = re.sub(r"^\s*\d+楼[^\n]*?个人资料[^\n]*\n?", "", txt).strip()
            if txt:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (ab) old Baidu Tieba threads (tieba.baidu.com/f?kz=...): <div class=post> per floor; author = li.name,
    #      body = <p id=post_content_N> inside <td class=content> (the floor number sits in p.floor)
    for t in root.walk():
        if t.tag == "div" and "post" in t.cls():
            body = next((c for c in t.walk() if c.tag == "p" and c.attrs.get("id", "").startswith("post_content_")), None)
            if body is None:
                continue
            author = next((re.sub(r"\s+", " ", text_of(c)).strip() for c in t.walk()
                           if c.tag == "li" and "name" in c.cls()), "")
            imgs = []
            posts.append({"author": author, "text": tidy(render(body, page, imgs)), "imgs": imgs})
    if posts:
        return posts
    # (ag) Discuz 5.0 "t_msg" boards (2007 花王論壇 saves, Rewrap_MiscOld_II 15546/16081): no pid table ids;
    #      one <td class=line> per post that holds <a name=pidNNN> (rating link), the subject span.bold and the body
    for t in root.walk():
        if t.tag == "td" and "line" in t.cls() and any(
                c.tag == "a" and re.match(r"pid\d+$", c.attrs.get("name", "")) for c in t.walk()):
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (ai) newer Baidu Tieba threads (2013+ saves, 旅行记录/2018_SuZhou 睢宁吧): one <p class="d_post_content"
    #      id="post_content_N"> per floor, without the <div class=post> wrapper adapter (ab) needs
    for t in root.walk():
        if "d_post_content" in t.cls() and t.attrs.get("id", "").startswith("post_content_"):
            imgs = []
            txt = tidy(render(t, page, imgs))
            if txt or imgs:
                posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (aj) Soso Wenwen (搜搜问问) Q&A pages: question and every answer are the <pre> of a <div class="pump_con">
    for t in root.walk():
        if t.tag == "div" and "pump_con" in t.cls():
            for pre in (c for c in t.walk() if c.tag == "pre"):
                imgs = []
                txt = tidy(render(pre, page, imgs))
                if txt:
                    posts.append({"author": "", "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (ah) BMForum Datium (2005 songmen.cc 男人頌 saves, mc_2006_07_04 重慶… pages): body = <span class=javascript
    #      id=textNNN>; author = first <b> of the member cell (<td width=20%>) in the same row; the paid-post header
    #      "[付费 N 爽幣，已有 N 人购买]<select>…" at the top of the body is dropped
    for t in root.walk():
        if t.tag == "span" and "javascript" in t.cls() and re.match(r"text\d+$", t.attrs.get("id", "")):
            for s in [x for x in t.walk() if x.tag == "select"]:
                s.children = []
            author = ""
            anc = t.parent
            while anc is not None and anc.tag != "tr":
                anc = anc.parent
            while anc is not None and not author:
                if anc.tag == "tr":
                    cell = next((c for c in anc.children if isinstance(c, Node) and c.tag == "td"
                                 and c.attrs.get("width", "") == "20%"), None)
                    if cell is not None:
                        b = next((x for x in cell.walk() if x.tag == "b"), None)
                        author = re.sub(r"\s+", " ", text_of(b)).strip() if b is not None else ""
                anc = anc.parent
            imgs = []
            txt = tidy(render(t, page, imgs))
            txt = re.sub(r"^\s*\[[^\]\n]{0,30}爽幣[^\]\n]{0,30}\]\s*", "", txt)
            if txt or imgs:
                posts.append({"author": author, "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (ak) SMF 1.x boards (2006 7chinahappy.net/smf saves): one <td valign=top width="85%"> per post; its direct
    #      children are a subject table, <hr class=hrcolor>, then the body; <div class=signature> is dropped;
    #      author = first <b> of the member cell (the <td> before it in the same row)
    for t in root.walk():
        if t.tag != "td" or t.attrs.get("width", "") != "85%":
            continue
        kids = t.children
        hr = next((i for i, c in enumerate(kids) if isinstance(c, Node) and c.tag == "hr"
                   and "hrcolor" in c.cls()), None)
        if hr is None:
            continue
        body = Node("div")
        body.children = [c for c in kids[hr + 1:] if not (isinstance(c, Node) and (
            "signature" in c.cls() or c.tag == "hr"))]
        author = ""
        sibs = [c for c in (t.parent.children if t.parent else []) if isinstance(c, Node) and c.tag == "td"]
        if sibs and sibs[0] is not t:
            b = next((x for x in sibs[0].walk() if x.tag == "b"), None)
            author = re.sub(r"\s+", " ", text_of(b)).strip() if b is not None else ""
        imgs = []
        txt = tidy(render(body, page, imgs))
        if txt or imgs:
            posts.append({"author": author, "text": txt, "imgs": imgs})
    if posts:
        return posts
    # (al) MyRedBook classified ads (classified.php?adid=N saves, "<name> <phone> <city> Escort|AAMP.htm"):
    #      photos = <td class=classcat5> (img.mypic), text = the next <td class=classcat6> (title, by-line, fields,
    #      description); the sidebar "Ad of the Day" pictures are outside both cells
    for t in root.walk():
        if t.tag == "td" and "classcat5" in t.cls():
            sibs = [c for c in (t.parent.children if t.parent else []) if isinstance(c, Node) and c.tag == "td"]
            txtcell = next((c for c in sibs if "classcat6" in c.cls()), None)
            body = Node("div")
            body.children = ([txtcell] if txtcell is not None else []) + [t]
            by = next((x for x in (txtcell.walk() if txtcell is not None else []) if x.tag == "strong"), None)
            for tr in list(txtcell.walk() if txtcell is not None else []):  # field rows: label | : | value
                tds = [c for c in tr.children if isinstance(c, Node) and c.tag == "td"] if tr.tag == "tr" else []
                if len(tds) == 3 and text_of(tds[1]).replace("\xa0", "").strip() == ":":
                    lab = re.sub(r"\s+", " ", text_of(tds[0])).strip()
                    val = re.sub(r"\s+", " ", text_of(tds[2]).replace("\xa0", " ")).strip()
                    long = len(val) > 80 or any(x.tag == "br" for x in tds[2].walk())
                    tr.children = [] if not val else [f"{lab}:\n", tds[2]] if long else [f"{lab}: {val}"]
            imgs = []
            txt = tidy(render(body, page, imgs))
            if txt or imgs:
                posts.append({"author": re.sub(r"\s+", " ", text_of(by)).strip() if by is not None else "",
                              "text": txt, "imgs": imgs})
            break
    if posts:
        return posts
    # (am) MyRedBook photo pages ("<name> <adid> Photos …"): fields = <div class=myshow> (its "Links:" line of
    #      tineye/google search links dropped), photos = every img.mypic of the page
    show = next((t for t in root.walk() if t.tag == "div" and "myshow" in t.cls()), None)
    if show is not None:
        body = Node("div")
        for li in show.walk():
            if li.tag == "li" and "Links:" in text_of(li):
                li.children = []
        body.children = [show] + [t for t in root.walk() if t.tag == "img" and "mypic" in t.cls()]
        imgs = []
        txt = tidy(render(body, page, imgs))
        if txt or imgs:
            return [{"author": "", "text": txt, "imgs": imgs}]
    # (an) backpage.com ads: <div id=postingTitle> (h1), div.adInfo (date), ul#viewAdPhotoLayout (photos),
    #      div.postingBody, p.metaInfoDisplay (age) inside div.mainBody
    mb = next((t for t in root.walk() if t.tag == "div" and "mainBody" in t.cls()), None)
    if mb is not None and any(t.tag == "div" and "postingBody" in t.cls() for t in mb.walk()):
        keep = [t for t in mb.walk() if t.attrs.get("id") in ("postingTitle", "viewAdPhotoLayout")
                or any(k in t.cls() for k in ("adInfo", "postingBody", "metaInfoDisplay"))]
        for k in keep:
            for a in k.walk():
                if a.tag == "a" and "Report Ad" in text_of(a):
                    a.children = []
        body = Node("div")
        body.children = keep
        imgs = []
        txt = tidy(render(body, page, imgs))
        if txt or imgs:
            return [{"author": "", "text": txt, "imgs": imgs}]
    # (af) plain article pages with no forum markup (e.g. 医院性游记.HTM): the whole <body> is one post, but only
    #      when it holds >= 1500 CJK characters (stubs, error pages and Q&A snippets stay unsupported)
    body = next((t for t in root.walk() if t.tag == "body"), None)
    if body is not None:
        imgs = []
        txt = tidy(render(body, page, imgs))
        if len(re.findall(r"[㐀-鿿]", txt)) >= 1500:
            return [{"author": "", "text": txt, "imgs": imgs}]
    # (b) photo-album pages: the photos sit in <div class="phototable212"> blocks
    imgs, parts = [], []
    for t in root.walk():
        if "phototable212" in t.cls():
            parts.append(render(t, page, imgs))
    if imgs:
        txt = "\n".join(f"{PH_L}{i}{PH_R}" for i in range(len(imgs)))
        posts.append({"author": "", "text": txt, "imgs": imgs})
    return posts


def page_title(root: Node, fallback: str) -> str:
    for n in root.walk():
        if n.tag == "title":
            t = re.sub(r"\s+", " ", text_of(n)).strip()
            return re.split(r" - ◎", t)[0].strip() or fallback
    return fallback


def html_body(text: str, imgs: list, rel_for) -> str:
    parts = re.split(f"{PH_L}(\\d+){PH_R}", text)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 0:
            out.append(html.escape(p).replace("\n", "<br>\n"))
        else:
            out.append(f'<br><img src="{html.escape(rel_for(imgs[int(p)]), quote=True)}"><br>')
    r = "".join(out)
    r = re.sub(r"(?:<br>\s*){3,}", "<br>\n<br>\n", r)  # 4.4: stray <br> runs
    return re.sub(r"(?:<br>\s*)+$", "", r)


def sniff(p: Path) -> str:
    h = p.read_bytes()[:8]
    return (".jpg" if h[:2] == b"\xff\xd8" else ".png" if h[:4] == b"\x89PNG" else
            ".gif" if h[:3] == b"GIF" else ".bmp" if h[:2] == b"BM" else "")


def sweep_images(src: Path, outdir: Path):
    """Route every image file that no kept post used (loose folders, files with broken names,
    images only in dropped replies) into outputs/images.only/<folder>/ as x_<its folder name>_<file name> (flat).
    Also writes <folder>_images_manifest.csv: every file in the source with its status."""
    rows, base = [], outdir / "images.only" / src.name
    for f in sorted(x for x in src.rglob("*") if x.is_file() and x.name != ".DS_Store"):
        rel = str(f.relative_to(src))
        if f.suffix.lower() in (".htm", ".html"):
            continue
        if f in ROUTED:
            rows.append((rel, "copied: used by a saved post", str(ROUTED[f].relative_to(outdir))))
            continue
        if f.name.lower() == "thumbs.db":
            rows.append((rel, "skipped: Windows thumbnail cache", ""))
            continue
        ext = f.suffix.lower() if f.suffix.lower() in IMG_EXT else sniff(f)
        if not ext:
            rows.append((rel, "skipped: not an image", ""))
            continue
        leaf = f.name if f.suffix.lower() in IMG_EXT else f"{f.name}{ext}"
        dest, k = base / f"x_{f.parent.name[:30].strip()}_{leaf}", 1
        while dest in ROUTED.values():  # same short folder name + file name: keep both
            k += 1
            dest = base / f"x_{f.parent.name[:30].strip()}_{k}_{leaf}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size != f.stat().st_size:
            rows.append((rel, "ERROR: different file already at destination", str(dest.relative_to(outdir))))
            continue
        shutil.copy2(f, dest)
        ROUTED[f] = dest
        why = "unreferenced by any page" if f.suffix.lower() in IMG_EXT else "broken file name (type sniffed)"
        rows.append((rel, f"copied: {why}", str(dest.relative_to(outdir))))
    with open(outdir / f"{src.name}_images_manifest.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["source_file", "status", "output"])
        w.writerows(rows)


def process_folder(src: Path, outdir: Path):
    pages = sorted(p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in (".htm", ".html"))  # .HTM / .html too
    rows, img_dir = [], outdir / "images" / src.name
    for nn, page in enumerate(pages, 1):
        rel = page.relative_to(src)
        root = parse(decode_file(page))
        UNRESOLVED.clear()
        posts = get_posts(root, page)
        unres = len(UNRESOLVED)
        if not posts:
            rows.append((str(rel), "unsupported", 0, 0, 0, 0))
            continue
        title = re.split(r" - ◎| - Powered by", page.stem)[0].strip() or page.stem
        title = re.sub(r"(\s*-)+\s*$", "", SPAM_FORUM.sub("", title)).strip() or page.stem
        has_img = any(p["imgs"] for p in posts)
        if not has_img:
            dest = (outdir / "txt" / src.name / rel).with_suffix(".txt")
            dest.parent.mkdir(parents=True, exist_ok=True)
            p0 = posts[0]
            dest.write_text(f"{title}\n作者: {p0['author']}\n\n{p0['text']}\n", encoding="utf-8")
            rows.append((str(rel), "txt", len(posts), 1, 0, unres))
            continue
        keep = [(i, p) for i, p in enumerate(posts) if i == 0 or p["imgs"]]
        dest = (outdir / "reports" / src.name / rel).with_suffix(".html")
        dest.parent.mkdir(parents=True, exist_ok=True)
        img_dir.mkdir(parents=True, exist_ok=True)
        copied: dict = {}

        def rel_for(p: Path) -> str:
            if p not in copied:
                leaf = p.name if p.suffix.lower() in IMG_EXT else p.name + sniff(p)
                new, k = f"p{nn:03d}_{leaf}", 1
                while (img_dir / new).exists() and (img_dir / new) in ROUTED.values():
                    k += 1
                    new = f"p{nn:03d}_{k}_{leaf}"
                shutil.copy2(p, img_dir / new)
                copied[p] = img_dir / new
                ROUTED[p] = img_dir / new
            return os.path.relpath(copied[p], dest.parent).replace(os.sep, "/")

        sec = []
        for i, p in keep:
            label = "Primary post" if i == 0 else f"Reply #{i}"
            sec.append(f"<section><h3>{label} — {html.escape(p['author'])}</h3>\n"
                       f"{html_body(p['text'], p['imgs'], rel_for)}</section>")
        dest.write_text(
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title><style>body{{max-width:900px;margin:2em auto;"
            "font-family:sans-serif;line-height:1.6}img{max-width:100%}section{border-bottom:1px "
            "solid #ccc;padding-bottom:1em}</style></head><body>"
            f"<h1>{html.escape(title)}</h1>\n" + "\n".join(sec) + "</body></html>\n", encoding="utf-8")
        rows.append((str(rel), "html", len(posts), len(keep), len(copied), unres))
    sweep_images(src, outdir)
    with open(outdir / f"{src.name}_summary.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["page", "mode", "posts_in_page", "posts_saved", "images_copied", "unresolved_img_refs"])
        w.writerows(rows)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("outputs"))
    a = ap.parse_args()
    for s in a.folders:
        rows = process_folder(s, a.outdir)
        modes = {m: sum(1 for r in rows if r[1] == m) for m in ("html", "txt", "unsupported")}
        print(f"{s.name}: pages={len(rows)} {modes} images={sum(r[4] for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
