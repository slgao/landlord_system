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

from reportlab.platypus import *
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import date
from pathlib import Path

PDF_DIR = Path("pdf")


def table(data):

    t = Table(data, colWidths=[320, 200])

    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ]
        )
    )

    return t


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
):

    styles = getSampleStyleSheet()

    file = f"pdf/Abrechnung_{tenant}.pdf"

    story = []

    story.append(Paragraph("Nebenkostenabrechnung", styles["Title"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph(f"<b>Mieter:</b> {tenant}", styles["Normal"]))
    story.append(Paragraph(f"<b>Adresse:</b> {address}", styles["Normal"]))
    story.append(Paragraph(f"<b>Datum:</b> {date.today()}", styles["Normal"]))

    story.append(Spacer(1, 20))

    strom_table = [
        ["Stromabrechnung", ""],
        ["Abrechnungszeitraum", strom_period],
        ["Abrechnungsdauer", f"{strom_days} Tage"],
        ["Kosten Wohnung", f"{strom_cost:.2f} €"],
        ["Kostenbegrenzung Zeitraum", f"{strom_limit:.2f} €"],
        ["Nachzahlung Strom", f"{strom_nach:.2f} €"],
    ]

    bk_table = [
        ["Betriebskosten", ""],
        ["Abrechnungszeitraum", bk_period],
        ["Abrechnungsdauer", f"{bk_months} Monate"],
        ["Kosten Zeitraum", f"{bk_cost:.2f} €"],
        ["Kostenbegrenzung Zeitraum", f"{bk_limit:.2f} €"],
        ["Nachzahlung", f"{bk_nach:.2f} €"],
    ]

    total = strom_nach + bk_nach

    total_table = [["Gesamtbetrag nachzuzahlen", f"{total:.2f} €"]]

    story.append(table(strom_table))
    story.append(Spacer(1, 20))
    story.append(table(bk_table))
    story.append(Spacer(1, 20))
    story.append(table(total_table))

    doc = SimpleDocTemplate(file, pagesize=A4, title=f"Abrechnung_{tenant}")
    doc.build(story)

    return file


def generate_mahnung(tenant_name, amount, address=None):
    from datetime import date

    file = f"pdf/Mahnung_{tenant_name}.pdf"
    styles = getSampleStyleSheet()
    normal = styles["BodyText"]
    normal.leading = 16

    from datetime import timedelta
    today = date.today().strftime("%d.%m.%Y")
    due = (date.today() + timedelta(days=7)).strftime("%d.%m.%Y")

    story = []

    story.append(Paragraph("<b>ZAHLUNGSERINNERUNG</b>", styles["Title"]))
    story.append(Spacer(1, 30))

    address_line = f"<br/>{address}" if address else ""
    story.append(Paragraph(f"An:<br/><b>{tenant_name}</b>{address_line}", normal))
    story.append(Spacer(1, 20))

    story.append(Paragraph(f"Datum: {today}", normal))
    story.append(Spacer(1, 24))

    story.append(Paragraph("Betreff: <b>Zahlungserinnerung – Ausstehende Mietzahlung</b>", normal))
    story.append(Spacer(1, 16))

    body = f"""
Sehr geehrte/r {tenant_name},<br/><br/>

trotz unserer bisherigen Zahlungsaufforderung mussten wir feststellen, dass der folgende Betrag auf unserem Konto noch nicht eingegangen ist:<br/><br/>

<b>Offener Betrag: {amount:.2f} €</b><br/><br/>

Wir bitten Sie, den ausstehenden Betrag bis spätestens <b>{due}</b> auf das Ihnen bekannte Konto zu überweisen.<br/><br/>

Sollte die Zahlung bis zu diesem Datum nicht bei uns eingehen, sehen wir uns leider gezwungen, weitere rechtliche Schritte einzuleiten. Dies kann zusätzliche Kosten für Sie verursachen, die wir gerne vermeiden möchten.<br/><br/>

Falls Sie der Meinung sind, dass diese Mahnung irrtümlich erfolgt ist, oder falls Sie Fragen zu Ihrem Zahlungsstand haben, stehen wir Ihnen gerne zur Verfügung.<br/><br/>

Wir bitten Sie, diese Angelegenheit umgehend zu klären, und danken Ihnen für Ihre Kooperation.<br/><br/>

Mit freundlichen Grüßen,<br/><br/>
<b>Ihre Vermieter</b>
"""
    story.append(Paragraph(body, normal))

    doc = SimpleDocTemplate(
        file, pagesize=A4,
        title=f"Mahnung_{tenant_name}",
        leftMargin=72, rightMargin=72, topMargin=72, bottomMargin=72
    )
    doc.build(story)

    return file
