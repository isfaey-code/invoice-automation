"""
Generate realistic sample supplier invoices (PDF) for demo/testing.
These stand in for the real supplier PDFs the pipeline will process.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "sample_invoices")
os.makedirs(OUT, exist_ok=True)
styles = getSampleStyleSheet()

def money(x): return f"{x:,.2f}".replace(",", " ")

def build(fname, supplier, inv_no, date, lines, vat_rate=0.15, force_ttc=None):
    ht = sum(q * pu for _, q, pu in lines)
    tva = round(ht * vat_rate, 2)
    ttc = force_ttc if force_ttc is not None else round(ht + tva, 2)
    doc = SimpleDocTemplate(os.path.join(OUT, fname), pagesize=A4,
                            topMargin=20*mm, bottomMargin=20*mm)
    el = []
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=22, textColor=colors.HexColor("#1F3864"))
    el.append(Paragraph("FACTURE", title))
    el.append(Spacer(1, 6*mm))
    meta = [
        [f"Fournisseur : {supplier}", f"N° de facture : {inv_no}"],
        ["", f"Date : {date}"],
    ]
    mt = Table(meta, colWidths=[95*mm, 75*mm])
    mt.setStyle(TableStyle([("FONTSIZE",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
    el.append(mt); el.append(Spacer(1, 8*mm))
    data = [["Description", "Qté", "Prix unitaire", "Montant"]]
    for desc, q, pu in lines:
        data.append([desc, str(q), money(pu), money(q*pu)])
    data += [["", "", "Montant HT", money(ht)],
             ["", "", f"TVA ({int(vat_rate*100)}%)", money(tva)],
             ["", "", "Total TTC", money(ttc)]]
    t = Table(data, colWidths=[85*mm, 20*mm, 35*mm, 30*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F3864")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("ALIGN",(1,0),(-1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-4),0.4,colors.grey),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("FONTNAME",(2,-1),(3,-1),"Helvetica-Bold"),
        ("LINEABOVE",(2,-3),(3,-3),0.5,colors.grey),
    ]))
    el.append(t)
    doc.build(el)
    print("wrote", fname, "| HT", ht, "TVA", tva, "TTC", ttc)

build("facture_ABC_2024-001.pdf", "ABC Fournitures SARL", "2024-001", "15/01/2024",
      [("Papier A4 (carton)", 10, 4500), ("Cartouches d'encre", 4, 8500)])
build("facture_TechPro_INV-5582.pdf", "TechPro Solutions Ltd", "INV-5582", "03/02/2024",
      [("Licence logiciel comptable", 1, 120000), ("Support technique annuel", 1, 45000)])
build("facture_OfficeMax_OM-9931.pdf", "OfficeMax Maurice", "OM-9931", "28/02/2024",
      [("Mobilier de bureau", 3, 22000), ("Chaises ergonomiques", 6, 9500), ("Lampes LED", 8, 1800)])

# --- Cas de test QA : déclenchent la file d'exceptions ---
# Totaux incohérents (TTC erroné) -> échoue au contrôle de réconciliation
build("facture_Erreur_totaux.pdf", "Global Supplies Co", "GS-7788", "10/03/2024",
      [("Matériel divers", 5, 12000)], force_ttc=99999.00)
# Doublon : même numéro de facture que ABC 2024-001 -> détection de doublon
build("facture_Doublon_2024-001.pdf", "ABC Fournitures SARL", "2024-001", "15/01/2024",
      [("Papier A4 (carton)", 10, 4500), ("Cartouches d'encre", 4, 8500)])
