import { useQueryClient } from "@tanstack/react-query";

// Formatting and cache helpers shared by the NK settlement and provider-bill
// components, kept here so neither has to import the other.

export const eur = (n: number) =>
  `${n.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;

/** "Nachzahlung 180,00 €" / "Guthaben 95,00 €" — the sign spelled out, since
 *  a bare −95 reads differently depending on whose side you are on. */
export function resultLabel(amount: number) {
  if (Math.abs(amount) < 0.005) return "Ausgeglichen";
  return amount > 0 ? `Nachzahlung ${eur(amount)}` : `Guthaben ${eur(-amount)}`;
}

export function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

// Every query a settlement change can move. Payments feed the arrears, the
// tax report and the balance sheet, so those go stale too.
export function invalidateSettlementViews(qc: ReturnType<typeof useQueryClient>) {
  for (const key of ["nk-overview", "nk-dashboard", "nk-settlements", "nk-pending",
                     "nk-unlinked-kaution", "payments",
                     "tenant-payments", "payment-reminders", "tax-report", "balance-sheet",
                     "balance-sheet-dash", "kaution-deductions", "kaution-overview",
                     "provider-bills"]) {
    qc.invalidateQueries({ queryKey: [key] });
  }
}

