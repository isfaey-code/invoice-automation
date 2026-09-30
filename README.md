# Invoice Automation — PDF → Validation → QuickBooks

A Python pipeline that extracts data from supplier invoice PDFs, validates it against
business rules, and produces **QuickBooks-ready output** — routing anything suspect to an
**exceptions queue** instead of importing bad data.

Built to eliminate manual invoice entry while keeping a human in the loop only for the
cases that genuinely need review.

---

## Why it exists

Manually keying supplier invoices into QuickBooks is slow and error-prone. This tool reads
the PDFs, pulls the key fields, checks them, and hands back a clean file to import — plus a
separate list of invoices that failed a check and need a look.

It handles **both French and English** invoice layouts (e.g. `Fournisseur` / `Supplier`,
`Montant HT` / `Subtotal`, `Total TTC` / `Total Due`).

---

## What it does

| Stage | Detail |
|-------|--------|
| **Extract** | Reads each PDF with `pdfplumber` and pulls supplier, invoice number, date, amount HT, VAT, and total TTC. |
| **Validate** | Required fields present · date parses (normalised to ISO `YYYY-MM-DD`) · **HT + VAT = TTC** reconciliation · **duplicate invoice-number** detection. |
| **Route** | Clean invoices → `invoices_for_quickbooks.csv`. Anything that fails a check → `exceptions_to_review.csv`, with the reason. |
| **Export** | CSV (for QuickBooks import) and JSON (for downstream use), plus a full processing log. |

---

## Example run

```
facture_ABC_2024-001.pdf           -> OK
facture_Doublon_2024-001.pdf       -> EXCEPTION  (Duplicate invoice number: 2024-001)
facture_Erreur_totaux.pdf          -> EXCEPTION  (Totals do not reconcile: HT 60000 + VAT 9000 != TTC 99999)
facture_OfficeMax_OM-9931.pdf      -> OK
facture_TechPro_INV-5582.pdf       -> OK
Done: 3 ready for import, 2 sent to exceptions queue.
```

**Clean output** (`invoices_for_quickbooks.csv`):

| supplier | invoice_no | date | amount_ht | vat | amount_ttc | status |
|----------|-----------|------|-----------|-----|------------|--------|
| ABC Fournitures SARL | 2024-001 | 2024-01-15 | 79000.00 | 11850.00 | 90850.00 | OK |
| TechPro Solutions Ltd | INV-5582 | 2024-02-03 | 165000.00 | 24750.00 | 189750.00 | OK |

**Exceptions queue** (`exceptions_to_review.csv`) captures the duplicate and the mismatched totals with reasons.

---

## Quick start

```bash
pip install -r requirements.txt

# (optional) regenerate the sample invoices
python src/generate_samples.py

# run the pipeline
python src/invoice_extractor.py --input sample_invoices --output output
```

Outputs land in `output/`.

---

## How QA / testing is handled

- **Reconciliation check** on every invoice (`HT + VAT = TTC`, 1-cent tolerance) — the single
  most effective guard against extraction errors.
- **Duplicate detection** so the same invoice can't be imported twice.
- **Fail-safe routing**: an invoice that fails *any* check is never written to the import file —
  it goes to the exceptions queue with the reason, so bad data can't reach QuickBooks.
- **Deterministic sample set** (`generate_samples.py`) includes deliberately broken invoices
  (wrong totals, duplicate number) so the validation layer is testable and repeatable.

---

## Roadmap (production build)

- **Direct QuickBooks Online import** via the QBO API (Bills), with supplier / expense-account
  / tax-code mapping.
- **OCR** (Tesseract) for scanned, image-only invoices.
- **Watched folder / email inbox** trigger for hands-off daily processing.
- Configurable per-supplier field templates.

---

## Tech

Python · pdfplumber · pandas · (QuickBooks Online API for the production import stage)
