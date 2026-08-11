"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  ComposedChart, Bar, Line, Area, AreaChart, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import {
  Download, TrendingUp, TrendingDown, Wallet, Banknote, Receipt, Target, Landmark,
} from "lucide-react";
import { C, fmt, fmtAxis, ChartTooltip, ChartLegend } from "@/components/chart";

const currentYear = new Date().getFullYear();
const YEARS = Array.from({ length: 5 }, (_, i) => currentYear - i);

function MetricCard({
  label, value, sub, positive, icon: Icon,
}: {
  label: string; value: string; sub?: string; positive?: boolean;
  accent?: string; icon: any;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Icon className="size-3.5" />
          <p className="eyebrow">{label}</p>
        </div>
        <p className={`text-2xl font-mono font-medium mt-2 tabular-nums ${positive === true ? "text-primary" : positive === false ? "text-destructive" : ""}`}>
          {value}
        </p>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function StatRow({ label, value, dot, strong }: { label: string; value: string; dot?: string; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        {dot && <span className="size-2 rounded-full" style={{ background: dot }} />}
        {label}
      </span>
      <span className={`font-mono tabular-nums ${strong ? "text-base font-semibold" : "text-sm"}`}>{value}</span>
    </div>
  );
}

export default function BalanceSheetPage() {
  const [year, setYear] = useState(String(currentYear));
  const [downloading, setDownloading] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["balance-sheet", year],
    queryFn: () => api.get(`/api/reports/balance-sheet/${year}`).then((r) => r.data),
  });

  async function downloadPdf() {
    setDownloading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/reports/balance-sheet/${year}/pdf`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `Bilanz_${year}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } finally { setDownloading(false); }
  }

  const properties: any[] = data?.properties || [];
  const snapshot: any[] = data?.snapshot || [];
  const isCurrentYear = Number(year) === currentYear;
  const monthLabel = new Date().toLocaleString("en", { month: "long", year: "numeric" });

  // Current-month projection (snapshot reflects today's active contracts & costs).
  const curExpected = snapshot.reduce((s, p) => s + (p.expected || 0), 0);
  const curCosts = snapshot.reduce((s, p) => s + (p.costs || 0), 0);
  const curNet = curExpected - curCosts;

  // Build aggregate chart data across all properties.
  const allMonths = properties[0]?.monthly_rows?.map((r: any) => r["Month"]) || [];
  const thisMonthKey = new Date().toLocaleString("en", { month: "short", year: "numeric" }); // e.g. "Jun 2026"
  const aggregateChartData = allMonths.map((month: string) => {
    const entry: any = { month };
    let exp = 0, act = 0, cost = 0, netExp = 0, netAct = 0;
    for (const prop of properties) {
      const row = prop.monthly_rows.find((r: any) => r["Month"] === month);
      if (row) {
        exp += row["Expected rent (€)"] || 0;
        act += row["Actual received (€)"] || 0;
        cost += row["Costs (€)"] || 0;
        netExp += row["Expected net (€)"] || 0;
        netAct += row["Actual net (€)"] || 0;
      }
    }
    entry["Expected"] = +exp.toFixed(2);
    entry["Actual"] = +act.toFixed(2);
    entry["Costs"] = +cost.toFixed(2);
    entry["Expected net"] = +netExp.toFixed(2);
    entry["Net"] = +netAct.toFixed(2);
    entry.isCurrent = isCurrentYear && month === thisMonthKey;
    return entry;
  });

  const totalExpected = properties.reduce((s: number, p: any) => s + (p.tot_expected || 0), 0);
  const totalActual = properties.reduce((s: number, p: any) => s + (p.tot_actual || 0), 0);
  const totalCosts = properties.reduce((s: number, p: any) => s + (p.tot_costs || 0), 0);
  const totalNet = totalActual - totalCosts;

  // Financing (mortgages): rough remaining debt + interest/equity paid this year.
  const totalDebt = properties.reduce((s: number, p: any) => s + (p.debt_remaining || 0), 0);
  const totalInterest = properties.reduce((s: number, p: any) => s + (p.interest_paid || 0), 0);
  const totalEquity = properties.reduce((s: number, p: any) => s + (p.equity_paid || 0), 0);
  const totalInterestAcq = properties.reduce((s: number, p: any) => s + (p.interest_since_acq || 0), 0);
  const totalEquityAcq = properties.reduce((s: number, p: any) => s + (p.equity_since_acq || 0), 0);
  const hasFinancing = totalDebt > 0 || totalInterest > 0 || totalEquity > 0;

  return (
    <div className="max-w-6xl space-y-6">
      <PageHeader title="Balance Sheet">
        <Select value={year} onValueChange={setYear}>
          <SelectTrigger className="w-28 h-8 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>{YEARS.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
        </Select>
        <Button size="sm" onClick={downloadPdf} disabled={downloading || isLoading}>
          <Download className="size-4 mr-1" />
          {downloading ? "Generating…" : "PDF"}
        </Button>
      </PageHeader>

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : (
        <>
          {/* Current-month expected net — the headline figure */}
          {isCurrentYear && snapshot.length > 0 && (
            <Card className="overflow-hidden">
              <CardContent className="p-0">
                <div className="grid md:grid-cols-[1.3fr_1fr]">
                  <div className="p-6">
                    <p className="eyebrow">Expected net · {monthLabel}</p>
                    <p className={`text-[2.75rem] leading-tight font-mono font-medium mt-2 tabular-nums ${curNet >= 0 ? "text-primary" : "text-destructive"}`}>
                      {fmt(curNet)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Projected result this month if all contracted rent is collected.
                    </p>
                  </div>
                  <div className="p-6 border-t md:border-t-0 md:border-l border-border flex flex-col justify-center gap-3">
                    <StatRow label="Expected rent" value={fmt(curExpected)} dot={C.expected} />
                    <StatRow label="Recurring costs" value={`− ${fmt(curCosts)}`} dot={C.costs} />
                    <div className="h-px bg-border" />
                    <StatRow label="Expected net" value={fmt(curNet)} dot={C.net} strong />
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Annual summary metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard label="Expected Rent" value={fmt(totalExpected)} accent={C.expected} icon={Target} />
            <MetricCard label="Actual Received" value={fmt(totalActual)}
              sub={`${totalActual >= totalExpected ? "+" : ""}${(totalActual - totalExpected).toFixed(2)} vs expected`}
              positive={totalActual >= totalExpected} accent={C.actual} icon={Banknote} />
            <MetricCard label="Total Costs" value={fmt(totalCosts)} accent={C.costs} icon={Receipt} />
            <MetricCard label="Net (actual)" value={fmt(totalNet)} positive={totalNet >= 0} accent={C.net} icon={Wallet} />
          </div>

          {/* Financing summary — compact single-row strip (only when a mortgage exists) */}
          {hasFinancing && (
            <Card>
              <CardContent className="p-4 flex flex-wrap items-center gap-x-8 gap-y-2">
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Landmark className="size-3.5" />
                  <p className="eyebrow">Financing · {year}</p>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-xs text-muted-foreground">Remaining debt</span>
                  <span className="font-mono tabular-nums text-sm font-semibold text-destructive">{fmt(totalDebt)}</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-xs text-muted-foreground">Interest ({year})</span>
                  <span className="font-mono tabular-nums text-sm">{fmt(totalInterest)}</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-xs text-muted-foreground">Equity ({year})</span>
                  <span className="font-mono tabular-nums text-sm text-primary">{fmt(totalEquity)}</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-xs text-muted-foreground">Interest since purchase</span>
                  <span className="font-mono tabular-nums text-sm">{fmt(totalInterestAcq)}</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-xs text-muted-foreground">Equity since purchase</span>
                  <span className="font-mono tabular-nums text-sm text-primary">{fmt(totalEquityAcq)}</span>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Monthly income: expected target vs actual, with net line overlay */}
          {aggregateChartData.length > 0 && (
            <Card>
              <CardHeader className="pb-1">
                <CardTitle className="text-sm font-medium">Income vs Target · {year}</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={260}>
                  <ComposedChart data={aggregateChartData} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                    <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
                    <XAxis dataKey="month" tickLine={false} axisLine={false}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={fmtAxis}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: "hsl(var(--accent))", opacity: 0.35 }} />
                    <Legend content={<ChartLegend />} />
                    <Bar dataKey="Expected" name="Expected" fill={C.expected} fillOpacity={0.14} maxBarSize={34} />
                    <Bar dataKey="Actual" name="Actual" fill={C.actual} fillOpacity={0.9} maxBarSize={34} />
                    <Line type="monotone" dataKey="Net" name="Net" stroke={C.net} strokeWidth={1.5}
                      dot={false} activeDot={{ r: 3 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Net income trend: actual vs expected projection */}
          {aggregateChartData.length > 0 && (
            <Card>
              <CardHeader className="pb-1">
                <CardTitle className="text-sm font-medium">Net Income Trend</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={aggregateChartData} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                    <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
                    <XAxis dataKey="month" tickLine={false} axisLine={false}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={fmtAxis}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend content={<ChartLegend />} />
                    <ReferenceLine y={0} stroke="hsl(var(--border))" />
                    <Area type="monotone" dataKey="Net" name="Actual net" stroke={C.actual} strokeWidth={1.5}
                      fill={C.actual} fillOpacity={0.06} dot={false} activeDot={{ r: 3 }} />
                    <Line type="monotone" dataKey="Expected net" name="Expected net" stroke={C.expected}
                      strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Per-property breakdown */}
          {properties.map((prop: any) => {
            const chartData = prop.monthly_rows.map((r: any) => ({
              month: r["Month"],
              Expected: r["Expected rent (€)"],
              Actual: r["Actual received (€)"],
              Net: r["Actual net (€)"],
            }));
            const net = prop.tot_actual - prop.tot_costs;
            return (
              <Card key={prop.name}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium">{prop.name}</CardTitle>
                    <span className={`text-sm font-semibold tabular-nums ${net >= 0 ? "text-primary" : "text-destructive"}`}>
                      {net >= 0 ? <TrendingUp className="inline size-3.5 mr-1" /> : <TrendingDown className="inline size-3.5 mr-1" />}
                      {fmt(net)}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                    <span>Expected: {fmt(prop.tot_expected)}</span>
                    <span>Received: {fmt(prop.tot_actual)}</span>
                    <span>Costs: {fmt(prop.tot_costs)}</span>
                    {prop.debt_remaining > 0 && (
                      <span>Debt remaining: <span className="text-destructive">{fmt(prop.debt_remaining)}</span></span>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <ResponsiveContainer width="100%" height={170}>
                    <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                      <XAxis dataKey="month" tickLine={false} axisLine={false}
                        tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} />
                      <YAxis tickLine={false} axisLine={false} width={50} tickFormatter={fmtAxis}
                        tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "hsl(var(--accent))", opacity: 0.4 }} />
                      <Bar dataKey="Expected" name="Expected" fill={C.expected} fillOpacity={0.2}
                        stroke={C.expected} strokeOpacity={0.4} strokeDasharray="3 3" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="Actual" name="Actual" fill={C.actual} fillOpacity={0.85} radius={[3, 3, 0, 0]} maxBarSize={36} />
                    </ComposedChart>
                  </ResponsiveContainer>

                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Month</TableHead>
                        <TableHead className="text-right">Expected</TableHead>
                        <TableHead className="text-right">Received</TableHead>
                        <TableHead className="text-right">Variance</TableHead>
                        <TableHead className="text-right">Costs</TableHead>
                        <TableHead className="text-right">Net</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {prop.monthly_rows.map((row: any, i: number) => {
                        const variance = row["Variance (€)"];
                        const netRow = row["Actual net (€)"];
                        return (
                          <TableRow key={i}>
                            <TableCell className="text-muted-foreground">{row["Month"]}</TableCell>
                            <TableCell className="text-right font-mono">{row["Expected rent (€)"]?.toFixed(2)}</TableCell>
                            <TableCell className="text-right font-mono">{row["Actual received (€)"]?.toFixed(2)}</TableCell>
                            <TableCell className={`text-right font-mono ${variance < 0 ? "text-destructive" : variance > 0 ? "text-primary" : "text-muted-foreground"}`}>
                              {variance >= 0 ? "+" : ""}{variance?.toFixed(2)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-muted-foreground">{row["Costs (€)"]?.toFixed(2)}</TableCell>
                            <TableCell className={`text-right font-mono font-medium ${netRow >= 0 ? "text-primary" : "text-destructive"}`}>
                              {netRow?.toFixed(2)}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            );
          })}
        </>
      )}
    </div>
  );
}
