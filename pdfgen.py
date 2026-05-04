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
PDF_DIR.mkdir(exist_ok=True)

# ── Palette ────────────────────────────────────────────────────────────────────
C_NAVY    = colors.HexColor("#1e2d3d")   # main dark
C_BLUE    = colors.HexColor("#3a7fc1")   # accent blue
C_LBLUE   = colors.HexColor("#deedf8")   # light-blue row highlight
C_SECBG   = colors.HexColor("#f3f8fd")   # section background
C_LGRAY   = colors.HexColor("#f8f9fa")   # alternating row / box bg
C_MGRAY   = colors.HexColor("#dde3ea")   # subtle separator
C_TEXT    = colors.HexColor("#2d3436")   # body text
C_MUTED   = colors.HexColor("#8395a7")   # muted / caption text
C_HDRFG   = colors.HexColor("#9ec5e8")   # header subtitle / date
C_RED     = colors.HexColor("#e74c3c")   # Nachzahlung / overdue
C_DARKRED = colors.HexColor("#7b241c")   # Mahnung banner
C_REDBG   = colors.HexColor("#fdf2f1")   # light red box background
C_GREEN   = colors.HexColor("#27ae60")   # Guthaben
C_WHITE   = colors.white

# Usable content width: A4(595.27pt) − leftMargin(25mm=70.87pt) − rightMargin(20mm=56.69pt)
W = 468


# ── Styles ─────────────────────────────────────────────────────────────────────

def _styles():
    s = {}
    s["body"]       = ParagraphStyle("body",       fontName="Helvetica",       fontSize=10, leading=15, textColor=C_TEXT)
    s["small"]      = ParagraphStyle("small",      fontName="Helvetica",       fontSize=8,  leading=12, textColor=C_MUTED)
    s["hdr_title"]  = ParagraphStyle("hdr_title",  fontName="Helvetica-Bold",  fontSize=18, leading=22, textColor=C_WHITE)
    s["hdr_sub"]    = ParagraphStyle("hdr_sub",    fontName="Helvetica",       fontSize=8,  leading=13, textColor=C_HDRFG)
    s["hdr_right"]  = ParagraphStyle("hdr_right",  fontName="Helvetica-Bold",  fontSize=10, leading=14, alignment=TA_RIGHT, textColor=C_WHITE)
    s["hdr_date"]   = ParagraphStyle("hdr_date",   fontName="Helvetica",       fontSize=8,  leading=13, alignment=TA_RIGHT, textColor=C_HDRFG)
    s["date_right"] = ParagraphStyle("date_right", fontName="Helvetica",       fontSize=10, leading=15, alignment=TA_RIGHT, textColor=C_MUTED)
    s["section"]    = ParagraphStyle("section",    fontName="Helvetica-Bold",  fontSize=11, leading=15, textColor=C_NAVY)
    s["caption"]    = ParagraphStyle("caption",    fontName="Helvetica",       fontSize=9,  leading=13, textColor=C_MUTED)
    return s


def _salutation(gender, name):
    if gender == "male":
        return f"Sehr geehrter Herr {name},"
    elif gender == "female":
        return f"Sehr geehrte Frau {name},"
    else:
        return f"Sehr geehrte/r {name},"


def _salutation_multi(primary_name, primary_gender, co_tenants):
    """Gender-aware salutation for one or more tenants."""
    persons = [{"name": primary_name, "gender": primary_gender}] + list(co_tenants)
    if len(persons) >= 3:
        return "Sehr geehrte Damen und Herren,"
    parts = []
    for p in persons:
        g, n = p["gender"], p["name"]
        if g == "male":
            parts.append(f"sehr geehrter Herr {n}")
        elif g == "female":
            parts.append(f"sehr geehrte Frau {n}")
        else:
            parts.append(f"sehr geehrte/r {n}")
    salutation = ", ".join(parts) + ","
    return salutation[0].upper() + salutation[1:]


# ── Shared building blocks ──────────────────────────────────────────────────────

def _header_banner(title, subtitle, sender, today_str, accent=None):
    """Full-width dark banner: title + subtitle left, sender + date right."""
    if accent is None:
        accent = C_NAVY
    s = _styles()
    left_cells = [Paragraph(title, s["hdr_title"])]
    if subtitle:
        left_cells.append(Spacer(1, 3))
        left_cells.append(Paragraph(subtitle, s["hdr_sub"]))
    right_cells = [
        Paragraph(sender, s["hdr_right"]),
        Spacer(1, 3),
        Paragraph(today_str, s["hdr_date"]),
    ]
    t = Table([[left_cells, right_cells]], colWidths=[320, 148])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), accent),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (0, -1),  18),
        ("LEFTPADDING",   (1, 0), (1, -1),  4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 18),
    ]))
    return t


def _accent_line(color=None, thickness=3):
    if color is None:
        color = C_BLUE
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=0, spaceBefore=0)


def _address_block(name, address_lines, today_str, s, co_tenants=None):
    """Recipient address left, date right."""
    left = [Paragraph(f"<b>{name}</b>", s["body"])]
    for ct in (co_tenants or []):
        left.append(Paragraph(f"<b>{ct['name']}</b>", s["body"]))
    for ln in address_lines:
        left.append(Paragraph(ln, s["body"]))
    right = [Spacer(1, 2), Paragraph(today_str, s["date_right"])]
    t = Table([[left, right]], colWidths=[310, 158])
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _section_header(num, title, s):
    """Numbered section title with a left accent strip and tinted background."""
    t = Table([["", Paragraph(f"{num}.  {title}", s["section"])]], colWidths=[5, W - 5])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), C_BLUE),
        ("BACKGROUND",    (1, 0), (1, -1), C_SECBG),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING",   (0, 0), (0, -1),  0),
        ("LEFTPADDING",   (1, 0), (1, -1),  12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _info_box(text, s):
    """Subtle caption row below a section header."""
    t = Table([[Paragraph(text, s["caption"])]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_SECBG),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, C_MGRAY),
        ("LEFTPADDING",   (0, 0), (-1, -1), 17),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _calc_table(data, col_widths=None):
    """
    Clean calculation table: navy header, alternating rows,
    highlighted last row, no vertical grid lines.
    Default col_widths sums to W=468.
    """
    if col_widths is None:
        col_widths = [190, 200, 78]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",     (0, 0), (-1, 0),  C_NAVY),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  C_WHITE),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        # Body rows
        ("FONTSIZE",       (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [C_WHITE, C_LGRAY]),
        ("LINEBELOW",      (0, 0), (-1, -2), 0.4, C_MGRAY),
        # Highlighted last row (Nachzahlung)
        ("BACKGROUND",     (0, -1), (-1, -1), C_LBLUE),
        ("FONTNAME",       (0, -1), (-1, -1), "Helvetica-Bold"),
        # Alignment
        ("ALIGN",          (2, 0), (2, -1),  "RIGHT"),
        ("ALIGN",          (1, 0), (1, -1),  "LEFT"),
        # Padding
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("LEFTPADDING",    (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 10),
    ]))
    return t


