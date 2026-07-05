"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Payment, Contract } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { ConfirmButton } from "@/components/confirm-button";
import { Trash2, Calendar } from "lucide-react";

const FOREIGN_CURRENCIES = ["CNY", "USD", "GBP"];
const CURRENCY_SYMBOLS: Record<string, string> = { EUR: "€", CNY: "¥", USD: "$", GBP: "£" };

// The tender note shown next to a EUR amount when the tenant paid in another
// currency, e.g. "(paid ¥5655)". Empty when the payment was made in EUR.
function foreignNote(p: { orig_amount?: number | null; orig_currency?: string | null }) {
  if (!p.orig_currency || p.orig_amount == null) return "";
  return `paid ${CURRENCY_SYMBOLS[p.orig_currency] || p.orig_currency}${p.orig_amount.toFixed(2)}`;
}

function currentYearMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function RentTrackingPage() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [selectedContract, setSelectedContract] = useState<Contract | null>(null);
  const [form, setForm] = useState({ amount: 0, payment_date: new Date().toISOString().split("T")[0], paidForeign: false, orig_amount: 0, orig_currency: "CNY" });
  const [monthFilter, setMonthFilter] = useState(currentYearMonth());

  const { data: contracts = [] } = useQuery<Contract[]>({
    queryKey: ["contracts-all"],
    queryFn: () => api.get("/api/contracts/").then((r) => r.data),
  });

  const { data: allPayments = [], isLoading } = useQuery<Payment[]>({
    queryKey: ["payments"],
    queryFn: () => api.get("/api/payments/").then((r) => r.data),
  });

  // Filter payments for the selected month
  const monthPayments = allPayments.filter((p) => p.payment_date.startsWith(monthFilter));

  // Per-currency totals for the month
  const monthTotals = monthPayments.reduce((acc, p) => {
    const curr = p.currency || "EUR";
    acc[curr] = (acc[curr] || 0) + p.amount;
    return acc;
  }, {} as Record<string, number>);

  const displayContracts = showInactive ? contracts : contracts.filter((c) => !c.terminated);

  const add = useMutation({
    mutationFn: (data: { contract_id: number; amount: number; payment_date: string; orig_amount?: number | null; orig_currency?: string | null }) =>
      api.post("/api/payments/", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payments"] });
      toast.success("Payment recorded");
      setAddOpen(false);
    },
    onError: () => toast.error("Failed to record payment"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/payments/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["payments"] });
      toast.success("Payment deleted");
    },
  });

  function openAdd() {
    setSelectedContract(null);
    setForm({ amount: 0, payment_date: new Date().toISOString().split("T")[0], paidForeign: false, orig_amount: 0, orig_currency: "CNY" });
    setAddOpen(true);
  }

  function handleContractSelect(contractId: string) {
    const c = contracts.find((c) => String(c.id) === contractId) || null;
    setSelectedContract(c);
    if (c) setForm((f) => ({ ...f, amount: c.rent }));
  }

  // Build month options (current year ±1)
  const monthOptions = [];
  const now = new Date();
  for (let i = -12; i <= 3; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleString("en", { month: "long", year: "numeric" });
    monthOptions.push({ val, label });
  }

  return (
    <div className="max-w-5xl">
      <PageHeader title="Rent Tracking" action={{ label: "Add Payment", onClick: openAdd }} />

      {/* Monthly overview */}
      <Card className="mb-4">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Calendar className="size-4" /> Monthly Overview
            </CardTitle>
            <Select value={monthFilter} onValueChange={setMonthFilter}>
              <SelectTrigger className="w-44 h-8 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {monthOptions.map((m) => <SelectItem key={m.val} value={m.val}>{m.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {Object.keys(monthTotals).length === 0 ? (
            <p className="text-sm text-muted-foreground">No payments recorded for this month.</p>
          ) : (
            <div className="flex gap-6 mb-3">
              {Object.entries(monthTotals).map(([curr, total]) => (
                <div key={curr}>
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Total {curr}</p>
                  <p className="text-2xl font-semibold">{CURRENCY_SYMBOLS[curr] || curr} {total.toFixed(2)}</p>
                </div>
              ))}
            </div>
          )}
          {monthPayments.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Apartment</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {monthPayments.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="text-muted-foreground">{p.payment_date}</TableCell>
                    <TableCell className="font-medium">{p.tenant_name}</TableCell>
                    <TableCell className="text-muted-foreground">{p.apartment_name}</TableCell>
                    <TableCell className="text-right font-mono">
                      {p.amount.toFixed(2)} EUR
                      {foreignNote(p) && <span className="block text-xs text-muted-foreground">({foreignNote(p)})</span>}
                    </TableCell>
                    <TableCell>
                      <ConfirmButton onConfirm={() => remove.mutate(p.id)} title="Delete payment?" message={`Delete the ${p.amount.toFixed(2)} EUR payment from ${p.payment_date}?`}>
                        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive">
                          <Trash2 className="size-4" />
                        </Button>
                      </ConfirmButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* All payments table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">All Payments</CardTitle>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Tenant</TableHead>
              <TableHead>Apartment</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-10">Loading…</TableCell></TableRow>
            ) : allPayments.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-10">No payments yet.</TableCell></TableRow>
            ) : (
              allPayments.slice(0, 200).map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="text-muted-foreground">{p.payment_date}</TableCell>
                  <TableCell className="font-medium">{p.tenant_name}</TableCell>
                  <TableCell className="text-muted-foreground">{p.apartment_name}</TableCell>
                  <TableCell className="text-right font-mono">
                    {p.amount.toFixed(2)} EUR
                    {foreignNote(p) && <span className="block text-xs text-muted-foreground">({foreignNote(p)})</span>}
                  </TableCell>
                  <TableCell>
                    <ConfirmButton onConfirm={() => remove.mutate(p.id)} title="Delete payment?" message={`Delete the ${p.amount.toFixed(2)} EUR payment from ${p.payment_date}?`}>
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive">
                        <Trash2 className="size-4" />
                      </Button>
                    </ConfirmButton>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      {/* Add payment dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Payment</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Contract</Label>
              <div className="flex items-center gap-2 mb-1">
                <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
                  <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} className="accent-primary" />
                  Show inactive contracts
                </label>
              </div>
              <Select onValueChange={handleContractSelect}>
                <SelectTrigger><SelectValue placeholder="Select tenant / contract" /></SelectTrigger>
                <SelectContent>
                  {displayContracts.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.tenant_name} — {c.apartment_name} {c.terminated ? "(inactive)" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {selectedContract && selectedContract.terminated && (
              <p className="text-xs text-amber-400">⚠ This is an inactive/terminated contract.</p>
            )}
            <div className="space-y-1.5">
              <Label>Amount (EUR)</Label>
              <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: Number(e.target.value) }))} />
              <p className="text-xs text-muted-foreground">The EUR value that counts as income. Defaults to the contract rent.</p>
            </div>
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.paidForeign} onChange={(e) => setForm((f) => ({ ...f, paidForeign: e.target.checked }))} className="accent-primary" />
                Tenant paid in another currency
              </label>
              {form.paidForeign && (
                <div className="grid grid-cols-2 gap-4 pt-1">
                  <div className="space-y-1.5">
                    <Label>Paid amount</Label>
                    <Input type="number" step="0.01" value={form.orig_amount || ""} placeholder="e.g. 5655" onChange={(e) => setForm((f) => ({ ...f, orig_amount: Number(e.target.value) }))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Currency</Label>
                    <Select value={form.orig_currency} onValueChange={(v) => setForm((f) => ({ ...f, orig_currency: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{FOREIGN_CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <p className="col-span-2 text-xs text-muted-foreground -mt-1">Recorded as a note only — the {form.orig_currency} amount is never added into EUR totals.</p>
                </div>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>Payment Date</Label>
              <Input type="date" value={form.payment_date} onChange={(e) => setForm((f) => ({ ...f, payment_date: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button
              onClick={() => selectedContract && add.mutate({
                contract_id: selectedContract.id, amount: form.amount, payment_date: form.payment_date,
                orig_amount: form.paidForeign ? form.orig_amount : null,
                orig_currency: form.paidForeign ? form.orig_currency : null,
              })}
              disabled={!selectedContract || !form.amount || !form.payment_date || add.isPending}
            >
              {add.isPending ? "Saving…" : "Record Payment"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
