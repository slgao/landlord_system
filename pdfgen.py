#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : pdfgen.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 18:21:21
#   Description :
#
# ================================================================

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from datetime import date, timedelta
from pathlib import Path

PDF_DIR = Path("pdf")
PAGE_W = A4[0]

# ── Shared styles ──────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    s = {}
    s["normal"] = ParagraphStyle("normal", fontName="Helvetica", fontSize=10, leading=15)
    s["small"]  = ParagraphStyle("small",  fontName="Helvetica", fontSize=8,  leading=12, textColor=colors.grey)
    s["bold"]   = ParagraphStyle("bold",   fontName="Helvetica-Bold", fontSize=10, leading=15)
    s["title"]  = ParagraphStyle("title",  fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=4)
    s["right"]  = ParagraphStyle("right",  fontName="Helvetica", fontSize=10, leading=15, alignment=TA_RIGHT)
    s["section"]= ParagraphStyle("section",fontName="Helvetica-Bold", fontSize=11, leading=16,
                                  textColor=colors.HexColor("#1a3a5c"), spaceBefore=10, spaceAfter=4)
    return s


def _salutation(gender, name):
    if gender == "male":
        return f"Sehr geehrter Herr {name},"
    elif gender == "female":
        return f"Sehr geehrte Frau {name},"
    else:
        return f"Sehr geehrte/r {name},"