def _total_box(items):
    """
    Summary box: item rows on light gray, total row on dark navy
    with colored amount (red = Nachzahlung, green = Guthaben).
    """
    total    = sum(v for _, v in items)
    is_nach  = total > 0
    t_color  = C_RED if is_nach else C_GREEN
    t_label  = "Gesamtbetrag nachzuzahlen" if is_nach else "Guthaben (wird erstattet)"

    body_lbl = ParagraphStyle("_bl", fontName="Helvetica",      fontSize=10, leading=15, textColor=C_TEXT)
    body_amt = ParagraphStyle("_ba", fontName="Helvetica",      fontSize=10, leading=15, alignment=TA_RIGHT, textColor=C_TEXT)
    tot_lbl  = ParagraphStyle("_tl", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=C_WHITE)
    tot_amt  = ParagraphStyle("_ta", fontName="Helvetica-Bold", fontSize=15, leading=19, alignment=TA_RIGHT, textColor=t_color)

    rows = []
    for label, val in items:
        rows.append([Paragraph(label, body_lbl), Paragraph(f"{val:.2f} €", body_amt)])
    rows.append([Paragraph(t_label, tot_lbl), Paragraph(f"{abs(total):.2f} €", tot_amt)])

    t = Table(rows, colWidths=[390, 78])
    t.setStyle(TableStyle([
        # Item rows
        ("BACKGROUND",    (0, 0), (-1, -2), C_LGRAY),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, C_MGRAY),
        ("TOPPADDING",    (0, 0), (-1, -2), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 9),
        ("LEFTPADDING",   (0, 0), (-1, -2), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -2), 14),
        # Total row
        ("BACKGROUND",    (0, -1), (-1, -1), C_NAVY),
        ("LINEABOVE",     (0, -1), (-1, -1), 2,   C_BLUE),
        ("TOPPADDING",    (0, -1), (-1, -1), 13),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 13),
        ("LEFTPADDING",   (0, -1), (-1, -1), 14),
        ("RIGHTPADDING",  (0, -1), (-1, -1), 14),
    ]))
    return t


def _signature_block(landlord_name, signature_path, s):
    from reportlab.platypus import Image as RLImage
    story = []
    story.append(Spacer(1, 24))
    story.append(Paragraph("Mit freundlichen Grüßen,", s["body"]))
    story.append(Spacer(1, 10))

    if signature_path:
        img = RLImage(signature_path)
        nat_w, nat_h = img.imageWidth, img.imageHeight
        max_w, max_h = 110.0, 45.0
        scale = min(max_w / nat_w, max_h / nat_h, 1.0)
        img = RLImage(signature_path, width=nat_w * scale, height=nat_h * scale)
        img.hAlign = "LEFT"
        story.append(img)
    else:
        story.append(Spacer(1, 48))

    story.append(Paragraph(f"<b>{landlord_name}</b>", s["body"]))
    return story


# ── Nebenkostenabrechnung ──────────────────────────────────────────────────────

