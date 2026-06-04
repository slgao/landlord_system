// Shared chart styling primitives so the Dashboard and Balance Sheet charts
// stay visually consistent: cohesive palette, currency formatting, and a
// custom tooltip/legend whose swatches resolve a solid colour by series key
// (gradient-filled bars expose a url(#…) fill that isn't a valid CSS colour).

// Professional palette tuned for the dark indigo theme.
export const C = {
  expected: "#818cf8", // indigo-400
  actual: "#34d399",   // emerald-400
  costs: "#fb7185",    // rose-400
  net: "#fbbf24",      // amber-400
};

export const SERIES_COLOR: Record<string, string> = {
  Expected: C.expected,
  Actual: C.actual,
  Received: C.actual,
  Costs: C.costs,
  Net: C.net,
  "Expected net": C.net,
  "Actual net": C.actual,
};

export const swatch = (key: string, fallback?: string) =>
  SERIES_COLOR[key] ?? fallback ?? C.expected;

export function fmt(n: number) {
  return `€${(n ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtAxis(n: number) {
  if (Math.abs(n) >= 1000) return `€${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k`;
  return `€${n}`;
}

export function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-card/95 backdrop-blur px-3 py-2 shadow-xl">
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
