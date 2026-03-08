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
from reportlab.lib.styles import getSampleStyleSheet
from datetime import date


def table(data):

    t = Table(data,colWidths=[320,200])

    t.setStyle(TableStyle([

        ("GRID",(0,0),(-1,-1),1,colors.black),

        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),

        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),

        ("ALIGN",(1,0),(1,-1),"RIGHT")

    ]))

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
    bk_nach
):

    styles = getSampleStyleSheet()

    file = f"pdf/Abrechnung_{tenant}.pdf"

    story=[]

    story.append(Paragraph("Nebenkostenabrechnung",styles["Title"]))
    story.append(Spacer(1,20))

    story.append(Paragraph(f"<b>Mieter:</b> {tenant}",styles["Normal"]))
    story.append(Paragraph(f"<b>Adresse:</b> {address}",styles["Normal"]))
    story.append(Paragraph(f"<b>Datum:</b> {date.today()}",styles["Normal"]))

    story.append(Spacer(1,20))

    strom_table=[

        ["Stromabrechnung",""],

        ["Abrechnungszeitraum",strom_period],

        ["Abrechnungsdauer",f"{strom_days} Tage"],

        ["Kosten Wohnung",f"{strom_cost:.2f} €"],

        ["Kostenbegrenzung Zeitraum",f"{strom_limit:.2f} €"],

        ["Nachzahlung Strom",f"{strom_nach:.2f} €"]

    ]

    bk_table=[

        ["Betriebskosten",""],

        ["Abrechnungszeitraum",bk_period],

        ["Abrechnungsdauer",f"{bk_months} Monate"],

        ["Kosten Zeitraum",f"{bk_cost:.2f} €"],

        ["Kostenbegrenzung Zeitraum",f"{bk_limit:.2f} €"],

        ["Nachzahlung",f"{bk_nach:.2f} €"]

    ]

    total = strom_nach + bk_nach

    total_table=[

        ["Gesamtbetrag nachzuzahlen",f"{total:.2f} €"]

    ]

    story.append(table(strom_table))
    story.append(Spacer(1,20))
    story.append(table(bk_table))
    story.append(Spacer(1,20))
    story.append(table(total_table))

    doc=SimpleDocTemplate(file,pagesize=A4)
    doc.build(story)

    return file


def mahnung_pdf(tenant,amount):

    styles=getSampleStyleSheet()

    file=f"pdf/Mahnung_{tenant}.pdf"

    story=[]

    story.append(Paragraph("Mahnung",styles["Title"]))
    story.append(Spacer(1,30))

    text=f"""
Sehr geehrter {tenant},

laut unserer Abrechnung besteht noch eine offene Forderung
in Höhe von <b>{amount:.2f} €</b>.

Wir bitten Sie, den Betrag innerhalb von 14 Tagen
auf das bekannte Konto zu überweisen.

Mit freundlichen Grüßen
"""

    story.append(Paragraph(text,styles["Normal"]))

    doc=SimpleDocTemplate(file,pagesize=A4)
    doc.build(story)

    return file
