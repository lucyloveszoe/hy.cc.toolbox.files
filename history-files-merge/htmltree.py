"""Tiny lenient DOM built on stdlib html.parser (no third-party deps)."""
import re
from html.parser import HTMLParser

VOID = {"br", "img", "hr", "input", "meta", "link", "area", "base", "col", "param", "embed", "wbr"}
SKIP = {"script", "style"}


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs or {}), parent, []

    def cls(self):
        return (self.attrs.get("class") or "").split()

    def walk(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.walk()


class _B(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.cur = self.root
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        n = Node(tag, [(k, v or "") for k, v in attrs], self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        if tag in SKIP:
            return
        self.cur.children.append(Node(tag, [(k, v or "") for k, v in attrs], self.cur))

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, d):
        if not self.skip:
            self.cur.children.append(d)


def parse(html: str) -> Node:
    b = _B()
    b.feed(html)
    b.close()
    return b.root


def decode_file(path) -> str:
    raw = open(path, "rb").read()
    m = re.search(rb"charset=[\"']?([\w-]+)", raw[:4000], re.I)
    cs = m.group(1).decode().lower() if m else "gb18030"
    cs = {"gb2312": "gb18030", "gbk": "gb18030", "x-gbk": "gb18030", "big5": "big5hkscs"}.get(cs, cs)
    if cs in ("windows-1252", "iso-8859-1", "latin1", "us-ascii"):
        # pages saved with a wrong western charset declaration: use big5 / gbk when the bytes decode strictly
        for alt in ("big5hkscs", "gb18030"):
            t = raw.decode(alt, "replace")
            cjk = sum("\u4e00" <= ch <= "\u9fff" for ch in t)
            if cjk > 20 and t.count("\ufffd") < cjk * 0.02:
                return t
    try:
        return raw.decode(cs, "replace")
    except LookupError:
        return raw.decode("gb18030", "replace")