def _calc_table(data, col_widths):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f0f4f8")]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN",       (2, 0), (2, -1),  "RIGHT"),
        ("ALIGN",       (1, 0), (1, -1),  "LEFT"),
        ("FONTNAME",    (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND",  (0, -1), (-1, -1), colors.HexColor("#dce8f5")),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _total_table(strom_nach, bk_nach, total, s):
    color = colors.HexColor("#c0392b") if total > 0 else colors.HexColor("#27ae60")
    data = [
        ["", "Nachzahlung Strom",        f"{strom_nach:.2f} €"],
        ["", "Nachzahlung Betriebskosten", f"{bk_nach:.2f} €"],
        ["▶", "Gesamtbetrag nachzuzahlen", f"{total:.2f} €"],
    ]
    t = Table(data, colWidths=[14, 380, 90])
    t.setStyle(TableStyle([
        ("FONTSIZE",    (0, 0), (-1, -1), 10),
        ("ALIGN",       (2, 0), (2, -1),  "RIGHT"),
        ("LINEABOVE",   (0, -1), (-1, -1), 1, colors.HexColor("#cccccc")),
        ("FONTNAME",    (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",   (0, -1), (-1, -1), color),
        ("FONTSIZE",    (0, -1), (-1, -1), 11),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    return t


# ── Nebenkostenabrechnung ──────────────────────────────────────────────────────

def invoice_pdf(
    tenant,
    address,
    strom_period,
    strom_days,
    strom_cost,
    strom_limit,
    strom_nach,
    bk_period,
    bk_months,
    bk_cost,
    bk_limit,
    bk_nach,
    landlord_name="Ihr Vermieter",
    num_tenants=1,
    monthly_strom_limit=0,
    monthly_bk_limit=0,
    gender="diverse",
):
    s = _styles()
    file = f"pdf/Abrechnung_{tenant}.pdf"
    story = []
    today_str = date.today().strftime("%d.%m.%Y")
    total = strom_nach + bk_nach

    # ── Header bar (sender right, recipient left) ──────────────────
    sender_lines = [Paragraph(f"<b>{landlord_name}</b>", s["right"]),
                    Paragraph(today_str, s["right"])]

    recipient_lines = [Paragraph(f"<b>{tenant}</b>", s["normal"])]
    if address:
        for line in address.replace(",", "\n").split("\n"):
            l = line.strip()
            if l:
                recipient_lines.append(Paragraph(l, s["normal"]))

    header_table = Table(
        [[recipient_lines, sender_lines]],
        colWidths=[280, 200]
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a3a5c")))
    story.append(Spacer(1, 10))

    # ── Title + subject ────────────────────────────────────────────
    story.append(Paragraph("Nebenkostenabrechnung", s["title"]))
    story.append(Paragraph(f"Abrechnungszeitraum Strom: {strom_period} &nbsp;|&nbsp; Betriebskosten: {bk_period}", s["small"]))
    story.append(Spacer(1, 18))

    # ── Salutation + intro ─────────────────────────────────────────
    story.append(Paragraph(_salutation(gender, tenant), s["normal"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "anbei erhalten Sie Ihre Nebenkostenabrechnung für den oben genannten Zeitraum. "
        "Die folgende Aufstellung zeigt die angefallenen Kosten, Ihre geleisteten Vorauszahlungen "
        "sowie den sich daraus ergebenden Nachzahlungsbetrag.",
        s["normal"]
    ))
    story.append(Spacer(1, 20))

    # ── 1. Strom ───────────────────────────────────────────────────
    story.append(Paragraph("1.  Stromkosten", s["section"]))
    strom_cost_per_tenant = strom_cost / num_tenants if num_tenants else strom_cost
    daily_limit = (monthly_strom_limit * 12) / 365 / num_tenants if num_tenants else 0
    story.append(Paragraph(
        f"Gesamtstromkosten der Wohnung werden zu gleichen Teilen auf {num_tenants} Mieter aufgeteilt. "
        f"Monatliche Vorauszahlung: <b>{monthly_strom_limit:.2f} €</b>. "
        f"Abrechnungsdauer: <b>{strom_days} Tage</b>.",
        s["normal"]
    ))
    story.append(Spacer(1, 6))
    story.append(_calc_table([
        ["Position", "Berechnung", "Betrag"],
        ["Gesamtkosten Wohnung (Strom)", "Gesamtkosten", f"{strom_cost:.2f} €"],
        ["Ihr Anteil", f"÷ {num_tenants} Mieter", f"{strom_cost_per_tenant:.2f} €"],
        ["Tägliche Vorauszahlung", f"({monthly_strom_limit:.2f} € × 12) ÷ 365 ÷ {num_tenants}", f"{daily_limit:.4f} €"],
        ["Vorauszahlung Zeitraum", f"{daily_limit:.4f} € × {strom_days} Tage", f"{strom_limit:.2f} €"],
        ["Nachzahlung Strom", "Ihr Anteil − Vorauszahlung", f"{strom_nach:.2f} €"],
    ], [195, 225, 80]))
    story.append(Spacer(1, 18))

    # ── 2. Betriebskosten ──────────────────────────────────────────
    story.append(Paragraph("2.  Betriebskosten", s["section"]))
    bk_cost_per_tenant = bk_cost / num_tenants if num_tenants else bk_cost
    bk_limit_month = monthly_bk_limit / num_tenants if num_tenants else 0
    story.append(Paragraph(
        f"Die Betriebskosten werden ebenfalls auf {num_tenants} Mieter aufgeteilt. "
        f"Monatliche Vorauszahlung: <b>{monthly_bk_limit:.2f} €</b>. "
        f"Abrechnungsdauer: <b>{bk_months} Monate</b>.",
        s["normal"]
    ))
    story.append(Spacer(1, 6))
    story.append(_calc_table([
        ["Position", "Berechnung", "Betrag"],
        ["Gesamte Betriebskosten", "Gesamtkosten", f"{bk_cost:.2f} €"],
        ["Ihr Anteil (gesamt)", f"÷ {num_tenants} Mieter", f"{bk_cost_per_tenant:.2f} €"],
        ["Monatliche Vorauszahlung", f"{monthly_bk_limit:.2f} € ÷ {num_tenants}", f"{bk_limit_month:.2f} €"],
        ["Vorauszahlung Zeitraum", f"{bk_limit_month:.2f} € × {bk_months} Monate", f"{bk_limit:.2f} €"],
        ["Nachzahlung Betriebskosten", "Ihr Anteil − Vorauszahlung", f"{bk_nach:.2f} €"],
    ], [195, 225, 80]))
    story.append(Spacer(1, 20))

    # ── 3. Gesamtbetrag ────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 8))
    story.append(_total_table(strom_nach, bk_nach, total, s))
    story.append(Spacer(1, 24))

    # ── Closing ────────────────────────────────────────────────────
    if total > 0:
        closing = (
            f"Wir bitten Sie, den Nachzahlungsbetrag von <b>{total:.2f} €</b> innerhalb von <b>7 Tagen</b> "
            "nach Erhalt dieses Schreibens auf das Ihnen bekannte Konto zu überweisen. "
            "Bei Fragen zur Abrechnung stehen wir Ihnen gerne zur Verfügung."
        )
    else:
        closing = (
            f"Ihre Vorauszahlungen haben die tatsächlichen Kosten vollständig gedeckt. "
            f"Es ergibt sich ein Guthaben von <b>{abs(total):.2f} €</b>, "
            "das wir Ihnen in Kürze erstatten werden."
        )
    story.append(Paragraph(closing, s["normal"]))
    story.append(Spacer(1, 30))
    story.append(Paragraph("Mit freundlichen Grüßen,", s["normal"]))
    story.append(Spacer(1, 24))
    story.append(Paragraph(f"<b>{landlord_name}</b>", s["normal"]))

    doc = SimpleDocTemplate(
        file, pagesize=A4, title=f"Abrechnung_{tenant}",
        leftMargin=25*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm
    )
    doc.build(story)
    return file


# ── Mahnung ────────────────────────────────────────────────────────────────────

def generate_mahnung(tenant_name, amount, address=None, gender="diverse"):
    file = f"pdf/Mahnung_{tenant_name}.pdf"
    s = _styles()
    today_str = date.today().strftime("%d.%m.%Y")
    due_str = (date.today() + timedelta(days=7)).strftime("%d.%m.%Y")
    story = []

    # ── Header ─────────────────────────────────────────────────────
    recipient_lines = [Paragraph(f"<b>{tenant_name}</b>", s["normal"])]
    if address:
        for line in address.replace(",", "\n").split("\n"):
            l = line.strip()
            if l:
                recipient_lines.append(Paragraph(l, s["normal"]))

    header_table = Table(
        [[recipient_lines, [Paragraph(today_str, s["right"])]]],
        colWidths=[280, 200]
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#c0392b")))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Zahlungserinnerung", s["title"]))
    story.append(Paragraph("Ausstehende Mietzahlung", s["small"]))
    story.append(Spacer(1, 18))

    story.append(Paragraph(_salutation(gender, tenant_name), s["normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "trotz unserer bisherigen Zahlungsaufforderung mussten wir feststellen, dass der folgende "
        "Betrag auf unserem Konto noch nicht eingegangen ist:",
        s["normal"]
    ))
    story.append(Spacer(1, 12))

    amt_table = Table([[f"Offener Betrag:  {amount:.2f} €"]], colWidths=[484])
    amt_table.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 13),
        ("TEXTCOLOR",   (0, 0), (-1, -1), colors.HexColor("#c0392b")),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND",  (0, 0), (-1, -1), colors.HexColor("#fdf2f2")),
        ("BOX",         (0, 0), (-1, -1), 1, colors.HexColor("#c0392b")),
        ("TOPPADDING",  (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
    ]))
    story.append(amt_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        f"Wir bitten Sie, den ausstehenden Betrag bis spätestens <b>{due_str}</b> "
        "auf das Ihnen bekannte Konto zu überweisen.",
        s["normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Sollte die Zahlung bis zu diesem Datum nicht bei uns eingehen, sehen wir uns leider gezwungen, "
        "weitere rechtliche Schritte einzuleiten. Dies kann zusätzliche Kosten verursachen, die wir gerne vermeiden möchten.",
        s["normal"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Falls Sie der Meinung sind, dass diese Erinnerung irrtümlich erfolgt ist, oder falls Sie Fragen "
        "zu Ihrem Zahlungsstand haben, stehen wir Ihnen gerne zur Verfügung.",
        s["normal"]
    ))
    story.append(Spacer(1, 30))
    story.append(Paragraph("Mit freundlichen Grüßen,", s["normal"]))
    story.append(Spacer(1, 24))
    story.append(Paragraph("<b>Ihre Vermieter</b>", s["normal"]))

    doc = SimpleDocTemplate(
        file, pagesize=A4, title=f"Mahnung_{tenant_name}",
        leftMargin=25*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm
    )
    doc.build(story)
    return file
