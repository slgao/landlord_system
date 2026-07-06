"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PaymentReminder } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, FileDown, History, Check } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PaymentRemindersPage() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<number | null>(null);
  const [generating, setGenerating] = useState<number | null>(null);
  const [settleDraft, setSettleDraft] = useState<Record<number, string>>({});

  const { data: reminders = [], isLoading } = useQuery<PaymentReminder[]>({
    queryKey: ["payment-reminders"],
    queryFn: () => api.get("/api/reports/payment-reminders").then((r) => r.data),
  });

  const { data: history = [] } = useQuery({
    queryKey: ["reminder-history"],
    queryFn: () => api.get("/api/reports/reminders/history").then((r) => r.data),
  });

  const settleRent = useMutation({
    mutationFn: (v: { contract_id: number; settled_until: string }) =>
      api.post(`/api/contracts/${v.contract_id}/settle-rent`, { settled_until: v.settled_until }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payment-reminders"] });
      toast.success("Updated — reminder recalculated");
    },
    onError: () => toast.error("Failed to update"),
  });

  const logReminder = useMutation({
    mutationFn: (r: PaymentReminder) => api.post("/api/reports/reminders", {
      contract_id: r.contract_id,
      sent_date: new Date().toISOString().split("T")[0],
      months_due: `${r.months_due} mo (${r.first_month}–${r.last_month})`,
      amount_due: r.amount_due,
      channel: "manual",
    }),
    onSuccess: () => toast.success("Reminder logged"),
    onError: () => toast.error("Failed to log reminder"),
  });

  async function generateMahnung(r: PaymentReminder) {
    setGenerating(r.contract_id);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API}/api/reports/mahnung/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          tenant_name: r.tenant_name,
          address: r.property_name,
          amount_due: r.amount_due,
          contract_id: r.contract_id,
        }),
      });
      if (!res.ok) { toast.error("Failed"); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `Mahnung_${r.tenant_name}.pdf`; a.click();
      URL.revokeObjectURL(url);
      await logReminder.mutateAsync(r);
    } finally { setGenerating(null); }
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Payment Reminders"
        description="Tenants whose total paid is less than total rent due over the tracked period"
      />

      <p className="text-xs text-muted-foreground mb-4">
        Reminders use a running balance: paying early or paying double one month to cover a
        missed month both net out. If old payments were never entered, expand a tenant and use{" "}
        <span className="font-medium">“Mark rent paid through”</span> to settle everything up to a
        date — only later months are then evaluated.
      </p>

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : reminders.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-muted-foreground">All tenants are up to date.</CardContent></Card>
      ) : (
        <div className="space-y-3">
          {reminders.map((r, i) => {
            const draft = settleDraft[r.contract_id] ?? r.settled_until ?? "";
            return (
            <Card key={r.contract_id}>
              <CardContent className="p-0">
                <div
                  className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/20"
                  onClick={() => setExpanded(expanded === i ? null : i)}
                >
                  <div className="flex items-center gap-3">
                    {expanded === i ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
                    <div>
                      <p className="font-medium">{r.tenant_name}</p>
                      <p className="text-sm text-muted-foreground">{r.apartment_name} · {r.property_name}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {r.settled_until && <Badge variant="secondary" className="hidden sm:inline-flex">settled ≤ {r.settled_until}</Badge>}
                    <Badge variant="destructive">{r.months_due} month{r.months_due !== 1 ? "s" : ""} due</Badge>
                    <span className="font-mono font-semibold text-destructive">{r.amount_due.toFixed(2)} {r.currency}</span>
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); generateMahnung(r); }}
                      disabled={generating === r.contract_id}>
                      <FileDown className="size-4 mr-1" />
                      {generating === r.contract_id ? "…" : "Mahnung"}
                    </Button>
                  </div>
                </div>

                {expanded === i && (
                  <div className="border-t border-border">
                    {/* Headline balance */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-4">
                      <div className="rounded-md bg-muted/40 p-2"><p className="text-[10px] text-muted-foreground uppercase tracking-wide">Rent / month</p><p className="text-sm font-semibold">{r.rent.toFixed(2)} {r.currency}</p></div>
                      <div className="rounded-md bg-muted/40 p-2"><p className="text-[10px] text-muted-foreground uppercase tracking-wide">Total due</p><p className="text-sm font-semibold">{r.expected_total.toFixed(2)}</p></div>
                      <div className="rounded-md bg-muted/40 p-2"><p className="text-[10px] text-muted-foreground uppercase tracking-wide">Total paid</p><p className="text-sm font-semibold text-emerald-400">{r.paid_total.toFixed(2)}</p></div>
                      <div className="rounded-md bg-muted/40 p-2"><p className="text-[10px] text-muted-foreground uppercase tracking-wide">Outstanding</p><p className="text-sm font-semibold text-destructive">{r.amount_due.toFixed(2)}</p></div>
                    </div>
                    {r.current_month_paid > 0 && (
                      <p className="px-4 -mt-2 pb-2 text-xs text-muted-foreground">
                        Includes {r.current_month_paid.toFixed(2)} {r.currency} paid this month (counted as credit).
                      </p>
                    )}

                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Month</TableHead>
                          <TableHead className="text-right">Expected</TableHead>
                          <TableHead className="text-right">Paid</TableHead>
                          <TableHead className="text-right">Running balance</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {r.months.map((m, j) => (
                          <TableRow key={j}>
                            <TableCell className="text-muted-foreground">{m.month}</TableCell>
                            <TableCell className="text-right font-mono">{m.expected.toFixed(2)}</TableCell>
                            <TableCell className={`text-right font-mono ${m.paid > 0 ? "text-emerald-400" : ""}`}>{m.paid.toFixed(2)}</TableCell>
                            <TableCell className={`text-right font-mono font-medium ${m.balance_after < -0.005 ? "text-destructive" : "text-muted-foreground"}`}>{m.balance_after.toFixed(2)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>

                    {/* Settle control */}
                    <div className="p-4 border-t border-border flex flex-wrap items-end gap-2">
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">Mark rent paid through (settles all months up to this date):</p>
                        <div className="flex items-center gap-2">
                          <Input
                            type="date"
                            className="h-8 w-40"
                            value={draft}
                            onChange={(e) => setSettleDraft((s) => ({ ...s, [r.contract_id]: e.target.value }))}
                          />
                          <Button size="sm" variant="outline"
                            disabled={!draft || settleRent.isPending}
                            onClick={() => settleRent.mutate({ contract_id: r.contract_id, settled_until: draft })}>
                            <Check className="size-4 mr-1" /> Apply
                          </Button>
                          {r.settled_until && (
                            <Button size="sm" variant="ghost" className="text-muted-foreground"
                              disabled={settleRent.isPending}
                              onClick={() => { setSettleDraft((s) => ({ ...s, [r.contract_id]: "" })); settleRent.mutate({ contract_id: r.contract_id, settled_until: "" }); }}>
                              Clear
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>

                    {r.tenant_email && (
                      <div className="p-4 text-sm text-muted-foreground border-t border-border">
                        Email on file: <a href={`mailto:${r.tenant_email}`} className="text-primary hover:underline">{r.tenant_email}</a>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
            );
          })}
        </div>
      )}
      {/* Reminder History */}
      {(history as any[]).length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-3 flex items-center gap-2">
            <History className="size-4" /> Reminder History
          </h2>
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Apartment</TableHead>
                  <TableHead>Months</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Channel</TableHead>
                  <TableHead>Note</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(history as any[]).map((h: any) => (
                  <TableRow key={h.id}>
                    <TableCell className="text-muted-foreground">{h.sent_date}</TableCell>
                    <TableCell className="font-medium">{h.tenant_name}</TableCell>
                    <TableCell className="text-muted-foreground">{h.apartment_name}</TableCell>
                    <TableCell className="text-muted-foreground">{h.months_due}</TableCell>
                    <TableCell className="text-right font-mono">{h.amount_due?.toFixed(2)}</TableCell>
                    <TableCell><span className="capitalize text-xs bg-muted px-2 py-0.5 rounded">{h.channel}</span></TableCell>
                    <TableCell className="text-muted-foreground text-sm">{h.note || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}
    </div>
  );
}