def invoice_pdf(
    tenant,
    address,
    landlord_name="Ihr Vermieter",
    gender="diverse",
    signature_path=None,
    strom=None,
    gas=None,
    water=None,
    warmwater=None,
    bk=None,
    heizung=None,
    extra=None,
    kaution_info=None,
    landlord_info=None,
    co_tenants=None,
):
    """
    strom / gas / water dict keys: bill_period, bill_days, period, days,
                                   cost, limit, nach, monthly_limit, num_tenants
    bk dict keys: bill_period, num_months, period, months, total_cost,
                  cost, limit, nach, monthly_limit, num_tenants
    Pass None to omit a section entirely.
    """
    s = _styles()
    safe_tenant = tenant.replace("/", "-").replace("\\", "-")
    file = f"pdf/Abrechnung_{safe_tenant}.pdf"
    story = []
    today_str = date.today().strftime("%d.%m.%Y")

    # Period subtitle for header (show tenant's effective periods)
    period_parts = []
    if strom:     period_parts.append(f"Strom: {strom['period']} ({strom['days']} Tage)")
    if gas:       period_parts.append(f"Gas: {gas['period']} ({gas['days']} Tage)")
    if water:     period_parts.append(f"Kaltwasser: {water['period']} ({water['days']} Tage)")
    if warmwater: period_parts.append(f"Warmwasser: {warmwater['period']} ({warmwater['days']} Tage)")
    if heizung:   period_parts.append(f"Heizung: {heizung['period']} ({heizung['days']} Tage)")
    if bk:        period_parts.append(f"BK: {bk['period']} ({bk['months']} Monate)")
    period_str = "  ·  ".join(period_parts)

    # ── Header banner ──────────────────────────────────────────────
    story.append(_header_banner("NEBENKOSTENABRECHNUNG", period_str, landlord_name, today_str))
    story.append(_accent_line(C_BLUE))
    story.append(Spacer(1, 22))

    # ── Address block ──────────────────────────────────────────────
    addr_lines = []
    if address:
        for line in address.replace(",", "\n").split("\n"):
            l = line.strip()
            if l:
                addr_lines.append(l)
    story.append(_address_block(tenant, addr_lines, today_str, s, co_tenants=co_tenants))
    story.append(Spacer(1, 18))
    story.append(_accent_line(C_MGRAY, thickness=0.5))
    story.append(Spacer(1, 14))

    # ── Salutation + intro ─────────────────────────────────────────
    story.append(Paragraph(_salutation_multi(tenant, gender, co_tenants or []), s["body"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "anbei erhalten Sie Ihre Nebenkostenabrechnung für den oben genannten Zeitraum. "
        "Die folgende Aufstellung zeigt die angefallenen Kosten, Ihre geleisteten Vorauszahlungen "
        "sowie den sich daraus ergebenden Nachzahlungsbetrag.",
        s["body"]
    ))
    story.append(Spacer(1, 22))

    section_num = 1
    total_items = []

    # ── Strom ──────────────────────────────────────────────────────
    if strom:
        d = strom
        n = d["num_tenants"]
        daily_gp = d["grundpreis_monthly"] * 12 / 365
        pauschale_s = d.get("is_pauschale", False)
        vz_label_s  = "Pauschale" if pauschale_s else "Vorauszahlung"

        story.append(_section_header(section_num, "Stromkosten", s))
        meter_line_s = ""
        if d.get("meter_serial"):
            meter_line_s = f"Stromzähler: {d['meter_serial']}"
            if d.get("meter_description"):
                meter_line_s += f" ({d['meter_description']})"
            meter_line_s += "  |  "
        story.append(_info_box(
            f"{meter_line_s}"
            f"Abrechnungszeitraum: {d['bill_period']}  ·  {d['bill_days']} Tage  |  "
            f"Ihr Zeitraum: {d['period']}  ·  {d['days']} Tage  ·  "
            f"{vz_label_s}: {d['monthly_limit']:.2f} €/Monat  ·  {n} Mieter"
            + ("  ·  Keine Erstattung bei Unterschreitung" if pauschale_s else ""), s
        ))
        story.append(Spacer(1, 8))
        story.append(_calc_table([
            ["Position", "Berechnung", "Betrag"],
            ["Anfang Zählerstand",       "—",
             f"{d['start_kwh']:.2f} kWh"],
            ["Ende Zählerstand",         "—",
             f"{d['end_kwh']:.2f} kWh"],
            ["Gesamtverbrauch Wohnung",  f"{d['end_kwh']:.2f} − {d['start_kwh']:.2f}",
             f"{d['verbrauch']:.2f} kWh"],
            ["Ihr Verbrauchsanteil",     f"× {d['days']} ÷ {d['bill_days']} Tage ÷ {n} Mieter",
             f"{d['verbrauch_tenant']:.2f} kWh"],
            ["Arbeitskosten",            f"{d['verbrauch_tenant']:.2f} kWh × {d['arbeitspreis']:.3f} €/kWh",
             f"{d['arbeitskosten']:.2f} €"],
            ["Grundpreis (täglich)",     f"{d['grundpreis_monthly']:.2f} €/Mon × 12 ÷ 365",
             f"{daily_gp:.3f} €/Tag"],
            ["Grundpreis Ihr Anteil",    f"{daily_gp:.3f} € × {d['days']} Tage ÷ {n} Mieter",
             f"{d['grundkosten']:.2f} €"],
            ["Gesamtkosten Ihr Anteil",  "Arbeitskosten + Grundpreis",
             f"{d['cost']:.2f} €"],
            [f"{vz_label_s} Zeitraum",   f"{d['monthly_limit']:.2f} €/Mon × 12 ÷ 365 × {d['days']} Tage",
             f"{d['limit']:.2f} €"],
            [f"Nachzahlung Strom",       f"Ihr Anteil − {vz_label_s}" + (" (mind. 0 €)" if pauschale_s else ""),
             f"{d['nach']:.2f} €"],
        ], col_widths=[175, 215, 78]))
        story.append(Spacer(1, 18))
        total_items.append(("Nachzahlung Strom", d["nach"]))
        section_num += 1

    # ── Gas ────────────────────────────────────────────────────────
    if gas:
        d = gas
        n = d["num_tenants"]
        daily_gp = d["grundpreis_monthly"] * 12 / 365
        pauschale_g = d.get("is_pauschale", False)
        vz_label_g  = "Pauschale" if pauschale_g else "Vorauszahlung"

        story.append(_section_header(section_num, "Gaskosten", s))
        story.append(_info_box(
            f"Abrechnungszeitraum: {d['bill_period']}  ·  {d['bill_days']} Tage  |  "
            f"Ihr Zeitraum: {d['period']}  ·  {d['days']} Tage  ·  "
            f"{vz_label_g}: {d['monthly_limit']:.2f} €/Monat  ·  {n} Mieter"
            + ("  ·  Keine Erstattung bei Unterschreitung" if pauschale_g else ""), s
        ))
        story.append(Spacer(1, 8))
        story.append(_calc_table([
            ["Position", "Berechnung", "Betrag"],
            ["Anfang Gaszählerstand",    "—",
             f"{d['start_m3']:.3f} m³"],
            ["Ende Gaszählerstand",      "—",
             f"{d['end_m3']:.3f} m³"],
            ["Verbrauch (m³)",           f"{d['end_m3']:.3f} − {d['start_m3']:.3f}",
             f"{d['verbrauch_m3']:.3f} m³"],
            ["Verbrauch (kWh)",          f"{d['verbrauch_m3']:.3f} m³ × {d['umrechnungsfaktor']:.3f} kWh/m³",
             f"{d['verbrauch_kwh']:.2f} kWh"],
            ["Ihr Verbrauchsanteil",     f"× {d['days']} ÷ {d['bill_days']} Tage ÷ {n} Mieter",
             f"{d['verbrauch_kwh_t']:.2f} kWh"],
            ["Arbeitskosten",            f"{d['verbrauch_kwh_t']:.2f} kWh × {d['arbeitspreis']:.3f} €/kWh",
             f"{d['arbeitskosten']:.2f} €"],
            ["Grundpreis (täglich)",     f"{d['grundpreis_monthly']:.2f} €/Mon × 12 ÷ 365",
             f"{daily_gp:.3f} €/Tag"],
            ["Grundpreis Ihr Anteil",    f"{daily_gp:.3f} € × {d['days']} Tage ÷ {n} Mieter",
             f"{d['grundkosten']:.2f} €"],
            ["Gesamtkosten Ihr Anteil",  "Arbeitskosten + Grundpreis",
             f"{d['cost']:.2f} €"],
            [f"{vz_label_g} Zeitraum",   f"{d['monthly_limit']:.2f} €/Mon × 12 ÷ 365 × {d['days']} Tage",
             f"{d['limit']:.2f} €"],
            ["Nachzahlung Gas",          f"Ihr Anteil − {vz_label_g}" + (" (mind. 0 €)" if pauschale_g else ""),
             f"{d['nach']:.2f} €"],
        ], col_widths=[175, 215, 78]))
        story.append(Spacer(1, 18))
        total_items.append(("Nachzahlung Gas", d["nach"]))
        section_num += 1

    # ── Kaltwasser ─────────────────────────────────────────────────
    if water:
        d = water
        n = d["num_tenants"]
        pauschale_w = d.get("is_pauschale", False)
        vz_label_w  = "Pauschale" if pauschale_w else "Vorauszahlung"

        story.append(_section_header(section_num, "Kaltwasser", s))
        meter_line_w = ""
        if d.get("meter_serial"):
            meter_line_w = f"Kaltwasserzähler: {d['meter_serial']}"
            if d.get("meter_description"):
                meter_line_w += f" ({d['meter_description']})"
            meter_line_w += "  |  "
        story.append(_info_box(
            f"{meter_line_w}"
            f"Abrechnungszeitraum: {d['bill_period']}  ·  {d['bill_days']} Tage  |  "
            f"Ihr Zeitraum: {d['period']}  ·  {d['days']} Tage  ·  "
            f"{vz_label_w}: {d['monthly_limit']:.2f} €/Monat  ·  {n} Mieter"
            + ("  ·  Keine Erstattung bei Unterschreitung" if pauschale_w else ""), s
        ))
        story.append(Spacer(1, 8))
        story.append(_calc_table([
            ["Position", "Berechnung", "Betrag"],
            ["Anfang Wasserzählerstand",  "—",
             f"{d['start_m3']:.3f} m³"],
            ["Ende Wasserzählerstand",    "—",
             f"{d['end_m3']:.3f} m³"],
            ["Verbrauch",                 f"{d['end_m3']:.3f} − {d['start_m3']:.3f}",
             f"{d['verbrauch_m3']:.3f} m³"],
            ["Frischwasser",              f"{d['frischwasser_per_m3']:.3f} €/m³",
             f"{d['frischwasser_per_m3']:.3f} €/m³"],
            ["Abwasser",                  f"{d['abwasser_per_m3']:.3f} €/m³",
             f"{d['abwasser_per_m3']:.3f} €/m³"],
            ["Gesamtpreis je m³",         "Frischwasser + Abwasser",
             f"{d['cost_per_m3']:.3f} €/m³"],
            ["Gesamtkosten Wohnung",      f"{d['verbrauch_m3']:.3f} m³ × {d['cost_per_m3']:.3f} €/m³",
             f"{d['cost_flat']:.2f} €"],
            ["Ihr Anteil",                f"× {d['days']} ÷ {d['bill_days']} Tage ÷ {n} Mieter",
             f"{d['cost']:.2f} €"],
            [f"{vz_label_w} Zeitraum",    f"{d['monthly_limit']:.2f} €/Mon × 12 ÷ 365 × {d['days']} Tage",
             f"{d['limit']:.2f} €"],
            ["Nachzahlung Kaltwasser",    f"Ihr Anteil − {vz_label_w}" + (" (mind. 0 €)" if pauschale_w else ""),
             f"{d['nach']:.2f} €"],
        ], col_widths=[175, 215, 78]))
        story.append(Spacer(1, 18))
        total_items.append(("Nachzahlung Kaltwasser", d["nach"]))
        section_num += 1

    # ── Warmwasser ─────────────────────────────────────────────────
    if warmwater:
        d = warmwater
        n = d["num_tenants"]
        pauschale_ww = d.get("is_pauschale", False)
        vz_label_ww  = "Pauschale" if pauschale_ww else "Vorauszahlung"
        meters_ww    = d.get("meter_details", [])

        story.append(_section_header(section_num, "Warmwasser", s))
        story.append(_info_box(
            f"Abrechnungszeitraum: {d['bill_period']}  ·  {d['bill_days']} Tage  |  "
            f"Ihr Zeitraum: {d['period']}  ·  {d['days']} Tage  ·  "
            f"{vz_label_ww}: {d['monthly_limit']:.2f} €/Monat  ·  {n} Mieter"
            + ("  ·  Keine Erstattung bei Unterschreitung" if pauschale_ww else ""), s
        ))
        story.append(Spacer(1, 8))

        rows_ww = [["Position", "Berechnung", "Betrag"]]
        for m in meters_ww:
            label = f"Zähler {m['serial'] or '—'}"
            if m.get("description"):
                label += f" ({m['description']})"
            rows_ww.append([
                label,
                f"{m['end']:.3f} − {m['start']:.3f} m³",
                f"{m['verbrauch']:.3f} m³",
            ])
        rows_ww.append([
            "Verbrauch (Summe)",
            "Σ alle Zähler" if len(meters_ww) > 1 else "—",
            f"{d['verbrauch_m3']:.3f} m³",
        ])
        rows_ww.append(["Frischwasser",  f"{d['frischwasser_per_m3']:.3f} €/m³",
                        f"{d['frischwasser_per_m3']:.3f} €/m³"])
        rows_ww.append(["Abwasser",      f"{d['abwasser_per_m3']:.3f} €/m³",
                        f"{d['abwasser_per_m3']:.3f} €/m³"])
        rows_ww.append(["Heizenergie",   f"{d['heizenergie_per_m3']:.3f} €/m³",
                        f"{d['heizenergie_per_m3']:.3f} €/m³"])
        rows_ww.append(["Gesamtpreis je m³",
                        "Frischwasser + Abwasser + Heizenergie",
                        f"{d['cost_per_m3']:.3f} €/m³"])
        rows_ww.append(["Gesamtkosten Wohnung",
                        f"{d['verbrauch_m3']:.3f} m³ × {d['cost_per_m3']:.3f} €/m³",
                        f"{d['cost_flat']:.2f} €"])
        rows_ww.append(["Ihr Anteil",
                        f"× {d['days']} ÷ {d['bill_days']} Tage ÷ {n} Mieter",
                        f"{d['cost']:.2f} €"])
        rows_ww.append([f"{vz_label_ww} Zeitraum",
                        f"{d['monthly_limit']:.2f} €/Mon × 12 ÷ 365 × {d['days']} Tage",
                        f"{d['limit']:.2f} €"])
        rows_ww.append(["Nachzahlung Warmwasser",
                        f"Ihr Anteil − {vz_label_ww}"
                        + (" (mind. 0 €)" if pauschale_ww else ""),
                        f"{d['nach']:.2f} €"])

        story.append(_calc_table(rows_ww, col_widths=[175, 215, 78]))
        story.append(Spacer(1, 18))
        total_items.append(("Nachzahlung Warmwasser", d["nach"]))
        section_num += 1

    # ── Betriebskosten ─────────────────────────────────────────────
    if bk:
        d = bk
        n = d["num_tenants"]
        cost_per_tenant_full = d["total_cost"] / n if n else d["total_cost"]
        bk_limit_month = d["monthly_limit"] / n if n else 0

        story.append(_section_header(section_num, "Betriebskosten", s))
        story.append(_info_box(
            f"Abrechnungszeitraum: {d['bill_period']}  ·  {d['num_months']} Monate  |  "
            f"Ihr Zeitraum: {d['period']}  ·  {d['months']} Monate  ·  "
            f"Vorauszahlung: {d['monthly_limit']:.2f} €/Monat  ·  {n} Mieter", s
        ))
        story.append(Spacer(1, 8))
        story.append(_calc_table([
            ["Position", "Berechnung", "Betrag"],
            ["Gesamte Betriebskosten", f"Abrechnungszeitraum {d['num_months']} Monate", f"{d['total_cost']:.2f} €"],
            ["Ihr Anteil (gesamt)", f"÷ {n} Mieter", f"{cost_per_tenant_full:.2f} €"],
            ["Ihr Anteil (Nutzungsdauer)", f"÷ {d['num_months']} × {d['months']} Monate", f"{d['cost']:.2f} €"],
            ["Monatliche Vorauszahlung", f"{d['monthly_limit']:.2f} € ÷ {n}", f"{bk_limit_month:.2f} €"],
            ["Vorauszahlung Zeitraum", f"{bk_limit_month:.2f} € × {d['months']} Monate", f"{d['limit']:.2f} €"],
            ["Nachzahlung Betriebskosten", "Ihr Anteil − Vorauszahlung", f"{d['nach']:.2f} €"],
        ]))
        story.append(Spacer(1, 18))
        total_items.append(("Nachzahlung Betriebskosten", d["nach"]))
        section_num += 1

    # ── Heizkosten ─────────────────────────────────────────────────
    if heizung:
        d = heizung
        n = d["num_tenants"]
        unit  = d.get("unit_label", "Einheiten")
        pauschale_h = d.get("is_pauschale", False)
        vz_label_h  = "Pauschale" if pauschale_h else "Vorauszahlung"

        story.append(_section_header(section_num, "Heizkosten (Heizkostenverteiler)", s))
        price_kwh = d.get("price_kwh", 0.0)
        story.append(_info_box(
            f"Abrechnungszeitraum: {d['bill_period']}  ·  {d['bill_days']} Tage  |  "
            f"Ihr Zeitraum: {d['period']}  ·  {d['days']} Tage  |  "
            f"Preis: {price_kwh:.4f} €/kWh  ·  "
            f"{vz_label_h}: {d['monthly_limit']:.2f} €/Monat  ·  {n} Mieter"
            + ("  ·  Keine Erstattung bei Unterschreitung" if pauschale_h else ""), s
        ))
        story.append(Spacer(1, 8))

        # ── Per-meter breakdown table ─────────────────────────────
        meter_style  = ParagraphStyle("_ms",  fontName="Helvetica",      fontSize=8, leading=11, textColor=C_TEXT)
        meter_hdr    = ParagraphStyle("_mh",  fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=C_WHITE)
        meter_right  = ParagraphStyle("_mr",  fontName="Helvetica",      fontSize=8, leading=11, textColor=C_TEXT, alignment=TA_RIGHT)
        meter_hdr_r  = ParagraphStyle("_mhr", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=C_WHITE, alignment=TA_RIGHT)
        meter_tot    = ParagraphStyle("_mt",  fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=C_TEXT)
        meter_tot_r  = ParagraphStyle("_mtr", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=C_TEXT, alignment=TA_RIGHT)

        # Check if any meter uses a conversion factor ≠ 1
        any_factor = any(abs(m.get("conversion_factor", 1.0) - 1.0) > 1e-6
                         for m in d.get("meter_details", []))

        if any_factor:
            # Einheiten → ×factor (per meter) → kWh → ×€/kWh (shared) → Kosten
            mw = [100, 105, 45, 45, 52, 50, 71]
            m_rows = [[
                Paragraph("Seriennummer",        meter_hdr),
                Paragraph("Beschreibung",        meter_hdr),
                Paragraph(f"Start ({unit})",     meter_hdr_r),
                Paragraph(f"Ende ({unit})",      meter_hdr_r),
                Paragraph(f"Verbr. ({unit})",    meter_hdr_r),
                Paragraph("kWh (×Faktor)",       meter_hdr_r),
                Paragraph("Kosten",              meter_hdr_r),
            ]]
            for m in d.get("meter_details", []):
                fac = m.get("conversion_factor", 1.0)
                kwh = m.get("kwh", round(m["units"] * fac, 3))
                m_rows.append([
                    Paragraph(m["serial"],                       meter_style),
                    Paragraph(m["description"],                  meter_style),
                    Paragraph(f"{m['start']:.3f}",               meter_right),
                    Paragraph(f"{m['end']:.3f}",                 meter_right),
                    Paragraph(f"{m['units']:.3f}",               meter_right),
                    Paragraph(f"{kwh:.3f} (×{fac:.4f})",        meter_right),
                    Paragraph(f"{m['cost']:.2f} €",             meter_right),
                ])
            m_rows.append([
                Paragraph("Gesamt",                        meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph(f"{d['total_cost_flat']:.2f} €", meter_tot_r),
            ])
        else:
            # Meters already read in kWh (factor = 1.0 for all)
            mw = [120, 130, 50, 50, 60, 58]
            m_rows = [[
                Paragraph("Seriennummer",    meter_hdr),
                Paragraph("Beschreibung",    meter_hdr),
                Paragraph("Start (kWh)",     meter_hdr_r),
                Paragraph("Ende (kWh)",      meter_hdr_r),
                Paragraph("Verbr. (kWh)",    meter_hdr_r),
                Paragraph("Kosten",          meter_hdr_r),
            ]]
            for m in d.get("meter_details", []):
                m_rows.append([
                    Paragraph(m["serial"],          meter_style),
                    Paragraph(m["description"],     meter_style),
                    Paragraph(f"{m['start']:.3f}",  meter_right),
                    Paragraph(f"{m['end']:.3f}",    meter_right),
                    Paragraph(f"{m['units']:.3f}",  meter_right),
                    Paragraph(f"{m['cost']:.2f} €", meter_right),
                ])
            m_rows.append([
                Paragraph("Gesamt",                        meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph("",                              meter_tot),
                Paragraph(f"{d['total_cost_flat']:.2f} €", meter_tot_r),
            ])
        mt = Table(m_rows, colWidths=mw)
        mt.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),   C_NAVY),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2),  [C_WHITE, C_LGRAY]),
            ("LINEBELOW",     (0, 0), (-1, -2),  0.4, C_MGRAY),
            ("BACKGROUND",    (0, -1),(-1, -1),  C_LBLUE),
            ("VALIGN",        (0, 0), (-1, -1),  "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1),  5),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  5),
            ("LEFTPADDING",   (0, 0), (-1, -1),  6),
            ("RIGHTPADDING",  (0, 0), (-1, -1),  6),
        ]))
        story.append(mt)
        story.append(Spacer(1, 8))

        # ── Proration calculation table ───────────────────────────
        story.append(_calc_table([
            ["Position", "Berechnung", "Betrag"],
            ["Gesamtkosten Wohnung",    f"Σ ({unit} × Faktor × {price_kwh:.4f} €/kWh)",
             f"{d['total_cost_flat']:.2f} €"],
            ["Ihr Anteil (Zeitraum)",   f"× {d['days']} ÷ {d['bill_days']} Tage ÷ {n} Mieter",
             f"{d['cost']:.2f} €"],
            [f"{vz_label_h} Zeitraum",  f"{d['monthly_limit']:.2f} €/Mon × 12 ÷ 365 × {d['days']} Tage",
             f"{d['limit']:.2f} €"],
            [f"Nachzahlung Heizkosten", f"Ihr Anteil − {vz_label_h}" + (" (mind. 0 €)" if pauschale_h else ""),
             f"{d['nach']:.2f} €"],
        ], col_widths=[175, 215, 78]))
        story.append(Spacer(1, 18))
        total_items.append(("Nachzahlung Heizkosten", d["nach"]))
        section_num += 1

    # ── Zusätzliche Positionen ─────────────────────────────────────
    if extra:
        items = [i for i in extra.get("items", []) if i.get("description")]
        if items:
            subtotal = sum(i["amount"] for i in items)
            story.append(_section_header(section_num, "Zusätzliche Positionen / Vereinbarte Abzüge", s))
            story.append(_info_box(
                "Die folgenden Positionen wurden zwischen Mieter und Vermieter vereinbart "
                "und sind Teil dieser Abrechnung.", s
            ))
            story.append(Spacer(1, 8))

            cell_style = ParagraphStyle("_ec", fontName="Helvetica", fontSize=9,
                                        leading=13, textColor=C_TEXT)
            hdr_style  = ParagraphStyle("_eh", fontName="Helvetica-Bold", fontSize=9,
                                        leading=13, textColor=C_WHITE)
            tot_style  = ParagraphStyle("_et", fontName="Helvetica-Bold", fontSize=9,
                                        leading=13, textColor=C_TEXT)
            amt_style  = ParagraphStyle("_ea", fontName="Helvetica", fontSize=9,
                                        leading=13, textColor=C_TEXT, alignment=TA_RIGHT)
            tot_amt_style = ParagraphStyle("_eta", fontName="Helvetica-Bold", fontSize=9,
                                           leading=13, textColor=C_TEXT, alignment=TA_RIGHT)

            rows = [[Paragraph("Bezeichnung", hdr_style), Paragraph("Betrag", hdr_style)]]
            for item in items:
                rows.append([
                    Paragraph(item["description"], cell_style),
                    Paragraph(f"{item['amount']:.2f} €", amt_style),
                ])
            rows.append([Paragraph("Gesamt", tot_style), Paragraph(f"{subtotal:.2f} €", tot_amt_style)])

            col_w = [390, 78]
            t = Table(rows, colWidths=col_w)
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0),   C_NAVY),
                ("ROWBACKGROUNDS",(0, 1), (-1, -2),  [C_WHITE, C_LGRAY]),
                ("LINEBELOW",     (0, 0), (-1, -2),  0.4, C_MGRAY),
                ("BACKGROUND",    (0, -1),(-1, -1),  C_LBLUE),
                ("VALIGN",        (0, 0), (-1, -1),  "TOP"),
                ("TOPPADDING",    (0, 0), (-1, -1),  7),
                ("BOTTOMPADDING", (0, 0), (-1, -1),  7),
                ("LEFTPADDING",   (0, 0), (-1, -1),  10),
                ("RIGHTPADDING",  (0, 0), (-1, -1),  10),
            ]))
            story.append(t)
            story.append(Spacer(1, 18))
            total_items.append(("Zusätzliche Positionen", subtotal))
            section_num += 1

    # ── Summary box ────────────────────────────────────────────────
    story.append(_accent_line(C_MGRAY, thickness=0.5))
    story.append(Spacer(1, 10))
    story.append(_total_box(total_items))
    story.append(Spacer(1, 26))

    # ── Kautionsverrechnung block (optional) ───────────────────────
    total = sum(v for _, v in total_items)

    if kaution_info and total > 0:
        k_amt      = kaution_info["kaution_amount"]
        remaining  = k_amt - total
        still_owed = max(0.0, -remaining)
        k_return   = max(0.0, remaining)

        lbl  = ParagraphStyle("_kl", fontName="Helvetica",      fontSize=10, leading=15, textColor=C_TEXT)
        lbl_b= ParagraphStyle("_klb",fontName="Helvetica-Bold", fontSize=10, leading=15, textColor=C_TEXT)
        amt  = ParagraphStyle("_ka", fontName="Helvetica",      fontSize=10, leading=15, alignment=TA_RIGHT, textColor=C_TEXT)
        amt_g= ParagraphStyle("_kg", fontName="Helvetica-Bold", fontSize=11, leading=15, alignment=TA_RIGHT, textColor=C_GREEN)
        amt_r= ParagraphStyle("_kr", fontName="Helvetica-Bold", fontSize=11, leading=15, alignment=TA_RIGHT, textColor=C_RED)

        k_rows = [
            [Paragraph("Kautionsverrechnung", lbl_b), Paragraph("", amt)],
            [Paragraph("Hinterlegte Kaution", lbl),   Paragraph(f"{k_amt:.2f} €", amt)],
            [Paragraph("Abzug (diese Abrechnung)", lbl), Paragraph(f"− {total:.2f} €", amt)],
        ]
        if k_return > 0:
            k_rows.append([
                Paragraph("Verbleibende Kaution (wird erstattet)", lbl_b),
                Paragraph(f"{k_return:.2f} €", amt_g),
            ])
        else:
            k_rows.append([
                Paragraph("Verbleibende Kaution", lbl_b),
                Paragraph("0.00 €", amt),
            ])
        if still_owed > 0:
            k_rows.append([
                Paragraph("Noch zu zahlen (Kaution nicht ausreichend)", lbl_b),
                Paragraph(f"{still_owed:.2f} €", amt_r),
            ])

        kt = Table(k_rows, colWidths=[390, 78])
        kt.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),   C_SECBG),
            ("LINEBELOW",     (0, 0), (-1, 0),   1.0, C_BLUE),
            ("BACKGROUND",    (0, 1), (-1, -1),  C_LGRAY),
            ("LINEBELOW",     (0, 1), (-1, -2),  0.4, C_MGRAY),
            ("BACKGROUND",    (0, -1),(-1, -1),  C_SECBG),
            ("LINEABOVE",     (0, -1),(-1, -1),  1.0, C_MGRAY),
            ("TOPPADDING",    (0, 0), (-1, -1),  8),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  8),
            ("LEFTPADDING",   (0, 0), (-1, -1),  12),
            ("RIGHTPADDING",  (0, 0), (-1, -1),  12),
            ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
        ]))
        story.append(Spacer(1, 10))
        story.append(kt)
        story.append(Spacer(1, 20))

        # Closing paragraph for Kautionsverrechnung mode
        if still_owed > 0:
            closing = (
                f"Der Nachzahlungsbetrag von <b>{total:.2f} €</b> übersteigt die hinterlegte Kaution. "
                f"Die Kaution von {k_amt:.2f} € wird vollständig verrechnet. "
                f"Den verbleibenden Betrag von <b>{still_owed:.2f} €</b> bitten wir Sie innerhalb von "
                "<b>7 Tagen</b> auf das Ihnen bekannte Konto zu überweisen."
            )
        else:
            closing = (
                f"Der Nachzahlungsbetrag von <b>{total:.2f} €</b> wird mit Ihrer Kaution verrechnet. "
                f"Die verbleibende Kaution in Höhe von <b>{k_return:.2f} €</b> "
                "wird Ihnen in Kürze zurückerstattet. "
                "Bei Fragen zur Abrechnung stehen wir Ihnen gerne zur Verfügung."
            )
    elif total > 0:
        closing = (
            f"Wir bitten Sie, den Nachzahlungsbetrag von <b>{total:.2f} €</b> innerhalb von <b>7 Tagen</b> "
            "nach Erhalt dieses Schreibens auf das Ihnen bekannte Konto zu überweisen. "
            "Bei Fragen zur Abrechnung stehen wir Ihnen gerne zur Verfügung."
        )
    else:
        closing = (
            "Ihre Vorauszahlungen haben die tatsächlichen Kosten vollständig gedeckt. "
            f"Es ergibt sich ein Guthaben von <b>{abs(total):.2f} €</b>, "
            "das wir Ihnen in Kürze erstatten werden."
        )
    story.append(Paragraph(closing, s["body"]))
    story.append(Spacer(1, 30))
    story.extend(_signature_block(landlord_name, signature_path, s))

    # ── Optional landlord info footer ──────────────────────────────
    if landlord_info:
        parts = []
        if landlord_info.get("address"):
            parts.append(f"Adresse: {landlord_info['address']}")
        if landlord_info.get("iban"):
            parts.append(f"IBAN: {landlord_info['iban']}")
        if landlord_info.get("bank"):
            parts.append(f"Bank: {landlord_info['bank']}")
        if parts:
            story.append(Spacer(1, 16))
            info_t = Table([[Paragraph("  ·  ".join(parts), s["small"])]], colWidths=[W])
            info_t.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), C_SECBG),
                ("LINEABOVE",     (0, 0), (-1, -1), 0.5, C_MGRAY),
                ("TOPPADDING",    (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ]))
            story.append(info_t)

    doc = SimpleDocTemplate(
        file, pagesize=A4, title=f"Abrechnung_{tenant}",
        leftMargin=25*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm
    )
    doc.build(story)
    return file


