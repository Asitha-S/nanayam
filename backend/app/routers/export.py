"""CA export (contract section 11). Routes are Asitha's; the real CSV/PDF builders are Charulatha's
backend/app/export/ module. STUB: CSV built from the ledger fixture, PDF is a one-line placeholder.
"""
import csv
import io
from datetime import date

from fastapi import APIRouter, Response

from ..stubs import fixture, require_merchant

router = APIRouter(tags=["export"])

CSV_COLUMNS = [
    "ledger_entry_id", "seq", "entry_type", "effective_at", "source_type", "source_id",
    "payer_or_description", "amount_rupees", "classification", "classification_source",
    "confidence", "expense_category", "supersedes_entry_id", "hash",
]


def _period(start_date: date | None, end_date: date | None) -> tuple[str, str]:
    s = fixture("summary_M001_after_confirm")["period"]
    return (start_date.isoformat() if start_date else s["start_date"], end_date.isoformat() if end_date else s["end_date"])


def _rupees(paise: int) -> str:
    return f"{paise // 100}.{paise % 100:02d}"


@router.get("/merchants/{merchant_id}/export/csv")
def export_csv(merchant_id: str, start_date: date | None = None, end_date: date | None = None):
    require_merchant(merchant_id)
    start, end = _period(start_date, end_date)
    summary = fixture("summary_M001_after_confirm")
    buf = io.StringIO()
    buf.write(f"# merchant: {merchant_id}\n# period: {start} to {end}\n# as_of: {summary['as_of']}\n")
    buf.write(f"# ledger_verify: {fixture('ledger_verify_valid')['status']}\n")
    buf.write(f"# {summary['scope_note']}\n# {summary['attribution_note']}\n# STUB EXPORT FROM FIXTURES\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for e in fixture("ledger_M001_2026-11-15")["items"]:
        writer.writerow([
            e["ledger_entry_id"], e["seq"], e["entry_type"], e["effective_at"], e["source_type"], e["source_id"],
            "", _rupees(e["amount_paise"]), e["classification"] or "", e["classification_source"] or "",
            "" if e["confidence"] is None else e["confidence"], e["expense_category"] or "",
            e["supersedes_entry_id"] or "", e["hash"],
        ])
    filename = f"naanayam_{merchant_id}_{start}_{end}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _placeholder_pdf(text: str) -> bytes:
    """A minimal valid one-page PDF (ASCII text only)."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 14 Tf 72 760 Td ({safe}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
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


@router.get("/merchants/{merchant_id}/export/pdf")
def export_pdf(merchant_id: str, start_date: date | None = None, end_date: date | None = None):
    require_merchant(merchant_id)
    start, end = _period(start_date, end_date)
    pdf = _placeholder_pdf(f"Naanayam CA pack (stub) - {merchant_id} - {start} to {end}")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="naanayam_{merchant_id}_{start}_{end}.pdf"'},
    )
