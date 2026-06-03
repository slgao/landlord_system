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
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { Download, TrendingUp, TrendingDown } from "lucide-react";

const currentYear = new Date().getFullYear();
const YEARS = Array.from({ length: 5 }, (_, i) => currentYear - i);

function MetricCard({ label, value, sub, positive }: { label: string; value: string; sub?: string; positive?: boolean }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
        <p className={`text-2xl font-semibold mt-1 ${positive === true ? "text-emerald-400" : positive === false ? "text-destructive" : ""}`}>
          {value}
        </p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function fmt(n: number) { return `€ ${n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}` }

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

  // Build aggregate chart data across all properties
  const allMonths = properties[0]?.monthly_rows?.map((r: any) => r["Month"]) || [];
  const aggregateChartData = allMonths.map((month: string) => {
    const entry: any = { month };
    let totalExpected = 0, totalActual = 0, totalCosts = 0;
    for (const prop of properties) {
      const row = prop.monthly_rows.find((r: any) => r["Month"] === month);
      if (row) {
        totalExpected += row["Expected rent (€)"] || 0;
        totalActual += row["Actual received (€)"] || 0;
        totalCosts += row["Costs (€)"] || 0;
      }
    }
    entry["Expected"] = +totalExpected.toFixed(2);
    entry["Actual"] = +totalActual.toFixed(2);
    entry["Costs"] = +totalCosts.toFixed(2);
    entry["Net"] = +(totalActual - totalCosts).toFixed(2);
    return entry;
  });

  const totalExpected = properties.reduce((s: number, p: any) => s + (p.tot_expected || 0), 0);
  const totalActual = properties.reduce((s: number, p: any) => s + (p.tot_actual || 0), 0);
  const totalCosts = properties.reduce((s: number, p: any) => s + (p.tot_costs || 0), 0);
  const totalNet = totalActual - totalCosts;

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
          {/* Annual summary metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard label="Expected Rent" value={fmt(totalExpected)} />
            <MetricCard label="Actual Received" value={fmt(totalActual)}
              sub={`${totalActual >= totalExpected ? "+" : ""}${(totalActual - totalExpected).toFixed(2)} vs expected`}
              positive={totalActual >= totalExpected} />
            <MetricCard label="Total Costs" value={fmt(totalCosts)} />
            <MetricCard label="Net (actual)" value={fmt(totalNet)} positive={totalNet >= 0} />
          </div>

          {/* Monthly overview chart */}
          {aggregateChartData.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Monthly Overview {year}</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={aggregateChartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="month" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6 }} />
                    <Legend />
                    <Bar dataKey="Expected" fill="hsl(var(--muted-foreground))" opacity={0.6} />
                    <Bar dataKey="Actual" fill="hsl(var(--primary))" />
                    <Bar dataKey="Costs" fill="hsl(var(--destructive))" opacity={0.7} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Net trend line chart */}
          {aggregateChartData.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Net Income Trend</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={aggregateChartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="month" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6 }} />
                    <Line type="monotone" dataKey="Net" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
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
                    <span className={`text-sm font-semibold ${net >= 0 ? "text-emerald-400" : "text-destructive"}`}>
                      {net >= 0 ? <TrendingUp className="inline size-3.5 mr-1" /> : <TrendingDown className="inline size-3.5 mr-1" />}
                      {fmt(net)}
                    </span>
                  </div>
                  <div className="flex gap-6 text-xs text-muted-foreground">
                    <span>Expected: {fmt(prop.tot_expected)}</span>
                    <span>Received: {fmt(prop.tot_actual)}</span>
                    <span>Costs: {fmt(prop.tot_costs)}</span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <ResponsiveContainer width="100%" height={160}>
                    <BarChart data={chartData} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="month" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} />
                      <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} width={50} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6 }} />
                      <Bar dataKey="Expected" fill="hsl(var(--muted-foreground))" opacity={0.5} />
                      <Bar dataKey="Actual" fill="hsl(var(--primary))" />
                    </BarChart>
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
                            <TableCell className={`text-right font-mono ${variance < 0 ? "text-destructive" : variance > 0 ? "text-emerald-400" : "text-muted-foreground"}`}>
                              {variance >= 0 ? "+" : ""}{variance?.toFixed(2)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-muted-foreground">{row["Costs (€)"]?.toFixed(2)}</TableCell>
                            <TableCell className={`text-right font-mono font-medium ${netRow >= 0 ? "text-emerald-400" : "text-destructive"}`}>
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
