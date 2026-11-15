"""A minimal multi-page PDF writer (A4) with embedded Noto Sans, so the CA pack shows "₹4,820".

Fonts: assets/fonts/NotoSans-{Regular,Bold}.ttf (SIL OFL 1.1). Each document embeds a subset with only the
characters it uses (fontTools), as a Type0 / CIDFontType2 font with Identity-H encoding and a ToUnicode map, so
the text can be copied and searched. Characters the font lacks (e.g. Tamil; the CA pack is English) become "?".
"""
from __future__ import annotations

import hashlib
import io
import logging
import textwrap
import zlib
from functools import lru_cache

from fontTools import subset
from fontTools.ttLib import TTFont

from ..config import REPO_ROOT

PAGE_W, PAGE_H = 595, 842
MARGIN, LEADING = 50, 15
WRAP_CHARS = 95
FONT_DIR = REPO_ROOT / "assets" / "fonts"
FONT_FILES = {"F1": "NotoSans-Regular.ttf", "F2": "NotoSans-Bold.ttf"}
STEM_V = {"F1": 80, "F2": 140}
logging.getLogger("fontTools").setLevel(logging.WARNING)  # subsetting logs every step at INFO


@lru_cache
def _font_bytes(name: str) -> bytes:
    return (FONT_DIR / name).read_bytes()


class _Font:
    """A subset of one Noto Sans weight for the characters of one document."""

    def __init__(self, key: str, chars: set[str]):
        full = TTFont(io.BytesIO(_font_bytes(FONT_FILES[key])))
        cmap_full = full.getBestCmap()
        wanted = {ord(c) for c in chars if ord(c) in cmap_full} | {ord("?"), ord(" ")}
        opts = subset.Options()
        opts.layout_features = []
        opts.hinting = False
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=wanted)
        sub.subset(full)
        buf = io.BytesIO()
        full.save(buf)
        self.data = buf.getvalue()
        self.font = TTFont(io.BytesIO(self.data))
        self.key = key
        self.cmap = self.font.getBestCmap()
        self.upem = self.font["head"].unitsPerEm
        tag = "".join(chr(65 + b % 26) for b in hashlib.sha256(self.data).digest()[:6])
        self.base_name = f"{tag}+{self.font['name'].getDebugName(6) or FONT_FILES[key][:-4]}"

    def gid(self, ch: str) -> int:
        name = self.cmap.get(ord(ch)) or self.cmap[ord("?")]
        return self.font.getGlyphID(name)

    def encode(self, text: str) -> str:
        return "".join(f"{self.gid(c):04X}" for c in text)

    def scale(self, v: float) -> int:
        return round(v * 1000 / self.upem)

    def objects(self, first_id: int) -> tuple[list[bytes], int]:
        """PDF objects (Type0, CIDFont, descriptor, font file, ToUnicode) starting at first_id; returns (objs, type0 id)."""
        t0, cid, desc, ff, tu = range(first_id, first_id + 5)
        hmtx = self.font["hmtx"]
        widths = " ".join(f"{self.font.getGlyphID(g)} [{self.scale(hmtx[g][0])}]"
                          for g in sorted(set(self.cmap.values()), key=self.font.getGlyphID))
        head, hhea, os2 = self.font["head"], self.font["hhea"], self.font["OS/2"]
        bbox = " ".join(str(self.scale(v)) for v in (head.xMin, head.yMin, head.xMax, head.yMax))
        cap = self.scale(getattr(os2, "sCapHeight", 0) or hhea.ascent)
        to_unicode = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
                      "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
                      "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def",
                      "1 begincodespacerange <0000> <FFFF> endcodespacerange"]
        pairs = sorted((self.font.getGlyphID(g), cp) for cp, g in self.cmap.items())
        for i in range(0, len(pairs), 100):
            chunk = pairs[i:i + 100]
            to_unicode.append(f"{len(chunk)} beginbfchar")
            to_unicode += [f"<{g:04X}> <{chr(cp).encode('utf-16-be').hex().upper()}>" for g, cp in chunk]
            to_unicode.append("endbfchar")
        to_unicode += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
        tu_stream = "\n".join(to_unicode).encode("ascii")
        font_file = zlib.compress(self.data)
        objs = [
            f"<< /Type /Font /Subtype /Type0 /BaseFont /{self.base_name} /Encoding /Identity-H "
            f"/DescendantFonts [{cid} 0 R] /ToUnicode {tu} 0 R >>".encode(),
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{self.base_name} "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor {desc} 0 R "
            f"/CIDToGIDMap /Identity /W [{widths}] >>".encode(),
            f"<< /Type /FontDescriptor /FontName /{self.base_name} /Flags 32 /FontBBox [{bbox}] /ItalicAngle 0 "
            f"/Ascent {self.scale(hhea.ascent)} /Descent {self.scale(hhea.descent)} /CapHeight {cap} "
            f"/StemV {STEM_V[self.key]} /FontFile2 {ff} 0 R >>".encode(),
            b"<< /Length " + str(len(font_file)).encode() + b" /Length1 " + str(len(self.data)).encode()
            + b" /Filter /FlateDecode >>\nstream\n" + font_file + b"\nendstream",
            b"<< /Length " + str(len(tu_stream)).encode() + b" >>\nstream\n" + tu_stream + b"\nendstream",
        ]
        return objs, t0


