/**
 * How this app writes a number, a date and an area — in one place.
 *
 * It had three ways of writing money and two of writing a date, several of
 * them on screen at once: `1.050,00 €` on the dashboard, `1050.00 EUR` in the
 * contracts table, `€ 540.00` under flat costs; `31.12.2026` beside
 * `2024-05-01`. For a German landlord an ISO date in a table reads as a
 * database export and `1050.00 EUR` reads as unfinished.
 *
 * So: German conventions throughout — a dot for thousands, a comma for
 * decimals, the symbol after the figure with a non-breaking space before it
 * (DIN 5008), and dates as TT.MM.JJJJ.
 *
 * These take the value, never a pre-rounded string, so the rounding happens
 * once and in one way.
 */

const DE = "de-DE";
// A narrow no-break space would be typographically nicer, but it goes missing
// in a copied-and-pasted figure. The ordinary no-break space survives.
const NBSP = " ";

/** `1.050,00 €` — money, always with its cents. */
export function money(n: number | null | undefined, opts?: { cents?: boolean }): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const digits = opts?.cents === false ? 0 : 2;
  return `${n.toLocaleString(DE, { minimumFractionDigits: digits,
                                   maximumFractionDigits: digits })}${NBSP}€`;
}

/** `1.051 €` — a headline figure, where the cents are noise. */
export const money0 = (n: number | null | undefined) => money(n, { cents: false });

/** `+1.050,00 €` / `−1.050,00 €` — where the direction is the point.
 *  A real minus sign (U+2212), not a hyphen: it lines up with the digits. */
export function signed(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const body = money(Math.abs(n));
  return n < 0 ? `−${body}` : `+${body}`;
}

/** `5,05 %` — a rate. */
export function percent(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toLocaleString(DE, { minimumFractionDigits: digits,
                                   maximumFractionDigits: digits })}${NBSP}%`;
}

/** `62,5 m²` — an area. */
export function sqm(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toLocaleString(DE, { maximumFractionDigits: 2 })}${NBSP}m²`;
}

/** `01.05.2024` — a date the way it is written on a German letter.
 *  Parsed by hand rather than through Date, which would shift the day across
 *  a timezone for anyone east or west of the server. */
export function date(iso?: string | null): string {
  if (!iso || iso === "None") return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  if (!y || !m || !d) return String(iso);
  return `${d}.${m}.${y}`;
}

/** `Mai 2024` — a month, for period headings. */
export function month(iso?: string | null): string {
  if (!iso || iso === "None") return "—";
  const [y, m] = String(iso).slice(0, 7).split("-");
  if (!y || !m) return String(iso);
  const names = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                 "August", "September", "Oktober", "November", "Dezember"];
  return `${names[Number(m) - 1] ?? m} ${y}`;
}

/** `01.05.2024 – 30.04.2026`, or `seit 01.05.2024` when it is open-ended. */
export function period(from?: string | null, to?: string | null): string {
  if (from && to) return `${date(from)} – ${date(to)}`;
  if (from) return `seit ${date(from)}`;
  if (to) return `bis ${date(to)}`;
  return "—";
}

/** The number on its own, German-formatted — for an input's display value. */
export function num(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "";
  return n.toLocaleString(DE, { minimumFractionDigits: digits,
                                maximumFractionDigits: digits });
}
