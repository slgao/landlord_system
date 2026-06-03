import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path


def send_reminder_email(
    smtp_host, smtp_port, smtp_user, smtp_password,
    from_addr, to_addr,
    tenant_name, landlord_name,
    overdue_months, total_due,
    pdf_path=None,
    use_tls=True,
):
    """
    Send a payment reminder email to a tenant.

    overdue_months: list of dicts with keys 'month', 'expected', 'paid', 'gap'
    pdf_path:       optional path to attach the Mahnung PDF
    """
    msg = MIMEMultipart()
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg["Subject"] = "Zahlungserinnerung – ausstehende Mietzahlung"

    month_lines = "\n".join(
        f"  • {m['month']}: {m['gap']:.2f} € ausstehend "
        f"(erwartet {m['expected']:.2f} €, erhalten {m['paid']:.2f} €)"
        for m in overdue_months
    )

    body = f"""Sehr geehrte/r {tenant_name},

wir möchten Sie darauf hinweisen, dass für die folgenden Monate noch keine vollständige Mietzahlung eingegangen ist:

{month_lines}

Gesamtbetrag ausstehend: {total_due:.2f} €

Wir bitten Sie, den ausstehenden Betrag so bald wie möglich auf das Ihnen bekannte Konto zu überweisen.

Sollten Sie die Zahlung bereits veranlasst haben, bitten wir Sie, diese Nachricht zu ignorieren.

Bei Rückfragen stehen wir Ihnen gerne zur Verfügung.

Mit freundlichen Grüßen
{landlord_name}"""

    msg.attach(MIMEText(body, "plain", "utf-8"))

    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=Path(pdf_path).name)
            part["Content-Disposition"] = f'attachment; filename="{Path(pdf_path).name}"'
            msg.attach(part)

    with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, to_addr, msg.as_string())