class SimplePdf:
    def __init__(self, footer: str = ""):
        self.footer = footer
        self.pages: list[list[tuple[str, int, float, float, str]]] = [[]]  # (font, size, x, y, text)
        self.y = PAGE_H - MARGIN

    def _ensure(self, height: float) -> None:
        if self.y - height < MARGIN + 30:
            self.pages.append([])
            self.y = PAGE_H - MARGIN

    def line(self, text: str, *, bold: bool = False, size: int = 10, x: float = MARGIN) -> None:
        self._ensure(LEADING)
        self.pages[-1].append(("F2" if bold else "F1", size, x, self.y, text))
        self.y -= LEADING + (size - 10)

    def row(self, label: str, value: str) -> None:
        self._ensure(LEADING)
        self.pages[-1].append(("F1", 10, MARGIN, self.y, label))
        self.pages[-1].append(("F2", 10, MARGIN + 260, self.y, value))
        self.y -= LEADING

    def wrapped(self, text: str) -> None:
        for part in textwrap.wrap(text, WRAP_CHARS) or [""]:
            self.line(part)

    def gap(self) -> None:
        self.y -= LEADING / 2

    def render(self) -> bytes:
        n_pages = len(self.pages)
        pages = [ops + [("F1", 8, MARGIN, 30, f"{self.footer}    Page {i + 1} of {n_pages}")]
                 for i, ops in enumerate(self.pages)]
        fonts = {k: _Font(k, {c for ops in pages for f, _, _, _, t in ops if f == k for c in t}) for k in FONT_FILES}
        objects: list[bytes] = [b"", b""]  # 1 catalog, 2 pages: filled below
        font_refs = {}
        for k, font in fonts.items():
            objs, t0 = font.objects(len(objects) + 1)
            objects += objs
            font_refs[k] = t0
        resources = " ".join(f"/{k} {ref} 0 R" for k, ref in font_refs.items())
        page_ids = []
        for ops in pages:
            stream = "\n".join(f"BT /{f} {size} Tf {x:.0f} {y:.0f} Td <{fonts[f].encode(t)}> Tj ET"
                               for f, size, x, y, t in ops).encode("ascii")
            page_id = len(objects) + 1
            page_ids.append(page_id)
            objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                           f"/Resources << /Font << {resources} >> >> /Contents {page_id + 1} 0 R >>".encode())
            objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n_pages} >>".encode()
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)
