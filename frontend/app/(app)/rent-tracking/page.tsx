"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { todayISO } from "@/lib/utils";
import { Payment, Contract, NKSettlement, PaymentKind } from "@/lib/types";
import { contractStatus, contractStatusSuffix, startsInLabel } from "@/lib/contract-status";
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
import { Badge } from "@/components/ui/badge";
import { eur, fmtDate, invalidateSettlementViews, resultLabel } from "@/components/nk-settlements";

const FOREIGN_CURRENCIES = ["CNY", "USD", "GBP"];
const CURRENCY_SYMBOLS: Record<string, string> = { EUR: "€", CNY: "¥", USD: "$", GBP: "£" };

// The tender note shown next to a EUR amount when the tenant paid in another
// currency, e.g. "(paid ¥5655)". Empty when the payment was made in EUR.
function foreignNote(p: { orig_amount?: number | null; orig_currency?: string | null }) {
  if (!p.orig_currency || p.orig_amount == null) return "";
  return `paid ${CURRENCY_SYMBOLS[p.orig_currency] || p.orig_currency}${p.orig_amount.toFixed(2)}`;
}

// Marks money that moved because of a Nebenkostenabrechnung, so it is not
// read as rent — it is not counted as rent anywhere else either.
function KindTag({ p }: { p: Payment }) {
  if (p.kind !== "nk_settlement") return null;
  return (
    <Badge variant="secondary" className="ml-2 text-[10px] px-1.5 py-0"
      title={p.amount < 0 ? "Nebenkosten refund to the tenant" : "Nebenkosten Nachzahlung from the tenant"}>
      NK {p.amount < 0 ? "refund" : "Nachzahlung"}
    </Badge>
  );
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
  const emptyForm = {
    amount: 0, payment_date: todayISO(), paidForeign: false, orig_amount: 0, orig_currency: "CNY",
    kind: "rent" as PaymentKind, settlementId: "", refund: false,
  };
  const [form, setForm] = useState(emptyForm);
  const [monthFilter, setMonthFilter] = useState(currentYearMonth());

  const { data: contracts = [] } = useQuery<Contract[]>({
    queryKey: ["contracts-all"],
    queryFn: () => api.get("/api/contracts/").then((r) => r.data),
  });

  const { data: allPayments = [], isLoading } = useQuery<Payment[]>({
    queryKey: ["payments"],
    queryFn: () => api.get("/api/payments/").then((r) => r.data),
  });

  const { data: contractSettlements = [] } = useQuery<NKSettlement[]>({
    queryKey: ["nk-settlements", selectedContract?.id],
    queryFn: () => api.get(`/api/nk-settlements/?contract_id=${selectedContract!.id}`).then((r) => r.data),
    enabled: addOpen && form.kind === "nk_settlement" && !!selectedContract,
  });

  // Filter payments for the selected month
  const monthPayments = allPayments.filter((p) => p.payment_date.startsWith(monthFilter));

  // Per-currency rent totals for the month. NK settlements are shown apart:
  // a Nachzahlung is not rent, and a refund would pull the rent total down.
  const monthTotals = monthPayments.reduce((acc, p) => {
    if (p.kind === "nk_settlement") return acc;
    const curr = p.currency || "EUR";
    acc[curr] = (acc[curr] || 0) + p.amount;
    return acc;
  }, {} as Record<string, number>);
  const monthSettlements = monthPayments
    .filter((p) => p.kind === "nk_settlement")
    .reduce((sum, p) => sum + p.amount, 0);
  const hasMonthSettlements = monthPayments.some((p) => p.kind === "nk_settlement");

  const displayContracts = showInactive ? contracts : contracts.filter((c) => !c.terminated);

  const add = useMutation({
    mutationFn: (data: {
      contract_id: number; amount: number; payment_date: string;
      orig_amount?: number | null; orig_currency?: string | null;
      kind: PaymentKind; settlement_id?: number | null;
    }) => api.post("/api/payments/", data),
    onSuccess: () => {
      invalidateSettlementViews(qc);
      toast.success("Payment recorded");
      setAddOpen(false);
    },
    onError: (e) => toast.error(errorMessage(e, "Failed to record payment")),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/payments/${id}`),
    onSuccess: () => {
      invalidateSettlementViews(qc);
      toast.success("Payment deleted");
    },
    onError: (e) => toast.error(errorMessage(e, "Could not delete the payment")),
  });

  function openAdd() {
    setSelectedContract(null);
    setForm(emptyForm);
    setAddOpen(true);
  }

  function handleContractSelect(contractId: string) {
    const c = contracts.find((c) => String(c.id) === contractId) || null;
    setSelectedContract(c);
    if (c) setForm((f) => ({ ...f, settlementId: "", amount: f.kind === "rent" ? c.rent : 0 }));
  }

  function setKind(kind: PaymentKind) {
    setForm((f) => ({
      ...f, kind, settlementId: "", refund: false, paidForeign: false,
      amount: kind === "rent" ? (selectedContract?.rent ?? 0) : 0,
    }));
  }

  // Picking the Abrechnung fills in what is still open on it, and which way.
  function pickSettlement(id: string) {
    const s = contractSettlements.find((x) => String(x.id) === id);
    setForm((f) => ({
      ...f, settlementId: id === "none" ? "" : id,
      ...(s ? { amount: Math.abs(s.open), refund: s.amount < 0 } : {}),
    }));
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
          {monthPayments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No payments recorded for this month.</p>
          ) : (
            <div className="flex gap-6 mb-3">
              {Object.entries(monthTotals).map(([curr, total]) => (
                <div key={curr}>
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Rent {curr}</p>
                  <p className="text-2xl font-semibold">{CURRENCY_SYMBOLS[curr] || curr} {total.toFixed(2)}</p>
                </div>
              ))}
              {hasMonthSettlements && (
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">NK settlements (net)</p>
                  <p className="text-2xl font-semibold text-muted-foreground">€ {monthSettlements.toFixed(2)}</p>
                </div>
              )}
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
                      {p.amount.toFixed(2)} EUR<KindTag p={p} />
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
                    {p.amount.toFixed(2)} EUR<KindTag p={p} />
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
              <Select value={selectedContract ? String(selectedContract.id) : ""} onValueChange={handleContractSelect}>
                <SelectTrigger><SelectValue placeholder="Select tenant / contract" /></SelectTrigger>
                <SelectContent>
                  {displayContracts.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.tenant_name} — {c.apartment_name}{contractStatusSuffix(c)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {selectedContract && selectedContract.terminated && (
              <p className="text-xs text-amber-400">⚠ This is an inactive/terminated contract.</p>
            )}
            {selectedContract && contractStatus(selectedContract) === "upcoming" && (
              <p className="text-xs text-sky-700 dark:text-sky-400">
                ⚠ This contract {startsInLabel(selectedContract.start_date)} ({selectedContract.start_date}) — no rent is due yet.
              </p>
            )}
            <div className="space-y-1.5">
              <Label>Type</Label>
              <div className="flex rounded-md border border-border overflow-hidden text-sm" role="radiogroup" aria-label="Payment type">
                {([["rent", "Rent"], ["nk_settlement", "NK settlement"]] as const).map(([k, label]) => (
                  <button key={k} type="button" role="radio" aria-checked={form.kind === k} onClick={() => setKind(k)}
                    className={`flex-1 px-2 py-1.5 transition-colors ${form.kind === k
                      ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:text-foreground"}`}>
                    {label}
                  </button>
                ))}
              </div>
              {form.kind === "nk_settlement" && (
                <p className="text-xs text-muted-foreground">
                  A Nachzahlung the tenant pays after a Nebenkostenabrechnung, or a Guthaben you pay back.
                  Kept out of rent arrears, and reported as Umlagen for tax.
                </p>
              )}
            </div>
            {form.kind === "nk_settlement" && selectedContract && (
              <div className="space-y-1.5">
                <Label>Abrechnung</Label>
                <Select value={form.settlementId || "none"} onValueChange={pickSettlement}>
                  <SelectTrigger aria-label="Abrechnung"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not linked</SelectItem>
                    {contractSettlements.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>
                        {fmtDate(s.period_start)}–{fmtDate(s.period_end)} · {resultLabel(s.amount)}
                        {s.status === "settled" ? " · settled" : ` · open ${eur(Math.abs(s.open))}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {contractSettlements.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    No settlement recorded for this contract. Record one under NK Settlements to track what is still open.
                  </p>
                )}
              </div>
            )}
            {form.kind === "nk_settlement" && (
              <div className="flex rounded-md border border-border overflow-hidden text-sm" role="radiogroup" aria-label="Direction">
                {([[false, "Tenant paid you"], [true, "You refunded the tenant"]] as const).map(([r, label]) => (
                  <button key={label} type="button" role="radio" aria-checked={form.refund === r}
                    onClick={() => setForm((f) => ({ ...f, refund: r }))}
                    className={`flex-1 px-2 py-1.5 transition-colors ${form.refund === r
                      ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:text-foreground"}`}>
                    {label}
                  </button>
                ))}
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Amount (EUR)</Label>
              <Input type="number" step="0.01" min="0" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: Math.abs(Number(e.target.value)) }))} />
              <p className="text-xs text-muted-foreground">
                {form.kind === "rent"
                  ? "The EUR value that counts as income. Defaults to the contract rent."
                  : "Enter it as a positive figure — the direction above decides the sign."}
              </p>
            </div>
            {form.kind === "rent" && <div className="space-y-1.5">
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
            </div>}
            <div className="space-y-1.5">
              <Label>Payment Date</Label>
              <Input type="date" value={form.payment_date} onChange={(e) => setForm((f) => ({ ...f, payment_date: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button
              onClick={() => selectedContract && add.mutate({
                contract_id: selectedContract.id,
                amount: form.kind === "nk_settlement" && form.refund ? -form.amount : form.amount,
                payment_date: form.payment_date,
                orig_amount: form.paidForeign ? form.orig_amount : null,
                orig_currency: form.paidForeign ? form.orig_currency : null,
                kind: form.kind,
                settlement_id: form.kind === "nk_settlement" && form.settlementId ? Number(form.settlementId) : null,
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
