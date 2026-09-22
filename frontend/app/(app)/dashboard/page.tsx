"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { DashboardStats, ContractAlert, NKSettlement, PendingAbrechnung } from "@/lib/types";
import Link from "next/link";
import { eur, fmtDate, resultLabel } from "@/components/nk-settlements";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Building2, Home, Users, FileText } from "lucide-react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import { C, fmtAxis, ChartTooltip, ChartLegend } from "@/components/chart";

const currentYear = new Date().getFullYear();
const thisMonthKey = new Date().toLocaleString("en", { month: "short", year: "numeric" });

function StatCard({ title, value, icon: Icon, note }: { title: string; value: number; icon: React.ElementType; note?: string }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-5">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">{title}</p>
          <p className="text-3xl font-semibold mt-0.5">{value}</p>
          {note && <p className="text-xs text-sky-700 dark:text-sky-400 mt-0.5">{note}</p>}
        </div>
        <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center">
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
  const { data: nkPending = [] } = useQuery<PendingAbrechnung[]>({
    queryKey: ["nk-pending"],
    queryFn: () => api.get("/api/nk-settlements/pending").then((r) => r.data),
  });
  const { data: nkSettlements = [] } = useQuery<NKSettlement[]>({
    queryKey: ["nk-settlements"],
    queryFn: () => api.get("/api/nk-settlements/").then((r) => r.data),
  });
  // Only what needs doing soon: a deadline inside four months, one just
  // missed, or money still open either way.
  const nkDue = nkPending.filter((p) => p.days_remaining <= 120);
  const nkOpen = nkSettlements.filter((s) => s.status !== "settled");
  const { data: bs } = useQuery({
    queryKey: ["balance-sheet-dash", currentYear],
    queryFn: () => api.get(`/api/reports/balance-sheet/${currentYear}`).then((r) => r.data),
  });

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
        <StatCard title="Properties" value={stats?.properties ?? 0} icon={Building2} />
        <StatCard title="Apartments" value={stats?.apartments ?? 0} icon={Home} />
        <StatCard title="Tenants" value={stats?.tenants ?? 0} icon={Users} />
        <StatCard title="Active Contracts" value={stats?.contracts ?? 0} icon={FileText}
          note={stats?.upcoming ? `+${stats.upcoming} starting soon` : undefined} />
      </div>

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

      <Card>
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