# ── Mahnung ────────────────────────────────────────────────────────────────────

def generate_mahnung(tenant_name, amount, address=None, gender="diverse", signature_path=None, co_tenants=None):
    safe_name = tenant_name.replace("/", "-").replace("\\", "-")
    file = f"pdf/Mahnung_{safe_name}.pdf"
    s = _styles()
    today_str = date.today().strftime("%d.%m.%Y")
    due_str   = (date.today() + timedelta(days=7)).strftime("%d.%m.%Y")
    story = []

    # ── Header banner (red theme) ──────────────────────────────────
    story.append(_header_banner(
        "ZAHLUNGSERINNERUNG", "Ausstehende Mietzahlung",
        "Ihre Vermieter", today_str, accent=C_DARKRED
    ))
    story.append(_accent_line(C_RED))
    story.append(Spacer(1, 22))

    # ── Address block ──────────────────────────────────────────────
    addr_lines = []
    if address:
        for line in address.replace(",", "\n").split("\n"):
            l = line.strip()
            if l:
                addr_lines.append(l)
    story.append(_address_block(tenant_name, addr_lines, today_str, s, co_tenants=co_tenants))
    story.append(Spacer(1, 18))
    story.append(_accent_line(C_MGRAY, thickness=0.5))
    story.append(Spacer(1, 14))

    # ── Salutation ─────────────────────────────────────────────────
    story.append(Paragraph(_salutation_multi(tenant_name, gender, co_tenants or []), s["body"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "für den oben genannten Abrechnungszeitraum ergibt sich folgender ausstehender Betrag:",
        s["body"]
    ))
    story.append(Spacer(1, 16))

    # ── Outstanding amount box ─────────────────────────────────────
    lbl_style  = ParagraphStyle("_ml", fontName="Helvetica",      fontSize=9,  leading=13, alignment=TA_CENTER, textColor=C_MUTED)
    amt_style  = ParagraphStyle("_ma", fontName="Helvetica-Bold", fontSize=26, leading=30, alignment=TA_CENTER, textColor=C_RED)
    due_style  = ParagraphStyle("_md", fontName="Helvetica",      fontSize=9,  leading=13, alignment=TA_CENTER, textColor=C_MUTED)

    amt_cell = [
        Paragraph("Offener Betrag", lbl_style),
        Spacer(1, 4),
        Paragraph(f"{amount:.2f} €", amt_style),
        Spacer(1, 4),
        Paragraph(f"Fällig bis: {due_str}", due_style),
    ]
    amt_t = Table([[amt_cell]], colWidths=[W])
    amt_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_REDBG),
        ("BOX",           (0, 0), (-1, -1), 1.5, C_RED),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(amt_t)
    story.append(Spacer(1, 18))

    # ── Body paragraphs ────────────────────────────────────────────
    story.append(Paragraph(
        f"Wir bitten Sie, den ausstehenden Betrag bis spätestens <b>{due_str}</b> "
        "auf das Ihnen bekannte Konto zu überweisen.",
        s["body"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Sollte die Zahlung bis zu diesem Datum nicht bei uns eingehen, sehen wir uns leider gezwungen, "
        "weitere rechtliche Schritte einzuleiten. Dies kann zusätzliche Kosten verursachen, "
        "die wir gerne vermeiden möchten.",
        s["body"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Falls Sie der Meinung sind, dass diese Erinnerung irrtümlich erfolgt ist, oder falls Sie Fragen "
        "zu Ihrem Zahlungsstand haben, stehen wir Ihnen gerne zur Verfügung.",
        s["body"]
    ))
    story.append(Spacer(1, 30))
    story.extend(_signature_block("Ihre Vermieter", signature_path, s))

    doc = SimpleDocTemplate(
        file, pagesize=A4, title=f"Mahnung_{tenant_name}",
        leftMargin=25*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm
    )
    doc.build(story)
    return file


# ── Balance Sheet Annual Report ────────────────────────────────────────────────

def balance_sheet_pdf(year, snapshot, props, landlord_name="Hausverwaltung"):
    """
    Generate a balance sheet annual report and return PDF bytes.

    year     : int  — the fiscal year
    snapshot : [{name, expected, costs, net}]  — current-month per-property figures
    props    : [{name, monthly_rows, tot_expected, tot_actual, tot_costs,
                 flat_rows, insights}]
    """
    import io as _io
    import re as _re

    buf = _io.BytesIO()
    s   = _styles()
    today_str = date.today().strftime("%d.%m.%Y")
    story     = []

    recv_key = f"Received {year} (€)"
    coll_key = f"Collection {year} (%)"

    # ── Cell helpers ──────────────────────────────────────────────────────────
    def _ph(text, right=False, bold=False, color=None, size=9):
        fn  = "Helvetica-Bold" if bold else "Helvetica"
        clr = colors.HexColor(color) if color else C_TEXT
        aln = TA_RIGHT if right else TA_LEFT
        return Paragraph(str(text), ParagraphStyle(
            "_ph", fontName=fn, fontSize=size,
            leading=int(size * 1.4), textColor=clr, alignment=aln,
        ))

    def _net_cell(val, size=9):
        clr = "#27ae60" if val >= 0 else "#e74c3c"
        return _ph(f"{val:+,.2f} €", right=True, bold=True, color=clr, size=size)

    def _eur_cell(val, size=9):
        return _ph(f"{val:,.2f} €", right=True, size=size)

    hdr   = ParagraphStyle("_h",  fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=C_WHITE)
    hdr_r = ParagraphStyle("_hr", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=C_WHITE, alignment=TA_RIGHT)

    # ── Header banner ─────────────────────────────────────────────────────────
    story.append(_header_banner(
        f"JAHRESABSCHLUSS {year}",
        f"Finanzbericht  ·  Erstellt am {today_str}",
        landlord_name,
        today_str,
    ))
    story.append(_accent_line(C_BLUE))
    story.append(Spacer(1, 22))

    # ═════════════════════════════════════════════════════════════════════════
    # SECTION 1 — Current monthly snapshot
    # ═════════════════════════════════════════════════════════════════════════
    story.append(_section_header(1, "Aktueller Monatsüberblick", s))
    story.append(Spacer(1, 6))

    snap_rows = [[
        Paragraph("Objekt",         hdr),
        Paragraph("Soll-Miete (€)", hdr_r),
        Paragraph("Kosten (€)",     hdr_r),
        Paragraph("Netto (€)",      hdr_r),
    ]]
    for item in snapshot:
        snap_rows.append([
            _ph(item["name"], bold=True),
            _eur_cell(item["expected"]),
            _eur_cell(item["costs"]),
            _net_cell(item["net"]),
        ])
    total_exp  = sum(i["expected"] for i in snapshot)
    total_cost = sum(i["costs"]    for i in snapshot)
    total_net  = sum(i["net"]      for i in snapshot)
    snap_rows.append([
        _ph("Gesamt", bold=True),
        _ph(f"{total_exp:,.2f} €",  right=True, bold=True),
        _ph(f"{total_cost:,.2f} €", right=True, bold=True),
        _net_cell(total_net),
    ])

    snap_t = Table(snap_rows, colWidths=[200, 89, 89, 90])
    snap_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),   C_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -2),  [C_WHITE, C_LGRAY]),
        ("LINEBELOW",     (0, 0), (-1, -2),  0.4, C_MGRAY),
        ("BACKGROUND",    (0, -1),(-1, -1),  C_LBLUE),
        ("TOPPADDING",    (0, 0), (-1, -1),  7),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  7),
        ("LEFTPADDING",   (0, 0), (-1, -1),  10),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  10),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
    ]))
    story.append(snap_t)
    story.append(Spacer(1, 22))

    # ═════════════════════════════════════════════════════════════════════════
    # SECTIONS 2+ — Per-property annual detail
    # ═════════════════════════════════════════════════════════════════════════
    for sec_num, prop in enumerate(props, start=2):

        # ── Property section header ───────────────────────────────────────
        story.append(_section_header(sec_num, prop["name"], s))
        story.append(Spacer(1, 8))

        # ── Monthly table ─────────────────────────────────────────────────
        # Month | Soll | Ist | Diff | Kosten | S-Netto | I-Netto  (sum=468)
        mo_w = [68, 70, 70, 63, 60, 68, 69]

        mo_rows = [[
            Paragraph("Monat",       hdr),
            Paragraph("Soll (€)",    hdr_r),
            Paragraph("Ist (€)",     hdr_r),
            Paragraph("Diff. (€)",   hdr_r),
            Paragraph("Kosten (€)",  hdr_r),
            Paragraph("S-Netto (€)", hdr_r),
            Paragraph("I-Netto (€)", hdr_r),
        ]]
        for row in prop["monthly_rows"]:
            mo_rows.append([
                _ph(row["Month"]),
                _eur_cell(row["Expected rent (€)"]),
                _eur_cell(row["Actual received (€)"]),
                _net_cell(row["Variance (€)"]),
                _eur_cell(row["Costs (€)"]),
                _net_cell(row["Expected net (€)"]),
                _net_cell(row["Actual net (€)"]),
            ])
        te, ta, tc = prop["tot_expected"], prop["tot_actual"], prop["tot_costs"]
        mo_rows.append([
            _ph("Gesamt", bold=True),
            _ph(f"{te:,.2f} €", right=True, bold=True),
            _ph(f"{ta:,.2f} €", right=True, bold=True),
            _net_cell(ta - te),
            _ph(f"{tc:,.2f} €", right=True, bold=True),
            _net_cell(te - tc),
            _net_cell(ta - tc),
        ])

        mo_t = Table(mo_rows, colWidths=mo_w)
        mo_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),   C_NAVY),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2),  [C_WHITE, C_LGRAY]),
            ("LINEBELOW",     (0, 0), (-1, -2),  0.4, C_MGRAY),
            ("BACKGROUND",    (0, -1),(-1, -1),  C_LBLUE),
            ("TOPPADDING",    (0, 0), (-1, -1),  6),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  6),
            ("LEFTPADDING",   (0, 0), (-1, -1),  8),
            ("RIGHTPADDING",  (0, 0), (-1, -1),  8),
            ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
        ]))
        story.append(mo_t)
        story.append(Spacer(1, 12))

        # ── Annual metrics row (4 cards) ──────────────────────────────────
        net_act = ta - tc
        net_exp = te - tc
        nc = "#27ae60" if net_act >= 0 else "#e74c3c"
        dc = "#27ae60" if (ta - te) >= 0 else "#e74c3c"

        def _mc(label, value, sub=None, vc=None):
            lbl_s = ParagraphStyle("_mcl", fontName="Helvetica",      fontSize=7,  leading=10, textColor=C_MUTED)
            val_s = ParagraphStyle("_mcv", fontName="Helvetica-Bold", fontSize=10, leading=13,
                                   textColor=colors.HexColor(vc) if vc else C_TEXT)
            sub_s = ParagraphStyle("_mcs", fontName="Helvetica",      fontSize=7,  leading=10, textColor=C_MUTED)
            cells = [Paragraph(label, lbl_s), Paragraph(value, val_s)]
            if sub:
                cells.append(Paragraph(sub, sub_s))
            return cells

        metrics_row = [[
            _mc("Soll-Miete",    f"€ {te:,.2f}"),
            _mc("Ist-Einnahmen", f"€ {ta:,.2f}", sub=f"{ta - te:+.2f} € vs. Soll", vc=dc),
            _mc("Gesamtkosten",  f"€ {tc:,.2f}"),
            _mc("Netto (Ist)",   f"€ {net_act:,.2f}", sub=f"Soll: {net_exp:+.2f} €", vc=nc),
        ]]
        mt = Table(metrics_row, colWidths=[117, 117, 117, 117])
        mt.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_SECBG),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_MGRAY),
            ("INNERGRID",     (0, 0), (-1, -1), 0.5, C_MGRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(mt)
        story.append(Spacer(1, 14))

        # ── Per-flat breakdown table ──────────────────────────────────────
        if prop.get("flat_rows"):
            fl_hdr   = ParagraphStyle("_fh",  fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=C_WHITE)
            fl_hdr_r = ParagraphStyle("_fhr", fontName="Helvetica-Bold", fontSize=8, leading=10,
                                      textColor=C_WHITE, alignment=TA_RIGHT)

            # Flat|Type|Tenant|Rent/mo|Received|Costs/mo|Net/mo|Net/yr|Quote (sum=468)
            fl_w = [65, 37, 96, 44, 47, 44, 44, 47, 44]
            fl_rows = [[
                Paragraph("Wohnung",          fl_hdr),
                Paragraph("Typ",              fl_hdr),
                Paragraph("Mieter",           fl_hdr),
                Paragraph("Miete/Mo",         fl_hdr_r),
                Paragraph(f"Einnahm. {year}", fl_hdr_r),
                Paragraph("Kosten/Mo",        fl_hdr_r),
                Paragraph("Netto/Mo",         fl_hdr_r),
                Paragraph("Netto/Jahr",       fl_hdr_r),
                Paragraph("Quote",            fl_hdr_r),
            ]]
            for fr in prop["flat_rows"]:
                coll = fr.get(coll_key)
                if coll is not None:
                    coll_str = f"{coll:.0f}%"
                    coll_clr = ("#27ae60" if coll >= 95 else "#e74c3c" if coll < 80 else "#f39c12")
                else:
                    coll_str, coll_clr = "—", None

                ten = fr["Tenant(s)"]
                if len(ten) > 28:
                    ten = ten[:26] + "…"

                fl_rows.append([
                    _ph(fr["Flat"],                             bold=True,          size=8),
                    _ph(fr["Type"],                                                 size=8),
                    _ph(ten,                                                        size=8),
                    _ph(f"{fr['Rent / mo (€)']:,.2f}",         right=True,         size=8),
                    _ph(f"{fr.get(recv_key, 0):,.2f}",         right=True,         size=8),
                    _ph(f"{fr['Costs / mo (€)']:,.2f}",        right=True,         size=8),
                    _net_cell(fr["Net / mo (€)"],                                  size=8),
                    _net_cell(fr["Net / yr  (€)"],                                 size=8),
                    _ph(coll_str, right=True, bold=bool(coll_clr), color=coll_clr, size=8),
                ])

            fl_t = Table(fl_rows, colWidths=fl_w)
            fl_t.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0),   C_NAVY),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1),  [C_WHITE, C_LGRAY]),
                ("LINEBELOW",     (0, 0), (-1, -1),  0.4, C_MGRAY),
                ("TOPPADDING",    (0, 0), (-1, -1),  5),
                ("BOTTOMPADDING", (0, 0), (-1, -1),  5),
                ("LEFTPADDING",   (0, 0), (-1, -1),  5),
                ("RIGHTPADDING",  (0, 0), (-1, -1),  5),
                ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
            ]))
            story.append(Paragraph("Wohnungsübersicht", s["section"]))
            story.append(Spacer(1, 6))
            story.append(fl_t)
            story.append(Spacer(1, 14))

        # ── Performance insights ──────────────────────────────────────────
        if prop.get("insights"):
            story.append(Paragraph("Hinweise & Empfehlungen", s["section"]))
            story.append(Spacer(1, 6))
            _ins_bg = {
                "success": ("#eafaf1", "#27ae60"),
                "warning": ("#fef9e7", "#f39c12"),
                "error":   ("#fdf2f1", "#e74c3c"),
                "info":    ("#eaf4fc", "#3a7fc1"),
            }
            _ins_icon = {"success": "✓", "warning": "⚠", "error": "✗", "info": "ℹ"}
            for level, msg in prop["insights"]:
                bg, border = _ins_bg.get(level, ("#f8f9fa", "#8395a7"))
                icon       = _ins_icon.get(level, "·")
                xml_msg    = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', msg)
                ins_p = Paragraph(
                    f"{icon}  {xml_msg}",
                    ParagraphStyle("_ins", fontName="Helvetica", fontSize=8, leading=12, textColor=C_TEXT),
                )
                ins_t = Table([[ins_p]], colWidths=[W])
                ins_t.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor(bg)),
                    ("LINEBELOW",     (0, 0), (-1, -1), 0.5, colors.HexColor(border)),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                    ("TOPPADDING",    (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]))
                story.append(ins_t)
                story.append(Spacer(1, 3))
            story.append(Spacer(1, 6))

        story.append(HRFlowable(width="100%", thickness=0.5, color=C_MGRAY, spaceBefore=4, spaceAfter=14))

    # ── Closing signature ─────────────────────────────────────────────────────
    story.extend(_signature_block(landlord_name, None, s))

    # ── Build with page footer ────────────────────────────────────────────────
    def _page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColorRGB(0.514, 0.584, 0.655)
        pw = A4[0]
        canvas.drawString(25 * mm, 10 * mm, f"Jahresabschluss {year}  ·  {landlord_name}")
        canvas.drawRightString(pw - 20 * mm, 10 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        title=f"Jahresabschluss_{year}",
        leftMargin=25 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()
