"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Amortization, AmortProperty, AmortRow } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { Banknote, Landmark, Percent, PiggyBank, CalendarCheck, Table2 } from "lucide-react";
import { C, fmt, fmtAxis, ChartTooltip, ChartLegend } from "@/components/chart";

const pct = (n: number) => `${n.toLocaleString("en-US", { maximumFractionDigits: 2 })} %`;

function MetricCard({ label, value, sub, icon: Icon, tone }: {
  label: string; value: string; sub?: string; icon: any; tone?: "interest" | "principal";
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Icon className="size-3.5" />
          <p className="eyebrow">{label}</p>
          {/* The swatch carries the series identity — the figure itself stays
              in ink, so the number is never legible by colour alone. */}
          {tone && (
            <span className="size-2 rounded-full shrink-0"
              style={{ background: tone === "interest" ? C.interest : C.principal }} />
          )}
        </div>
        <p className="text-2xl font-mono font-medium mt-2 tabular-nums">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

/** Recharts wants a string category for the x axis; the year is also the key
 *  the "today" reference line is drawn at, so both live on every row. */
function toChartRows(rows: AmortRow[]) {
  return rows.map((r) => ({
    year: String(r.year),
    Zins: r.interest,
    Tilgung: r.tilgung,
    Restschuld: r.balance_end,
  }));
}

function Charts({ rows, thisYear }: { rows: AmortRow[]; thisYear: number }) {
  const data = useMemo(() => toChartRows(rows), [rows]);
  const marker = data.some((d) => d.year === String(thisYear)) ? String(thisYear) : null;
  // A 30-year loan puts ~30 categories on the axis; let Recharts drop labels
  // rather than overlap them, but always keep the first and last year visible.
  const axis = {
    tick: { fill: "hsl(var(--muted-foreground))", fontSize: 11 },
    tickLine: false,
    axisLine: false,
  } as const;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Zins und Tilgung per year</CardTitle>
          <p className="text-xs text-muted-foreground">
            The bar height is the annual payment — it barely moves. What moves is the
            split inside it: every euro of Tilgung shrinks the balance, so next year
            less of the same payment is eaten by interest.
          </p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data} margin={{ top: 22, right: 8, left: 4, bottom: 0 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
              <XAxis dataKey="year" {...axis} minTickGap={18} />
              <YAxis {...axis} width={54} tickFormatter={fmtAxis} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "hsl(var(--accent))", opacity: 0.35 }} />
              <Legend content={<ChartLegend />} />
              {marker && (
                <ReferenceLine x={marker} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3"
                  label={{ value: "today", position: "top", offset: 8, fontSize: 10,
                           fill: "hsl(var(--muted-foreground))" }} />
              )}
              {/* stroke = the card surface: a hairline that keeps the two stacked
                  segments from bleeding into one another. */}
              <Bar dataKey="Zins" stackId="a" fill={C.interest} fillOpacity={0.9}
                stroke="hsl(var(--card))" strokeWidth={1} maxBarSize={26} />
              <Bar dataKey="Tilgung" stackId="a" fill={C.principal} fillOpacity={0.9}
                stroke="hsl(var(--card))" strokeWidth={1} maxBarSize={26} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Restschuld</CardTitle>
          <p className="text-xs text-muted-foreground">
            Outstanding debt at each year end. It falls slowly at first and then
            steeply — the mirror image of the shifting split on the left. A step
            upward means a further loan was drawn on the same property.
          </p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={data} margin={{ top: 22, right: 8, left: 4, bottom: 0 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
              <XAxis dataKey="year" {...axis} minTickGap={18} />
              <YAxis {...axis} width={54} tickFormatter={fmtAxis} />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: "hsl(var(--border))" }} />
              {marker && (
                <ReferenceLine x={marker} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3"
                  label={{ value: "today", position: "top", offset: 8, fontSize: 10,
                           fill: "hsl(var(--muted-foreground))" }} />
              )}
              {/* One series — the card title names it, so no legend box. */}
              <Area type="monotone" dataKey="Restschuld" stroke={C.net} strokeWidth={2}
                fill={C.net} fillOpacity={0.07} dot={false} activeDot={{ r: 4 }} />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}

function ScheduleTable({ rows, thisYear }: { rows: AmortRow[]; thisYear: number }) {
  return (
    <div className="max-h-[420px] overflow-auto">
      <Table>
        <TableHeader className="sticky top-0 bg-card">
          <TableRow>
            <TableHead>Year</TableHead>
            <TableHead className="text-right">
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: C.interest }} />Zins
              </span>
            </TableHead>
            <TableHead className="text-right">
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: C.principal }} />Tilgung
              </span>
            </TableHead>
            <TableHead className="text-right">Payment</TableHead>
            <TableHead className="text-right">Restschuld</TableHead>
            <TableHead className="text-right">Zins total</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.year} className={r.year === thisYear ? "bg-accent/40" : undefined}>
              <TableCell className="font-medium tabular-nums">{r.year}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">{fmt(r.interest)}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">{fmt(r.tilgung)}</TableCell>
              <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                {fmt(r.payment)}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums">{fmt(r.balance_end)}</TableCell>
              <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                {fmt(r.interest_cum)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function LoanTable({ p }: { p: AmortProperty }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          {p.mortgages.length > 1 ? `${p.mortgages.length} loans on this property` : "Loan terms"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Loan</TableHead>
              <TableHead>Start</TableHead>
              <TableHead className="text-right">Principal</TableHead>
              <TableHead className="text-right">Sollzins</TableHead>
              <TableHead className="text-right">Tilgung</TableHead>
              <TableHead className="text-right">Rate / month</TableHead>
              <TableHead className="text-right">Restschuld</TableHead>
              <TableHead className="text-right">Paid off</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {p.mortgages.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="font-medium">{m.label || `Loan #${m.id}`}</TableCell>
                <TableCell className="text-muted-foreground tabular-nums">{m.start_date}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{fmt(m.principal)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{pct(m.interest_rate_pct)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{pct(m.tilgung_rate_pct)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{fmt(m.monthly_payment)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{fmt(m.balance_now)}</TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">{m.paid_off_year}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export default function FinancingPage() {
  const [selected, setSelected] = useState<number | "all">("all");
  const [showTable, setShowTable] = useState(false);

  const { data, isLoading, isError } = useQuery<Amortization>({
    queryKey: ["amortization"],
    queryFn: async () => (await api.get("/api/tax/amortization")).data,
  });

  const props = data?.properties ?? [];
  const thisYear = new Date(data?.as_of ?? Date.now()).getFullYear();

  // "all" folds the portfolio into one timeline; otherwise a single property.
  const view = useMemo(() => {
    if (selected === "all") {
      if (!data?.totals) return null;
      return {
        name: "Whole portfolio",
        sub: `${props.length} propert${props.length === 1 ? "y" : "ies"} · ` +
             `${props.reduce((n, p) => n + p.mortgages.length, 0)} loans`,
        rows: data.totals.combined,
        ...data.totals,
      };
    }
    const p = props.find((x) => x.property_id === selected);
    if (!p) return null;
    return {
      name: p.property_name,
      sub: p.apartments.length
        ? `${p.apartments.length} flat${p.apartments.length === 1 ? "" : "s"}: ${p.apartments.join(", ")}`
        : "no flats recorded",
      rows: p.combined,
      ...p,
    };
  }, [selected, data, props]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Financing" description="Zins and Tilgung development for the financed flats" />
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Financing" description="Zins and Tilgung development for the financed flats" />
        <Card>
          <CardContent className="p-8 text-center text-sm text-destructive">
            Could not load the loan schedules. Reload the page, or check that the API is reachable.
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!props.length || !view) {
    return (
      <div className="space-y-6">
        <PageHeader title="Financing" description="Zins and Tilgung development for the financed flats" />
        <Card>
          <CardContent className="p-10 text-center">
            <div className="mx-auto flex size-11 items-center justify-center rounded-full bg-muted">
              <Landmark className="size-5 text-muted-foreground" />
            </div>
            <p className="mt-4 font-medium">No loans recorded</p>
            <p className="mx-auto mt-1.5 max-w-md text-sm text-muted-foreground">
              A property bought outright has nothing to amortise, so there is nothing to plot.
              Record a mortgage and this page fills in on its own: the Zins/Tilgung split year
              by year, the falling Restschuld, and the year each loan is paid off.
            </p>
            <Button asChild size="sm" variant="outline" className="mt-5">
              <Link href="/tax-setup">Add a loan in Tax Setup</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Financing"
        description="Zins and Tilgung development for the financed flats"
      />

      {/* Filters in one row above the charts. */}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={selected === "all" ? "default" : "outline"}
          onClick={() => setSelected("all")}>
          Whole portfolio
        </Button>
        {props.map((p) => (
          <Button key={p.property_id} size="sm"
            variant={selected === p.property_id ? "default" : "outline"}
            onClick={() => setSelected(p.property_id)}>
            {p.property_name}
          </Button>
        ))}
      </div>

      <div>
        <h2 className="text-lg font-medium">{view.name}</h2>
        <p className="text-xs text-muted-foreground">{view.sub}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Borrowed" value={fmt(view.principal_total)} icon={Banknote}
          sub="original principal" />
        <MetricCard label="Restschuld" value={fmt(view.balance_now)} icon={Landmark}
          sub={`as of ${data!.as_of}`} />
        <MetricCard label="Tilgung so far" value={fmt(view.tilgung_since_start)} icon={PiggyBank}
          tone="principal" sub="equity built" />
        <MetricCard label="Zins so far" value={fmt(view.interest_since_start)} icon={Percent}
          tone="interest" sub={`${fmt(view.interest_lifetime)} over the full term`} />
        <MetricCard label="Rate" value={fmt(view.monthly_payment)} icon={Banknote}
          sub="per month, all loans" />
        <MetricCard label="Paid off" value={String(view.paid_off_year)} icon={CalendarCheck}
          sub={`${view.paid_off_year - thisYear} years to go`} />
      </div>

      <Charts rows={view.rows} thisYear={thisYear} />

      <p className="text-xs text-muted-foreground">
        Projected from the loan terms as a standard Annuitätendarlehen at a constant
        rate — it assumes the Sollzins holds to payoff and knows nothing about
        Sondertilgungen or the end of a Zinsbindung. Check figures against your bank
        statements before using them in a tax return.
      </p>

      {selected !== "all" && <LoanTable p={props.find((x) => x.property_id === selected)!} />}

      <Card>
        <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm">Year-by-year schedule</CardTitle>
          <Button size="sm" variant="ghost" onClick={() => setShowTable((v) => !v)}>
            <Table2 className="size-3.5 mr-1.5" />
            {showTable ? "Hide" : "Show"}
          </Button>
        </CardHeader>
        {showTable && (
          <CardContent>
            <ScheduleTable rows={view.rows} thisYear={thisYear} />
          </CardContent>
        )}
      </Card>
    </div>
  );
}
