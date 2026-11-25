"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { DashboardStats, ContractAlert, NKDashboard, FlatInsights } from "@/lib/types";
import Link from "next/link";
import { eur, fmtDate, resultLabel } from "@/components/nk-settlements";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SetupChecklist } from "@/components/setup-checklist";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, DoorOpen, TrendingUp, Wallet } from "lucide-react";
import {
  ComposedChart, Bar, Line, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import { C, fmtAxis } from "@/components/chart";
import { money, money0, signed } from "@/lib/fmt";

const currentYear = new Date().getFullYear();
const thisMonthKey = new Date().toLocaleString("en", { month: "short", year: "numeric" });

/** A headline figure. The dashboard used to count properties, apartments,
 *  tenants and contracts — four numbers that are each already the headline of
 *  their own page, barely move, and answer none of the questions a landlord
 *  opens the app with. These answer them. */
function StatCard({ title, value, icon: Icon, note, tone, href, label }: {
  title: string; value: string; icon: React.ElementType; note?: React.ReactNode;
  tone?: "good" | "bad"; href?: string; label?: string;
}) {
  // The card-wide link is an overlay covering the card rather than a wrapper
  // around it, because a note can carry links of its own — one per job on the
  // "Needs doing" card — and an <a> inside an <a> is not valid HTML. Those
  // paint above the overlay (`relative z-10` where they are written), so the
  // whole card area clicks through to `href` and a clicked part of the
  // breakdown wins over it.
  return (
    <Card className={`relative ${href ? "transition-colors hover:border-foreground/20" : ""}`}>
      {href && (
        <Link href={href} aria-label={label ?? title} className="absolute inset-0 rounded-lg" />
      )}
      <CardContent className="flex items-center justify-between p-5">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground uppercase tracking-wide">{title}</p>
          <p className={`text-2xl font-semibold mt-0.5 tabular-nums whitespace-nowrap ${
            tone === "good" ? "text-emerald-600 dark:text-emerald-400"
            : tone === "bad" ? "text-destructive" : ""}`}>{value}</p>
          {/* Wrapped, not truncated: the note is the sentence that explains
              the figure, and "408 € is Tilgu…" explains nothing. Two lines at
              most, so the four cards keep a common height. */}
          {note && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2 text-pretty">
              {note}
            </p>
          )}
        </div>
        <div className="size-10 shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
          <Icon className="size-5 text-primary" />
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// The cashflow chart's own parts
// ─────────────────────────────────────────────────────────────────────────────

/** The rent that was due, drawn as a mark across the month's bar.
 *
 *  A bullet-chart target: the bar is what arrived, the mark is what should
 *  have. Reaching the mark means the month was paid in full, and falling
 *  short shows the shortfall as a gap rather than as a difference the reader
 *  has to compute between two adjacent bars. Recharts hands a Scatter point
 *  its centre already placed on the category and on the value, which is what
 *  keeps the mark over the bar it belongs to. */
function TargetMark({ cx, cy, payload, half = 11 }: any) {
  if (cx == null || cy == null || !payload?.Expected) return null;
  // A month paid in full puts the mark inside its own bar, where ink on ink
  // disappears; one that fell short puts it on the card. So the mark takes
  // the colour that contrasts with whichever it landed on.
  const inside = payload.Received >= payload.Expected;
  return (
    <line x1={cx - half} x2={cx + half} y1={cy} y2={cy}
      stroke={inside ? "hsl(var(--background))" : "hsl(var(--foreground))"}
      strokeOpacity={inside ? 0.85 : 0.6} strokeWidth={1.5} strokeDasharray="3 2" />
  );
}

/** What the three marks mean, named beside the title.
 *
 *  Out here rather than in a legend strip under the plot: a legend sits where
 *  the eye has already left, and Recharts orders it by series rather than by
 *  how the chart is read. */
function CashflowKey() {
  const items: [string, React.ReactNode][] = [
    ["rent received", <span key="a" className="inline-block size-2.5 rounded-[2px]"
      style={{ background: C.actual }} />],
    ["costs", <span key="b" className="inline-block size-2.5 rounded-[2px]"
      style={{ background: C.costs, opacity: 0.85 }} />],
    ["rent due", <svg key="c" width="16" height="8" aria-hidden>
      <line x1="1" x2="15" y1="4" y2="4" stroke="currentColor" strokeOpacity={0.5}
        strokeWidth="1.5" strokeDasharray="3 2" /></svg>],
    ["what was left", <svg key="d" width="16" height="8" aria-hidden>
      <line x1="1" x2="15" y1="4" y2="4" stroke="currentColor" strokeWidth="1.5" /></svg>],
  ];
  return (
    <>
      {items.map(([label, mark]) => (
        <span key={label} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          {mark}{label}
        </span>
      ))}
    </>
  );
}

/** The month's figures, in the direction a reader thinks in.
 *
 *  Costs are held as negatives so they draw below the line; showing them that
 *  way too would read as a refund, so the sign goes back here. */
function CashflowTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const short = d.Expected - d.Received;
  const rows: [string, string, string][] = [
    ["Rent due", money(d.Expected), "text-muted-foreground"],
    ["Rent received", money(d.Received),
      short > 0.5 ? "text-amber-700 dark:text-amber-400" : "text-primary"],
    ["Costs", money(Math.abs(d.Costs)), "text-destructive"],
  ];
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 shadow-md">
      <p className="text-xs font-medium mb-1.5">{d.fullMonth}</p>
      <table className="text-xs">
        <tbody>
          {rows.map(([label, value, cls]) => (
            <tr key={label}>
              <td className="pr-4 text-muted-foreground">{label}</td>
              <td className={`text-right font-mono tabular-nums ${cls}`}>{value}</td>
            </tr>
          ))}
          <tr className="border-t border-border">
            <td className="pr-4 pt-1">Left</td>
            <td className="text-right font-mono tabular-nums pt-1 font-medium">{signed(d.Net)}</td>
          </tr>
        </tbody>
      </table>
      {short > 0.5 && (
        <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-1.5">
          {money(short)} short of the rent due
        </p>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats } = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.get("/api/dashboard/stats").then((r) => r.data),
  });
  const { data: alerts } = useQuery<ContractAlert[]>({
    queryKey: ["dashboard-alerts"],
    queryFn: () => api.get("/api/dashboard/alerts").then((r) => r.data),
  });
  // One request: the server picks what needs doing soon — a deadline inside
  // four months or just missed — and the settlements still open either way.
  const { data: nk } = useQuery<NKDashboard>({
    queryKey: ["nk-dashboard"],
    queryFn: () => api.get("/api/nk-settlements/dashboard").then((r) => r.data),
  });
  const nkDue = nk?.pending ?? [];
  const nkOpen = nk?.open_settlements ?? [];
  const { data: bs } = useQuery({
    queryKey: ["balance-sheet-dash", currentYear],
    queryFn: () => api.get(`/api/reports/balance-sheet/${currentYear}`).then((r) => r.data),
  });
  // The money. Fetched in parallel with the rest — chaining these on the
  // server costs more than it saves, since the page then waits for the sum of
  // them rather than the slowest.
  const { data: ins } = useQuery<FlatInsights>({
    queryKey: ["flat-insights"],
    queryFn: () => api.get("/api/insights/flats").then((r) => r.data),
  });
  const m = ins?.summary;
  const allFlats = ins?.flats ?? [];
  const vacant = allFlats.filter((f) => f.vacant_rooms > 0);
  const owing = allFlats.filter((f) => f.arrears > 0);
  const warnings = ins?.warnings ?? [];
  // Across everything let out, not just the flats you own: a sublet standing
  // empty still costs the rent you pay its owner, so counting only owned
  // rooms would have said "7 of 7 let" beside a flat flagged as empty.
  const rooms = allFlats.reduce((t, f) => t + f.rooms, 0);
  const letRooms = allFlats.reduce((t, f) => t + f.let_rooms, 0);
  const vacantCost = vacant.reduce(
    (t, f) => t + f.costs_monthly + f.rent_to_owner_monthly + f.instalment_monthly, 0);

  // What the "Needs doing" card counts, each piece paired with the page that
  // piece is actually done on: a Mahnung is written on Payment Reminders, an
  // Abrechnung on NK Settlements, a mortgage or ownership conflict is resolved
  // on Flat Economics, and the expiring contracts are listed further down this
  // very page.
  const todo = [
    { n: owing.length, href: "/payment-reminders",
      label: `${owing.length} in arrears` },
    { n: nkDue.length, href: "/nk-settlements",
      label: `${nkDue.length} Abrechnung${nkDue.length === 1 ? "" : "en"} due` },
    { n: alerts?.length ?? 0, href: "#contract-alerts",
      label: `${alerts?.length ?? 0} contract${alerts?.length === 1 ? "" : "s"}` },
    { n: warnings.length, href: "/flat-economics",
      label: `${warnings.length} to check` },
  ].filter((t) => t.n > 0);

  // Build monthly chart data from balance sheet
  const chartData = (() => {
    const props = bs?.properties || [];
    if (!props[0]?.monthly_rows) return [];
    const months = props[0].monthly_rows.map((r: any) => r["Month"]);
    return months.map((month: string) => {
      let exp = 0, act = 0, costs = 0;
      for (const p of props) {
        const row = p.monthly_rows.find((r: any) => r["Month"] === month);
        if (row) { exp += row["Expected rent (€)"] || 0; act += row["Actual received (€)"] || 0; costs += row["Costs (€)"] || 0; }
      }
      return {
        // "Jan 2026" eleven times says the year eleven times; the title
        // already does. Only the month belongs on the axis.
        month: String(month).replace(/\s*\d{4}$/, ""),
        fullMonth: month,
        Expected: +exp.toFixed(0),
        Received: +act.toFixed(0),
        // Negative, because it is drawn below the line: money out. The
        // tooltip puts the sign back the way a reader expects it.
        Costs: -Math.abs(+costs.toFixed(0)),
        Net: +(act - costs).toFixed(0), // money in − money out
        isCurrent: month === thisMonthKey,
      };
    });
  })();

  // What the year comes to, for the figure that leads the card. The months
  // already elapsed are the ones with anything in them, so they are the ones
  // the average divides by — twelve would understate it for most of the year.
  const chartNet = chartData.reduce((a: number, d: any) => a + d.Net, 0);
  const chartMonths = chartData.length || 1;

  // Left to itself Recharts squares the domain off around zero, which here
  // reserved as much room below the line for costs that never reach it as
  // above for rent — half an empty plot. This fits the range to the figures
  // and then rounds out to a round number so the ticks stay readable.
  // A fixed-width target mark is fine on a desktop and wrong on a phone: at
  // 390px the months are 22px apart, so a 22px mark touches its neighbours
  // and eleven of them read as one long line across the chart — the opposite
  // of the per-month figure they are. So the mark is cut to the band it sits
  // in, which means measuring the plot.
  //
  // A callback ref rather than useRef + useEffect: the card is only rendered
  // once the figures have arrived, so on the mount the effect would run
  // against a node that does not exist yet and, with no dependency to bring
  // it back, would never measure anything at all.
  const observer = useRef<ResizeObserver | null>(null);
  const [plotWidth, setPlotWidth] = useState(0);
  const plotRef = useCallback((el: HTMLDivElement | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!el || typeof ResizeObserver === "undefined") return;
    setPlotWidth(el.getBoundingClientRect().width);
    observer.current = new ResizeObserver(([e]) => setPlotWidth(e.contentRect.width));
    observer.current.observe(el);
  }, []);
  useEffect(() => () => observer.current?.disconnect(), []);

  // 56 for the Y axis, 12 for the chart's own margins.
  const markHalf = plotWidth
    ? Math.max(4, Math.min(11, ((plotWidth - 68) / chartMonths) * 0.31))
    : 11;

  const { chartDomain, chartTicks } = (() => {
    if (!chartData.length) {
      return { chartDomain: [0, 0] as [number, number], chartTicks: [0] };
    }
    const hi = Math.max(0, ...chartData.map((d: any) => Math.max(d.Received, d.Expected)));
    const lo = Math.min(0, ...chartData.map((d: any) => d.Costs));
    // The bounds hug the figures. Rounding them out to the tick step first
    // is what left a quarter of the plot empty below costs that never got
    // near it; the ticks can be round without the edges having to be.
    const top = hi * 1.08;
    const bottom = lo * 1.08;
    // Then a round step for the labels, counted out from zero in both
    // directions — so the line the whole chart is read against is one of the
    // labelled ticks. Recharts divides a domain into equal parts wherever
    // they happen to fall, and left to it the zero line here went unnamed.
    const rough = (top - bottom) / 5;
    const mag = Math.pow(10, Math.floor(Math.log10(Math.max(rough, 1))));
    const step = [1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10].map((m) => m * mag)
      .find((v) => v >= rough) ?? 10 * mag;
    const ticks: number[] = [];
    for (let t = Math.ceil(bottom / step) * step; t <= top; t += step) {
      ticks.push(Math.round(t));
    }
    return { chartDomain: [bottom, top] as [number, number], chartTicks: ticks };
  })();

  // An account with no tenancy has no cashflow, no yield and nothing let, and
  // four dashes say less than one list of what to do first.
  const empty = !!stats && stats.properties === 0;
  const setupDone = !!stats && stats.contracts > 0 && allFlats.length > 0
    && (ins?.flats?.some((f) => f.rent_monthly > 0) ?? false);

  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-xl font-semibold">Dashboard</h1>

      {stats && !setupDone && (
        <SetupChecklist state={{
          properties: stats.properties,
          apartments: stats.apartments,
          tenants: stats.tenants,
          contracts: stats.contracts,
          payments: allFlats.reduce((t, f) => t + (f.rent_monthly > 0 ? 1 : 0), 0),
        }} />
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Cashflow" icon={Wallet} href="/flat-economics"
          value={m ? `${money0(m.cashflow_monthly)}/mo` : "—"}
          tone={m ? (m.cashflow_monthly < 0 ? "bad" : "good") : undefined}
          note={m ? `${money0(m.operating_monthly)} earned, ${money0(m.principal_monthly)} is Tilgung` : undefined}
        />
        {/* Net yield goes to Flat Economics, which has the per-flat gross and
            net yield this summarises. Valuation holds the values the yield is
            computed ON — m², €/m², debt, equity, LTV — but no yield at all. */}
        <StatCard
          title="Net yield" icon={TrendingUp} href="/flat-economics"
          value={m?.net_yield != null ? `${m.net_yield.toLocaleString("de-DE")} %` : "—"}
          note={m?.value ? `on ${money0(m.value)} across ${m.valued_flats} flats` : "set a comparable €/m²"}
        />
        <StatCard
          title="Let" icon={DoorOpen} href="/contracts"
          value={ins ? `${letRooms} of ${rooms}` : "—"}
          tone={vacant.length ? "bad" : undefined}
          note={vacant.length
            ? `${vacant.map((f) => f.property_name).join(", ")} — ${money0(vacantCost)}/mo`
            : rooms > 0 ? "every room let" : "no flats recorded yet"}
        />
        {/* Four unrelated jobs add up to this one number, and each is done on a
            different page, so every part of the breakdown links to where that
            job is done. The card area itself follows the first of them — the
            most pressing, since `todo` is built worst-first — so this card
            clicks like the other three rather than only on its text. */}
        <StatCard
          title="Needs doing" icon={AlertTriangle} href={todo[0]?.href}
          label={todo.length ? `Needs doing: ${todo[0].label}` : "Needs doing"}
          value={String(owing.length + nkDue.length + (alerts?.length ?? 0) + warnings.length)}
          tone={owing.length || nkDue.length ? "bad" : undefined}
          note={todo.length
            ? todo.map((t, i) => (
                <span key={t.href}>
                  {i > 0 && " · "}
                  <Link href={t.href}
                    className="relative z-10 hover:text-foreground hover:underline">
                    {t.label}
                  </Link>
                </span>
              ))
            : "nothing outstanding"}
        />
      </div>

      {/* The counts that used to headline this page. Each is the headline of
          its own page; here they are a reference line, not the story. */}
      {stats && (
        <p className="text-xs text-muted-foreground">
          <Link href="/properties" className="hover:text-foreground">{stats.properties} properties</Link>
          {" · "}
          <Link href="/apartments" className="hover:text-foreground">{stats.apartments} apartments</Link>
          {" · "}
          <Link href="/tenants" className="hover:text-foreground">{stats.tenants} tenants</Link>
          {" · "}
          <Link href="/contracts" className="hover:text-foreground">
            {stats.contracts} active contracts
          </Link>
          {stats.upcoming ? ` · ${stats.upcoming} starting soon` : ""}
        </p>
      )}

      {chartData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-end justify-between gap-4 flex-wrap">
              <div>
                <CardTitle className="text-sm font-medium">
                  In and out, month by month · {currentYear}
                </CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Rent above the line, costs below it; the line through them is
                  what was left.
                </p>
                <div className="flex items-center gap-4 flex-wrap mt-1.5">
                  <CashflowKey />
                </div>
              </div>
              {/* Right of the title on a desktop, under it once the header
                  wraps on a phone — otherwise the caption leaves its figure. */}
              <div className="text-left sm:text-right">
                <p className="text-2xl sm:text-3xl font-semibold leading-none">
                  {signed(Math.round(chartNet / chartMonths))}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  left per month on average
                </p>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div ref={plotRef}>
            <ResponsiveContainer width="100%" height={280}>
              {/* stackOffset="sign" is what sends the negative half below the
                  line; the default sums the stack instead, which draws the
                  costs on top of the rent and the whole point is lost. */}
              <ComposedChart data={chartData} margin={{ top: 10, right: 8, left: 4, bottom: 0 }}
                barCategoryGap="22%" stackOffset="sign">
                <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
                <XAxis dataKey="month" tickLine={false} axisLine={false} interval="preserveStartEnd"
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} width={56} tickFormatter={fmtAxis}
                  domain={chartDomain} ticks={chartTicks} allowDataOverflow={false}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                <Tooltip content={<CashflowTooltip />}
                  cursor={{ fill: "hsl(var(--accent))", opacity: 0.3 }} />
                {/* One stack per month, so rent and costs share a centre and
                    read as a single spine rather than as two neighbours: what
                    came in above the line, what went out below it, and the
                    gap between their ends is the month. */}
                <Bar dataKey="Received" name="Received" stackId="m" fill={C.actual}
                  maxBarSize={22} radius={[4, 4, 0, 0]} />
                <Bar dataKey="Costs" name="Costs" stackId="m" fill={C.costs}
                  fillOpacity={0.85} maxBarSize={22} radius={[0, 0, 4, 4]} />
                {/* The rent that was due, as a mark across the bar rather than
                    a second bar beside it: eleven near-identical grey slabs
                    spent a third of the ink repeating a number that barely
                    moves, and a bar short of its mark is read at a glance. */}
                <Scatter dataKey="Expected" name="Expected" isAnimationActive={false}
                  shape={<TargetMark half={markHalf} />} />
                <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1} />
                {/* Straight segments between the months: these are twelve
                    discrete figures, and a spline through them draws curves
                    where the books have none. */}
                <Line type="linear" dataKey="Net" name="Net" stroke={C.net} strokeWidth={1.5}
                  dot={{ r: 2, fill: C.net, strokeWidth: 0 }}
                  activeDot={{ r: 3.5 }} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {(nkDue.length > 0 || nkOpen.length > 0) && (
        <Card>
          <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm font-medium">Nebenkostenabrechnungen</CardTitle>
            <Link href="/nk-settlements" className="text-xs text-primary hover:underline">NK Settlements →</Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {nkDue.map((p) => (
              <div key={`d-${p.contract_id}-${p.year}`} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                <div>
                  <p className="text-sm font-medium">{p.tenant_name} · Abrechnung {p.year}</p>
                  <p className="text-xs text-muted-foreground">{p.apartment_name} · {p.property_name}</p>
                </div>
                <div className="text-right space-y-1">
                  <Badge variant={p.level === "missed" ? "destructive" : "secondary"}>
                    {p.level === "missed" ? `Deadline passed ${-p.days_remaining}d ago` : `Send within ${p.days_remaining}d`}
                  </Badge>
                  <p className="text-xs text-muted-foreground">{fmtDate(p.deadline)}</p>
                </div>
              </div>
            ))}
            {nkOpen.map((s) => (
              <div key={`o-${s.id}`} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                <div>
                  <p className="text-sm font-medium">{s.tenant_name} · {resultLabel(s.amount)}</p>
                  <p className="text-xs text-muted-foreground">{fmtDate(s.period_start)}–{fmtDate(s.period_end)}</p>
                </div>
                <p className="text-sm font-mono">
                  {s.amount > 0 ? "owes you " : "you owe "}{eur(Math.abs(s.open))}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card id="contract-alerts" className="scroll-mt-4">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Contract Alerts</CardTitle>
        </CardHeader>
        <CardContent>
          {!alerts?.length ? (
            <p className="text-sm text-muted-foreground py-2">No contracts expiring or starting in the next 90 days.</p>
          ) : (
            <div className="space-y-2">
              {alerts.map((a, i) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <div>
                    <p className="text-sm font-medium">{a.tenant_name}</p>
                    <p className="text-xs text-muted-foreground">{a.apartment_name} · {a.property_name}</p>
                  </div>
                  <div className="text-right space-y-1">
                    <Badge
                      variant={a.level === "expired" ? "destructive" : "secondary"}
                      className={a.level === "upcoming" ? "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/20" : ""}
                    >
                      {a.level === "expired" ? `Expired ${Math.abs(a.days_remaining)}d ago`
                        : a.level === "upcoming" ? `Starts in ${a.days_remaining}d`
                        : `${a.days_remaining}d remaining`}
                    </Badge>
                    <p className="text-xs text-muted-foreground">
                      {a.level === "upcoming" ? a.start_date : a.end_date}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
