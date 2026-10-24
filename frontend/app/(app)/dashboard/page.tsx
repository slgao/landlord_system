"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { DashboardStats, ContractAlert, NKDashboard, FlatInsights } from "@/lib/types";
import Link from "next/link";
import { eur, fmtDate, resultLabel } from "@/components/nk-settlements";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, DoorOpen, TrendingUp, Wallet } from "lucide-react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import { C, fmtAxis, ChartTooltip, ChartLegend } from "@/components/chart";

/** Whole euro — a headline figure does not need its cents. */
const eur0 = (n: number) => `${n.toLocaleString("de-DE", { maximumFractionDigits: 0 })} €`;

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
          <p className={`text-2xl font-semibold mt-0.5 tabular-nums ${
            tone === "good" ? "text-emerald-600 dark:text-emerald-400"
            : tone === "bad" ? "text-destructive" : ""}`}>{value}</p>
          {note && <p className="text-xs text-muted-foreground mt-0.5 truncate">{note}</p>}
        </div>
        <div className="size-10 shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
          <Icon className="size-5 text-primary" />
        </div>
      </CardContent>
    </Card>
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
        month,
        Expected: +exp.toFixed(0),
        Received: +act.toFixed(0),
        Costs: +costs.toFixed(0),
        Net: +(act - costs).toFixed(0), // money in − money out
        isCurrent: month === thisMonthKey,
      };
    });
  })();

  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-xl font-semibold">Dashboard</h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Cashflow" icon={Wallet} href="/flat-economics"
          value={m ? `${eur0(m.cashflow_monthly)}/mo` : "—"}
          tone={m ? (m.cashflow_monthly < 0 ? "bad" : "good") : undefined}
          note={m ? `${eur0(m.operating_monthly)} earned, ${eur0(m.principal_monthly)} is Tilgung` : undefined}
        />
        {/* Net yield goes to Flat Economics, which has the per-flat gross and
            net yield this summarises. Valuation holds the values the yield is
            computed ON — m², €/m², debt, equity, LTV — but no yield at all. */}
        <StatCard
          title="Net yield" icon={TrendingUp} href="/flat-economics"
          value={m?.net_yield != null ? `${m.net_yield.toLocaleString("de-DE")} %` : "—"}
          note={m?.value ? `on ${eur0(m.value)} across ${m.valued_flats} flats` : "set a comparable €/m²"}
        />
        <StatCard
          title="Let" icon={DoorOpen} href="/contracts"
          value={ins ? `${letRooms} of ${rooms}` : "—"}
          tone={vacant.length ? "bad" : undefined}
          note={vacant.length
            ? `${vacant.map((f) => f.property_name).join(", ")} — ${eur0(vacantCost)}/mo`
            : "every room let"}
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
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium">Monthly Overview {currentYear}</CardTitle>
            <p className="text-xs text-muted-foreground">Net line = Received − Costs</p>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
                <XAxis dataKey="month" tickLine={false} axisLine={false}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={fmtAxis}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "hsl(var(--accent))", opacity: 0.35 }} />
                <Legend content={<ChartLegend />} />
                <Bar dataKey="Expected" name="Expected" fill={C.expected} fillOpacity={0.14} maxBarSize={24} />
                <Bar dataKey="Received" name="Received" fill={C.actual} fillOpacity={0.9} maxBarSize={24} />
                <Bar dataKey="Costs" name="Costs" fill={C.costs} fillOpacity={0.85} maxBarSize={24} />
                <Line type="monotone" dataKey="Net" name="Net" stroke={C.net} strokeWidth={1.5}
                  dot={false} activeDot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
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
