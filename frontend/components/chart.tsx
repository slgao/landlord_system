import { money } from "@/lib/fmt";

// Shared chart styling primitives so the Dashboard and Balance Sheet charts
// stay visually consistent: cohesive palette, currency formatting, and a
// custom tooltip/legend whose swatches resolve a solid colour by series key
// (gradient-filled bars expose a url(#…) fill that isn't a valid CSS colour).

// Kontobuch palette — resolves to CSS vars so charts follow the light/dark
// ledger theme. Disciplined and near-monochrome: a faint grey-green target,
// solid seal for what's real, a brighter seal for the running net, and the
// accounting red reserved for costs/negatives.
export const C = {
  expected: "hsl(var(--muted-foreground))",
  actual: "hsl(var(--primary))",
  costs: "hsl(var(--destructive))",
  net: "hsl(var(--foreground))", // quiet ink line — the bottom line
  // Financing: interest burned vs principal repaid. `interest` is deliberately
  // NOT `costs` — accounting red against the pine `actual` is the one pair
  // protanopes cannot separate, so the orange carries that job on charts where
  // the two sit side by side. See --chart-interest in globals.css.
  interest: "hsl(var(--chart-interest))",
  principal: "hsl(var(--primary))",
};

export const SERIES_COLOR: Record<string, string> = {
  Expected: C.expected,
  Actual: C.actual,
  Received: C.actual,
  Costs: C.costs,
  Net: C.net,
  "Expected net": C.net,
  "Actual net": C.actual,
  Zins: C.interest,
  Interest: C.interest,
  Tilgung: C.principal,
  Principal: C.principal,
  Restschuld: C.net,
  "Debt remaining": C.net,
};

export const swatch = (key: string, fallback?: string) =>
  SERIES_COLOR[key] ?? fallback ?? C.expected;

// Chart figures follow the same conventions as the rest of the app (lib/fmt):
// a dot for thousands, a comma for decimals, the symbol after the figure.
// A tooltip reading €1,050.00 beside a table reading 1.050,00 € was the last
// place the two spellings still met.
export function fmt(n: number) {
  return money(n);
}

export function fmtAxis(n: number) {
  if (Math.abs(n) >= 1000) {
    const k = n / 1000;
    return `${k.toLocaleString("de-DE", { maximumFractionDigits: 1 })}k\u00A0€`;
  }
  return money(n, { cents: false });
}

export function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2">
      <p className="text-xs font-medium mb-1.5">{label}</p>
      <div className="space-y-1">
        {payload.map((p: any) => (
          <div key={p.dataKey} className="flex items-center justify-between gap-5 text-xs">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="size-2 rounded-full" style={{ background: swatch(p.dataKey, p.stroke) }} />
              {p.name}
            </span>
            <span className="font-mono font-medium tabular-nums">{fmt(p.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChartLegend({ payload }: any) {
  if (!payload?.length) return null;
  return (
    <div className="flex flex-wrap justify-center gap-4 pt-1">
      {payload.map((e: any) => (
        <span key={e.dataKey ?? e.value} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="size-2 rounded-full" style={{ background: swatch(e.dataKey, e.color) }} />
          {e.value}
        </span>
      ))}
    </div>
  );
}
