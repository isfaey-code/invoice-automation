"""
invoice_extractor.py
--------------------
Extract structured data from supplier invoice PDFs, validate it, and export
QuickBooks-ready CSV/JSON — with an exceptions queue for anything that fails a check.

Author: Isfaaq Ali
Usage:
    python src/invoice_extractor.py --input sample_invoices --output output
"""
import argparse
import csv
import json
import logging
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

import pdfplumber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("invoice_extractor")

# Field patterns support both French and English labels (bilingual suppliers).
PATTERNS = {
    "supplier":   r"(?:Fournisseur|Supplier)\s*[:\-]\s*(.+?)(?:\s+N°|\s+Invoice|\s*$)",
    "invoice_no": r"(?:N°?\s*de\s*facture|Invoice\s*(?:No|Number|#))\s*[:\-]\s*(\S+)",
    "date":       r"(?:Date)\s*[:\-]\s*([0-3]?\d[/\-.][0-1]?\d[/\-.]\d{2,4})",
    "amount_ht":  r"(?:Montant\s*HT|Subtotal|Total\s*HT)\s*[:\-]?\s*([\d\s.,]+)",
    "vat":        r"(?:TVA|VAT)\s*\(?\d*%?\)?\s*[:\-]?\s*([\d\s.,]+)",
    "amount_ttc": r"(?:Total\s*TTC|Total\s*Due|Grand\s*Total)\s*[:\-]?\s*([\d\s.,]+)",
}


@dataclass
class Invoice:
    source_file: str
    supplier: Optional[str] = None
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    amount_ht: Optional[float] = None
    vat: Optional[float] = None
    amount_ttc: Optional[float] = None
    status: str = "OK"
    issues: list = field(default_factory=list)


def _to_float(raw: str) -> Optional[float]:
    """Parse '1 234,56' / '1,234.56' / '120000' into a float."""
    if raw is None:
        return None
    s = raw.strip().replace(" ", "").replace(" ", "")
    if "," in s and "." in s:                      # 1,234.56 -> 1234.56
        s = s.replace(",", "")
    elif "," in s:                                  # 1234,56 -> 1234.56
        s = s.replace(",", ".")
    s = re.sub(r"[^\d.]", "", s)
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def extract(pdf_path: str) -> Invoice:
    inv = Invoice(source_file=os.path.basename(pdf_path))
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:                          # unreadable / corrupt / scanned-no-OCR
        inv.status = "EXCEPTION"
        inv.issues.append(f"Could not read PDF: {e}")
        return inv

    for field_name, pat in PATTERNS.items():
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            val = m.group(1).strip()
            if field_name in ("amount_ht", "vat", "amount_ttc"):
                setattr(inv, field_name, _to_float(val))
            else:
                setattr(inv, field_name, val)
    return inv


def validate(inv: Invoice, seen_invoice_nos: set) -> Invoice:
    """Business-rule checks. Anything that fails routes the invoice to the exceptions queue."""
    # 1. Required fields present
    for f in ("supplier", "invoice_no", "date", "amount_ht", "amount_ttc"):
        if getattr(inv, f) in (None, ""):
            inv.issues.append(f"Missing field: {f}")

    # 2. Date parses
    if inv.date:
        parsed = None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
            try:
                parsed = datetime.strptime(inv.date, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            inv.issues.append(f"Unparseable date: {inv.date}")
        else:
            inv.date = parsed.strftime("%Y-%m-%d")   # normalise to ISO for QuickBooks

    # 3. Totals reconcile: HT + VAT == TTC (1 cent tolerance)
    if None not in (inv.amount_ht, inv.vat, inv.amount_ttc):
        if abs((inv.amount_ht + inv.vat) - inv.amount_ttc) > 0.01:
            inv.issues.append(
                f"Totals do not reconcile: HT {inv.amount_ht} + VAT {inv.vat} "
                f"!= TTC {inv.amount_ttc}"
            )

    # 4. Duplicate detection
    if inv.invoice_no:
        if inv.invoice_no in seen_invoice_nos:
            inv.issues.append(f"Duplicate invoice number: {inv.invoice_no}")
        seen_invoice_nos.add(inv.invoice_no)

    inv.status = "EXCEPTION" if inv.issues else "OK"
    return inv


def process_folder(input_dir: str, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    pdfs = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(".pdf"))
    if not pdfs:
        log.warning("No PDF files found in %s", input_dir)
        return

    seen: set = set()
    clean, exceptions = [], []
    for name in pdfs:
        inv = validate(extract(os.path.join(input_dir, name)), seen)
        (clean if inv.status == "OK" else exceptions).append(inv)
        log.info("%-34s -> %s%s", name, inv.status,
                 f"  ({'; '.join(inv.issues)})" if inv.issues else "")

    _write_csv(os.path.join(output_dir, "invoices_for_quickbooks.csv"), clean)
    _write_csv(os.path.join(output_dir, "exceptions_to_review.csv"), exceptions)
    with open(os.path.join(output_dir, "invoices.json"), "w", encoding="utf-8") as fh:
        json.dump([asdict(i) for i in clean + exceptions], fh, ensure_ascii=False, indent=2)

    log.info("Done: %d ready for import, %d sent to exceptions queue.",
             len(clean), len(exceptions))


def _write_csv(path: str, invoices: list) -> None:
    cols = ["source_file", "supplier", "invoice_no", "date",
            "amount_ht", "vat", "amount_ttc", "status", "issues"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for inv in invoices:
            row = asdict(inv)
            row["issues"] = "; ".join(row["issues"])
            w.writerow([row[c] for c in cols])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Extract & validate supplier invoices from PDF.")
    ap.add_argument("--input", default="sample_invoices", help="Folder of PDF invoices")
    ap.add_argument("--output", default="output", help="Folder for CSV/JSON output")
    args = ap.parse_args()
    process_folder(args.input, args.output)
