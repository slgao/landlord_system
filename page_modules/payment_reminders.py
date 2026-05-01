import streamlit as st
import pandas as pd
from datetime import date
from db import fetch, execute, get_config, set_config, get_secret_config, set_secret_config
from logic import detect_overdue
from pdfgen import generate_mahnung
from utils.mailer import send_reminder_email
from pathlib import Path


# ── helpers ────────────────────────────────────────────────────────────────────

def _log_reminder(contract_id, months_due, amount_due, channel, note=""):
    execute(
        """INSERT INTO reminders (contract_id, sent_date, months_due, amount_due, channel, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (contract_id, str(date.today()),
         ", ".join(m["month"] for m in months_due),
         amount_due, channel, note)
    )


def _smtp_configured():
    return bool(get_config("smtp_host") and get_config("smtp_user") and get_secret_config("smtp_password"))


# ── main page ──────────────────────────────────────────────────────────────────

def show():
    st.header("Payment Reminders")

    # ── SMTP Settings (collapsed by default) ───────────────────────
    with st.expander("SMTP Settings", expanded=not _smtp_configured()):
        import os as _os
        _enc = "encrypted with FERNET_KEY" if _os.environ.get("FERNET_KEY") else "plaintext — set FERNET_KEY in .env to encrypt"
        st.caption(
            f"Credentials are stored in the app database ({_enc}). "
            "Use an app password (not your main account password) for Gmail/Outlook."
        )
        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input("SMTP host",
                                      value=get_config("smtp_host", "smtp.gmail.com"),
                                      key="cfg_smtp_host")
            smtp_user = st.text_input("SMTP username / email",
                                      value=get_config("smtp_user", ""),
                                      key="cfg_smtp_user")
            smtp_from = st.text_input("From address (shown to tenant)",
                                      value=get_config("smtp_from", ""),
                                      key="cfg_smtp_from")
        with col2:
            smtp_port = st.text_input("Port",
                                      value=get_config("smtp_port", "587"),
                                      key="cfg_smtp_port")
            smtp_pass = st.text_input("Password / App password",
                                      value=get_secret_config("smtp_password", ""),
                                      type="password", key="cfg_smtp_pass")
            landlord_name = st.text_input("Landlord name (in email signature)",
                                          value=get_config("landlord_name", "Ihr Vermieter"),
                                          key="cfg_landlord")

        if st.button("Save SMTP Settings", key="btn_save_smtp"):
            set_config("smtp_host",      smtp_host)
            set_config("smtp_port",      smtp_port)
            set_config("smtp_user",      smtp_user)
            set_secret_config("smtp_password", smtp_pass)
            set_config("smtp_from",      smtp_from)
            set_config("landlord_name",  landlord_name)
            st.success("Settings saved.")
            st.rerun()

    st.divider()

    # ── Overdue Detection ───────────────────────────────────────────
    months_back = st.number_input("Check last N months", min_value=1, max_value=24,
                                  value=3, key="months_back")
    overdue = detect_overdue(int(months_back))

    if not overdue:
        st.success("No overdue payments detected.")
    else:
        st.warning(f"{len(overdue)} contract(s) with outstanding payments.")

        # Summary table
        summary_rows = []
        for o in overdue:
            months_str = ", ".join(m["month"] for m in o["overdue_months"])
            summary_rows.append({
                "Tenant":          o["tenant"],
                "Apartment":       o["apartment"],
                "Overdue Months":  months_str,
                "Total Due (€)":   o["total_due"],
                "Email on file":   "Yes" if o["email"] else "No",
            })
        st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

        st.divider()

        # ── Send Reminder ───────────────────────────────────────────
        with st.expander("Send Reminder", expanded=True):
            overdue_labels = [f"{o['tenant']} — {o['apartment']} ({o['total_due']:.2f} €)"
                              for o in overdue]
            selected_idx = st.selectbox("Select contract", range(len(overdue)),
                                        format_func=lambda i: overdue_labels[i],
                                        key="reminder_select")
            selected = overdue[selected_idx]

            # Breakdown for selected contract
            st.markdown(f"**Overdue breakdown for {selected['tenant']}:**")
            breakdown = pd.DataFrame(selected["overdue_months"])
            breakdown.columns = ["Month", "Expected (€)", "Paid (€)", "Gap (€)"]
            st.dataframe(breakdown, hide_index=True)

            channel = st.radio("Reminder method",
                               ["Email (with Mahnung PDF)", "Manual (log only)"],
                               key="reminder_channel")

            # Email override address
            to_addr = selected["email"]
            if channel.startswith("Email"):
                to_addr = st.text_input(
                    "Send to email",
                    value=selected["email"],
                    help="Pre-filled from tenant record. Edit if needed.",
                    key="reminder_to"
                )

            note = st.text_input("Optional note (saved in history)", key="reminder_note")

            col_send, col_info = st.columns([1, 3])
            with col_send:
                send_btn = st.button("Send / Log Reminder", key="btn_send_reminder",
                                     type="primary")
            with col_info:
                if channel.startswith("Email") and not _smtp_configured():
                    st.warning("Configure SMTP settings above first.")
                elif channel.startswith("Email") and not to_addr:
                    st.warning("No email address — edit the tenant record or enter one above.")

            if send_btn:
                cid     = selected["contract_id"]
                months  = selected["overdue_months"]
                total   = selected["total_due"]
                pdf_path = None

                if channel.startswith("Email"):
                    if not _smtp_configured():
                        st.error("SMTP not configured.")
                    elif not to_addr:
                        st.error("No recipient email address.")
                    else:
                        # Generate Mahnung PDF
                        try:
                            tenant_info = fetch("""
                                SELECT t.name, t.gender FROM tenants t
                                JOIN contracts c ON c.tenant_id = t.id
                                WHERE c.id=? LIMIT 1
                            """, (cid,))
                            t_name  = tenant_info[0][0] if tenant_info else selected["tenant"]
                            t_gender = tenant_info[0][1] if tenant_info else "diverse"
                            address = fetch("""
                                SELECT p.address FROM contracts c
                                JOIN apartments a ON c.apartment_id = a.id
                                JOIN properties p ON a.property_id = p.id
                                WHERE c.id=? LIMIT 1
                            """, (cid,))
                            addr_str = address[0][0] if address else ""
                            sig_path = "pdf/signature.png"
                            pdf_path = generate_mahnung(
                                t_name, total, addr_str,
                                gender=t_gender,
                                signature_path=sig_path if Path(sig_path).exists() else None
                            )
                        except Exception as e:
                            st.warning(f"PDF generation failed ({e}), sending without attachment.")

                        try:
                            send_reminder_email(
                                smtp_host=get_config("smtp_host"),
                                smtp_port=get_config("smtp_port", "587"),
                                smtp_user=get_config("smtp_user"),
                                smtp_password=get_secret_config("smtp_password"),
                                from_addr=get_config("smtp_from") or get_config("smtp_user"),
                                to_addr=to_addr,
                                tenant_name=selected["tenant"],
                                landlord_name=get_config("landlord_name", "Ihr Vermieter"),
                                overdue_months=months,
                                total_due=total,
                                pdf_path=pdf_path,
                            )
                            _log_reminder(cid, months, total, "email", note)
                            st.success(f"Reminder sent to {to_addr}.")
                            if pdf_path:
                                with open(pdf_path, "rb") as f:
                                    st.download_button("Download Mahnung PDF", f,
                                                       file_name=Path(pdf_path).name)
                        except Exception as e:
                            st.error(f"Failed to send email: {e}")
                else:
                    _log_reminder(cid, months, total, "manual", note)
                    st.success(f"Manual reminder logged for {selected['tenant']}.")

    st.divider()

    # ── Reminder History ────────────────────────────────────────────
    with st.expander("Reminder History"):
        history = fetch("""
            SELECT r.id, t.name, a.name, r.sent_date, r.months_due,
                   r.amount_due, r.channel, r.note
            FROM reminders r
            JOIN contracts c ON r.contract_id = c.id
            JOIN tenants t ON c.tenant_id = t.id
            JOIN apartments a ON c.apartment_id = a.id
            ORDER BY r.sent_date DESC
        """)
        if history:
            df_hist = pd.DataFrame(history,
                                   columns=["ID", "Tenant", "Apartment", "Date",
                                            "Months", "Amount (€)", "Channel", "Note"])
            st.dataframe(df_hist, width="stretch", hide_index=True)
        else:
            st.info("No reminders sent yet.")
