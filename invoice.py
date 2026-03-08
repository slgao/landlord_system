#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : invoice.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 16:11:53
#   Description :
#
# ================================================================

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import date


def create_invoice(
    tenant,
    address,
    strom_start,
    strom_end,
    strom_days,
    strom_cost_flat,
    betriebskosten_start,
    betriebskosten_end,
    betriebskosten_months,
    betriebskosten_flat,
    tenants,
):

    styles = getSampleStyleSheet()

    file = f"pdf/Abrechnung_{tenant}.pdf"

    story = []

    story.append(Paragraph("Nebenkostenabrechnung", styles["Title"]))
    story.append(Spacer(1,20))

    story.append(Paragraph(f"<b>Mieter:</b> {tenant}", styles["Normal"]))
    story.append(Paragraph(f"<b>Wohnung:</b> {address}", styles["Normal"]))
    story.append(Paragraph(f"<b>Datum:</b> {date.today().strftime('%d.%m.%Y')}", styles["Normal"]))
    story.append(Spacer(1,20))

    strom_cost_per_tenant = strom_cost_flat / tenants

    strom_limit_day = (50*12)/365/tenants
    strom_limit_period = strom_limit_day * strom_days

    strom_nachzahlung = strom_cost_per_tenant - strom_limit_period

    strom_table = [

        ["Strom (Elektrizität)",""],

        ["Abrechnungszeitraum",f"{strom_start} - {strom_end}"],

        ["Abrechnungsdauer",f"{strom_days} Tage"],

        ["Verbrauch Wohnung",f"{strom_cost_flat:.2f} €"],

        ["Kosten pro Mieter",f"{strom_cost_per_tenant:.2f} €"],

        ["Kostenbegrenzung Zeitraum",f"{strom_limit_period:.2f} €"],

        ["Nachzahlung Strom",f"{strom_nachzahlung:.2f} €"]

    ]

    betriebskosten_per_tenant = betriebskosten_flat / tenants

    betriebskosten_period_cost = betriebskosten_per_tenant/12 * betriebskosten_months

    limit_month = 206/tenants
    limit_period = limit_month * betriebskosten_months

    betriebskosten_nachzahlung = betriebskosten_period_cost - limit_period

    betriebskosten_table = [

        ["Betriebskosten (inkl. Heizung)",""],

        ["Abrechnungszeitraum",f"{betriebskosten_start} - {betriebskosten_end}"],

        ["Abrechnungsdauer",f"{betriebskosten_months} Monate"],

        ["Verbrauch Wohnung",f"{betriebskosten_flat:.2f} €"],

        ["Kosten pro Mieter",f"{betriebskosten_per_tenant:.2f} €"],

        ["Kosten Zeitraum",f"{betriebskosten_period_cost:.2f} €"],

        ["Kostenbegrenzung Zeitraum",f"{limit_period:.2f} €"],

        ["Nachzahlung",f"{betriebskosten_nachzahlung:.2f} €"]

    ]

    total = strom_nachzahlung + betriebskosten_nachzahlung

    total_table = [

        ["Gesamtbetrag nachzuzahlen",f"{total:.2f} €"]

    ]

    def table(data):

        t = Table(data,colWidths=[300,200])

        t.setStyle(TableStyle([
            ("GRID",(0,0),(-1,-1),1,colors.black),
            ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("ALIGN",(1,0),(1,-1),"RIGHT")
        ]))

        return t

    story.append(table(strom_table))
    story.append(Spacer(1,20))
    story.append(table(betriebskosten_table))
    story.append(Spacer(1,20))
    story.append(table(total_table))

    doc = SimpleDocTemplate(file,pagesize=A4)
    doc.build(story)

    return file
