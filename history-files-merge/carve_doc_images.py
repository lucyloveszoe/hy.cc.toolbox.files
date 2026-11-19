"""Carve embedded pictures (JPEG/PNG/GIF) out of a Word .doc binary, in file order."""
import re
import struct


def jpeg_end(d: bytes, i: int) -> int | None:
    """Walk JPEG segments from SOI at i; return index after EOI, or None if malformed."""
    p = i + 2
    n = len(d)
    while p + 4 <= n:
        if d[p] != 0xFF:
            return None
        m = d[p + 1]
        if m == 0xFF:
            p += 1
            continue
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            p += 2
            continue
        if m == 0xD9:
            return p + 2
        ln = struct.unpack(">H", d[p + 2:p + 4])[0]
        p += 2 + ln
        if m == 0xDA:  # entropy data until next real marker
            while p + 1 < n:
                if d[p] == 0xFF and d[p + 1] not in (0x00, 0xFF) and not 0xD0 <= d[p + 1] <= 0xD7:
                    break
                p += 1
    return None


def carve(d: bytes, min_jpeg: int = 2000):
    """Yield (ext, bytes) in file order. Nested thumbnails are skipped."""
    pos = 0
    pat = re.compile(rb"\xff\xd8\xff|\x89PNG\r\n\x1a\n|GIF8[79]a")
    while True:
        m = pat.search(d, pos)
        if not m:
            return
        i = m.start()
        sig = m.group()
        if sig.startswith(b"\xff\xd8"):
            e = jpeg_end(d, i)
            if e and e - i > min_jpeg:
                yield "jpg", d[i:e]
                pos = e
                continue
        elif sig.startswith(b"\x89PNG"):
            e = d.find(b"IEND", i)
            if e > 0:
                yield "png", d[i:e + 8]
                pos = e + 8
                continue
        else:
            e = d.find(b"\x00;", i)
            if e > 0 and e - i > 100:
                yield "gif", d[i:e + 2]
                pos = e + 2
                continue
        pos = i + 3
