"""A minimal multi-page PDF writer (Helvetica, A4) so the CA pack needs no extra dependency.

The standard PDF fonts have no ₹ glyph: amounts are written "Rs 4,820" and the minus sign as "-". Text that the
fonts cannot show (e.g. Tamil) is replaced with "?"; the CA pack is English.
"""
from __future__ import annotations

import textwrap

PAGE_W, PAGE_H = 595, 842
MARGIN, LEADING = 50, 15
WRAP_CHARS = 95


def _pdf_text(s: str) -> str:
    s = s.replace("₹", "Rs ").replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class SimplePdf:
    def __init__(self, footer: str = ""):
        self.footer = footer
        self.pages: list[list[str]] = [[]]
        self.y = PAGE_H - MARGIN

    def _ensure(self, height: float) -> None:
        if self.y - height < MARGIN + 30:
            self.pages.append([])
            self.y = PAGE_H - MARGIN

    def line(self, text: str, *, bold: bool = False, size: int = 10, x: float = MARGIN) -> None:
        self._ensure(LEADING)
        font = "F2" if bold else "F1"
        self.pages[-1].append(f"BT /{font} {size} Tf {x:.0f} {self.y:.0f} Td ({_pdf_text(text)}) Tj ET")
        self.y -= LEADING + (size - 10)

    def row(self, label: str, value: str) -> None:
        self._ensure(LEADING)
        self.pages[-1].append(f"BT /F1 10 Tf {MARGIN} {self.y:.0f} Td ({_pdf_text(label)}) Tj ET")
        self.pages[-1].append(f"BT /F2 10 Tf {MARGIN + 260} {self.y:.0f} Td ({_pdf_text(value)}) Tj ET")
        self.y -= LEADING

    def wrapped(self, text: str) -> None:
        for part in textwrap.wrap(text, WRAP_CHARS) or [""]:
            self.line(part)

    def gap(self) -> None:
        self.y -= LEADING / 2

    def render(self) -> bytes:
        objects: list[bytes] = []
        n_pages = len(self.pages)
        # 1 catalog, 2 pages, 3 F1, 4 F2, then per page: page object, content stream
        page_ids = [5 + 2 * i for i in range(n_pages)]
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n_pages} >>".encode())
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        for i, ops in enumerate(self.pages):
            footer = f"BT /F1 8 Tf {MARGIN} 30 Td ({_pdf_text(f'{self.footer}    Page {i + 1} of {n_pages}')}) Tj ET"
            stream = "\n".join([*ops, footer]).encode("latin-1")
            objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                           f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>".encode())
            objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        out = bytearray(b"%PDF-1.4\n")
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
