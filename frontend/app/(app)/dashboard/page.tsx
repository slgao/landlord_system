"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { DashboardStats, ContractAlert } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Building2, Home, Users, FileText } from "lucide-react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell,
} from "recharts";
import { C, fmtAxis, ChartTooltip, ChartLegend } from "@/components/chart";

const currentYear = new Date().getFullYear();
const thisMonthKey = new Date().toLocaleString("en", { month: "short", year: "numeric" });

function StatCard({ title, value, icon: Icon }: { title: string; value: number; icon: React.ElementType }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-5">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">{title}</p>
          <p className="text-3xl font-semibold mt-0.5">{value}</p>
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
        <StatCard title="Active Contracts" value={stats?.contracts ?? 0} icon={FileText} />
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
                <defs>
                  <linearGradient id="dashReceived" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={C.actual} stopOpacity={0.95} />
                    <stop offset="100%" stopColor={C.actual} stopOpacity={0.5} />
                  </linearGradient>
                  <linearGradient id="dashCosts" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={C.costs} stopOpacity={0.85} />
                    <stop offset="100%" stopColor={C.costs} stopOpacity={0.45} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis dataKey="month" tickLine={false} axisLine={false}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={fmtAxis}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "hsl(var(--accent))", opacity: 0.4 }} />
                <Legend content={<ChartLegend />} />
                <Bar dataKey="Expected" name="Expected" fill={C.expected} fillOpacity={0.22}
                  stroke={C.expected} strokeOpacity={0.5} strokeDasharray="3 3" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Received" name="Received" fill="url(#dashReceived)" radius={[4, 4, 0, 0]} maxBarSize={28}>
                  {chartData.map((d: any, i: number) => (
                    <Cell key={i} stroke={d.isCurrent ? C.actual : "transparent"} strokeWidth={d.isCurrent ? 2 : 0} />
                  ))}
                </Bar>
                <Bar dataKey="Costs" name="Costs" fill="url(#dashCosts)" radius={[4, 4, 0, 0]} maxBarSize={28} />
                <Line type="monotone" dataKey="Net" name="Net" stroke={C.net} strokeWidth={2}
                  dot={{ r: 2.5, fill: C.net, strokeWidth: 0 }} activeDot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Contract Alerts</CardTitle>
        </CardHeader>
        <CardContent>
          {!alerts?.length ? (
            <p className="text-sm text-muted-foreground py-2">No contracts expiring in the next 90 days.</p>
          ) : (
            <div className="space-y-2">
              {alerts.map((a, i) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <div>
                    <p className="text-sm font-medium">{a.tenant_name}</p>
                    <p className="text-xs text-muted-foreground">{a.apartment_name} · {a.property_name}</p>
                  </div>
                  <div className="text-right space-y-1">
                    <Badge variant={a.level === "expired" ? "destructive" : "secondary"}>
                      {a.level === "expired" ? `Expired ${Math.abs(a.days_remaining)}d ago` : `${a.days_remaining}d remaining`}
                    </Badge>
                    <p className="text-xs text-muted-foreground">{a.end_date}</p>
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
