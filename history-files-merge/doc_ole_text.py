r"""Fallback reader for Word 97-2003 .doc files that macOS textutil refuses ("not in the correct format").

read_text(path) -> text in textutil-like form: paragraph marks -> newline, field codes kept as text
(INCLUDEPICTURE "url" ... MERGEFORMATINET), and every picture that is NOT already the cached result of
an INCLUDEPICTURE field gets a synthetic field `INCLUDEPICTURE "inline:N" \* MERGEFORMATINET`, so doc_to_html.process() turns
all pictures into ordered marks. Pictures: read_doc() returns them 1:1 with the marks, found through each anchor's sprmCPicLocation (Data stream offset).
Standard library only. Handles the main document text only (not headers/footnotes).
"""
import re
import struct
class CFB:
    def __init__(s,path):
        d=s.d=open(path,'rb').read()
        assert d[:8]==bytes.fromhex('d0cf11e0a1b11ae1')
        s.ss=1<<struct.unpack('<H',d[30:32])[0]; s.mss=1<<struct.unpack('<H',d[32:34])[0]
        nfat,dirstart,_,cutoff,minifat,nminifat,difat,ndifat=struct.unpack('<IIIIIIII',d[44:76])
        s.cutoff=cutoff
        sec=lambda i:d[(i+1)*s.ss:(i+2)*s.ss]
        difl=list(struct.unpack('<109I',d[76:512]))
        x=difat
        for _ in range(ndifat):
            b=sec(x); v=struct.unpack('<%dI'%(s.ss//4),b); difl+=v[:-1]; x=v[-1]
        fat=[]
        for i in difl[:nfat]: fat+=struct.unpack('<%dI'%(s.ss//4),sec(i))
        s.fat=fat; s.sec=sec
        s.chain=lambda st:s._chain(st)
        dd=s.read_chain(dirstart)
        s.ents=[]
        for i in range(0,len(dd),128):
            e=dd[i:i+128]; n=struct.unpack('<H',e[64:66])[0]
            name=e[:max(n-2,0)].decode('utf-16le','replace'); typ=e[66]
            st,size=struct.unpack('<IQ',e[116:128]); s.ents.append((name,typ,st,size))
        s.minifat=[]
        if minifat<0xFFFFFFF0:
            mb=s.read_chain(minifat); s.minifat=list(struct.unpack('<%dI'%(len(mb)//4),mb))
        s.ministream=s.read_chain(s.ents[0][2])[:s.ents[0][3]] if s.minifat else b''
    def _chain(s,st):
        out=[];seen=set()
        while st<0xFFFFFFF0 and st not in seen:
            seen.add(st);out.append(st);st=s.fat[st]
        return out
    def read_chain(s,st): return b''.join(s.sec(i) for i in s._chain(st))
    def stream(s,name):
        for n,t,st,size in s.ents:
            if n==name and t==2:
                if size<s.cutoff:
                    out=b'';seen=set()
                    while st<0xFFFFFFF0 and st not in seen:
                        seen.add(st);out+=s.ministream[st*s.mss:(st+1)*s.mss];st=s.minifat[st]
                    return out[:size]
                return s.read_chain(st)[:size]


SPRA = {0: 1, 1: 1, 2: 2, 3: 4, 4: 2, 5: 2, 7: 3}


def _pic_offset(grpprl: bytes):
    """sprmCPicLocation (0x6A03) operand from a CHPX grpprl, or None."""
    i = 0
    while i + 2 <= len(grpprl):
        op = struct.unpack("<H", grpprl[i:i + 2])[0]
        spra = op >> 13
        i += 2
        if spra == 6:
            if i >= len(grpprl):
                break
            n = grpprl[i]
            val, i = grpprl[i + 1:i + 1 + n], i + 1 + n
        else:
            n = SPRA[spra]
            val, i = grpprl[i:i + n], i + n
        if op == 0x6A03 and len(val) == 4:
            return struct.unpack("<i", val)[0]
    return None


def read_doc(path):
    """-> (text, pics). pics[k] = (ext, bytes) for the k-th INCLUDEPICTURE mark in the text."""
    from bisect import bisect_right
    from carve_doc_images import carve
    c = CFB(str(path))
    w = c.stream("WordDocument")
    data = c.stream("Data") or b""
    wid, nfib = struct.unpack("<HH", w[:4])
    if wid != 0xA5EC:
        raise ValueError("not a Word 97+ document")
    flags = struct.unpack("<H", w[10:12])[0]
    t = c.stream("1Table" if flags & 0x200 else "0Table")
    ccp_text = struct.unpack("<I", w[0x4C:0x50])[0]
    fc_clx, lcb_clx = struct.unpack("<II", w[0x1A2:0x1AA])
    clx = t[fc_clx:fc_clx + lcb_clx]
    i = 0
    while clx[i] == 1:
        i += 3 + struct.unpack("<H", clx[i + 1:i + 3])[0]
    lcb = struct.unpack("<I", clx[i + 1:i + 5])[0]
    plc = clx[i + 5:i + 5 + lcb]
    n = (lcb - 4) // 12
    cps = struct.unpack("<%dI" % (n + 1), plc[:4 * (n + 1)])
    pieces, out = [], []  # (cp_start, cp_end, fc_byte_start, bytes_per_char)
    for k in range(n):
        a, b = cps[k], min(cps[k + 1], ccp_text)
        if a >= ccp_text:
            break
        fc = struct.unpack("<I", plc[4 * (n + 1) + 8 * k + 2:4 * (n + 1) + 8 * k + 6])[0]
        if fc & 0x40000000:
            off = (fc & 0x3FFFFFFF) // 2
            pieces.append((a, b, off, 1))
            out.append(w[off:off + (b - a)].decode("cp1252", "replace"))
        else:
            pieces.append((a, b, fc, 2))
            out.append(w[fc:fc + 2 * (b - a)].decode("utf-16le", "replace"))
    raw = "".join(out)
    starts = [p[0] for p in pieces]

    def cp_to_fc(cp):
        p = pieces[bisect_right(starts, cp) - 1]
        return p[2] + (cp - p[0]) * p[3]

    fc_bte, lcb_bte = struct.unpack("<II", w[0xFA:0x102])
    bte = t[fc_bte:fc_bte + lcb_bte]
    nb = (lcb_bte - 4) // 8
    bfcs = struct.unpack("<%dI" % (nb + 1), bte[:4 * (nb + 1)])
    bpns = struct.unpack("<%dI" % nb, bte[4 * (nb + 1):4 * (nb + 1) + 4 * nb])
    fkp_cache = {}

    def pic_loc(fc):
        j = bisect_right(bfcs, fc) - 1
        if not 0 <= j < nb:
            return None
        pn = bpns[j]
        if pn not in fkp_cache:
            pg = w[pn * 512:pn * 512 + 512]
            cr = pg[511]
            fcs = struct.unpack("<%dI" % (cr + 1), pg[:4 * (cr + 1)])
            fkp_cache[pn] = (pg, cr, fcs)
        pg, cr, fcs = fkp_cache[pn]
        r = bisect_right(fcs, fc) - 1
        if not 0 <= r < cr:
            return None
        o = pg[4 * (cr + 1) + r] * 2
        if o == 0:
            return None
        cb = pg[o]
        return _pic_offset(pg[o + 1:o + 1 + cb])

    def picture(cp):
        off = pic_loc(cp_to_fc(cp))
        if off is None or off < 0 or off + 68 > len(data):
            return None
        lcb_p, cbh = struct.unpack("<IH", data[off:off + 6])
        if not 0x44 <= cbh <= 0x100 or off + lcb_p > len(data):
            return None
        return next(carve(data[off + cbh:off + lcb_p] + b"\x00" * 8, min_jpeg=100), None)  # pad: jpeg_end needs look-ahead

    top, stack, pics, inline = [], [], [], 0

    def emit(x):
        (stack[-1]["res"] if stack[-1]["in_result"] else stack[-1]["code"]).append(x) if stack else top.append(x)

    for cp, ch in enumerate(raw):
        if ch == "\x13":
            stack.append({"code": [], "res": [], "in_result": False, "pic": False, "anchors": []})
        elif ch == "\x14" and stack:
            f = stack[-1]
            f["in_result"] = True
            f["pic"] = "INCLUDEPICTURE" in "".join(f["code"])
        elif ch == "\x15" and stack:
            f = stack.pop()
            code, resu = "".join(f["code"]), "".join(f["res"])
            if f["pic"]:
                pic = next((q for q in map(picture, f["anchors"]) if q), None)
                if pic:
                    pics.append(pic)
                    emit(code.strip())
                else:
                    emit(" [image missing] ")
            else:
                emit(code + resu)
        elif ch == "\x01":
            owner = next((f for f in reversed(stack) if f["pic"] and f["in_result"]), None)
            if owner is not None:
                owner["anchors"].append(cp)
            else:
                pic = picture(cp)
                if pic:
                    pics.append(pic)
                    inline += 1
                    emit(f' INCLUDEPICTURE "inline:{inline}" \\* MERGEFORMATINET ')
        else:
            emit(ch)
    while stack:
        f = stack.pop()
        emit("".join(f["code"]) + "".join(f["res"]))
    text = "".join(top)
    text = text.replace("\r", "\n").replace("\x07", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    return text, pics


def read_text(path) -> str:
    return read_doc(path)[0]
