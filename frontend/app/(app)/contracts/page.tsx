"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Contract, Tenant, Apartment, CoTenant, KautionDeduction, KautionPayment } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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
import { Pencil, Trash2, Plus, Users, CreditCard, XCircle, RotateCcw, BarChart2, Check, X } from "lucide-react";

const CURRENCIES = ["EUR", "CNY", "USD", "GBP"];
const KAUTION_CATS = ["NK Nachzahlung", "Schaden", "Reinigung", "Mietrückstand", "Sonstiges"];

const CONTRACT_EMPTY = {
  tenant_id: 0, apartment_id: 0, rent: 0, currency: "EUR",
  start_date: "", end_date: "", terminated: false,
  kaution_amount: 0, kaution_currency: "EUR",
  kaution_paid_date: "", kaution_returned_date: "", kaution_returned_amount: 0,
};

export default function ContractsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"contracts" | "detail" | "kaution-overview">("contracts");
  const [kautionReturnForm, setKautionReturnForm] = useState({ date: new Date().toISOString().split("T")[0], amount: 0 });
  const [editing, setEditing] = useState<Contract | null>(null);
  const [form, setForm] = useState<typeof CONTRACT_EMPTY>(CONTRACT_EMPTY);
  const [showAll, setShowAll] = useState(false);
  const [selectedContract, setSelectedContract] = useState<Contract | null>(null);
  // Terminate dialog: which date to record as the contract's end date
  const [terminateTarget, setTerminateTarget] = useState<Contract | null>(null);
  const [terminateChoice, setTerminateChoice] = useState<"contract" | "today" | "custom">("contract");
  const [terminateCustom, setTerminateCustom] = useState("");

  // Co-tenant form
  const [ctForm, setCtForm] = useState({ name: "", gender: "diverse", email: "", in_contract: false });
  // Kaution deduction form
  const [kdForm, setKdForm] = useState({ date: new Date().toISOString().split("T")[0], amount: 0, category: "Sonstiges", reason: "" });
  // Kaution installment (payment) form + inline-edit state
  const [kpForm, setKpForm] = useState({ date: new Date().toISOString().split("T")[0], amount: 0, note: "" });
  const [editPay, setEditPay] = useState<{ id: number; date: string; amount: number; note: string } | null>(null);
  const [editDed, setEditDed] = useState<{ id: number; date: string; amount: number; category: string; reason: string } | null>(null);

  const { data: contracts = [], isLoading } = useQuery<Contract[]>({
    queryKey: ["contracts", showAll],
    queryFn: () => api.get(`/api/contracts/?active_only=${!showAll}`).then((r) => r.data),
  });
  const { data: tenants = [] } = useQuery<Tenant[]>({
    queryKey: ["tenants"], queryFn: () => api.get("/api/tenants/").then((r) => r.data),
  });
  const { data: apartments = [] } = useQuery<Apartment[]>({
    queryKey: ["apartments"], queryFn: () => api.get("/api/apartments/").then((r) => r.data),
  });
  const { data: coTenants = [] } = useQuery<CoTenant[]>({
    queryKey: ["co-tenants", selectedContract?.id],
    queryFn: () => api.get(`/api/co-tenants/?contract_id=${selectedContract!.id}`).then((r) => r.data),
    enabled: !!selectedContract,
  });
  const { data: kautionDeductions = [] } = useQuery<KautionDeduction[]>({
    queryKey: ["kaution-deductions", selectedContract?.id],
    queryFn: () => api.get(`/api/kaution-deductions/?contract_id=${selectedContract!.id}`).then((r) => r.data),
    enabled: !!selectedContract,
  });
  const { data: kautionPayments = [] } = useQuery<KautionPayment[]>({
    queryKey: ["kaution-payments", selectedContract?.id],
    queryFn: () => api.get(`/api/kaution-payments/?contract_id=${selectedContract!.id}`).then((r) => r.data),
    enabled: !!selectedContract,
  });

  const { data: kautionOverview = [] } = useQuery({
    queryKey: ["kaution-overview"],
    queryFn: () => api.get("/api/contracts/kaution-overview").then((r) => r.data),
    enabled: tab === "kaution-overview",
  });

  const terminate = useMutation({
    mutationFn: ({ id, end_date }: { id: number; end_date?: string }) =>
      api.post(`/api/contracts/${id}/terminate`, null, end_date ? { params: { end_date } } : undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["contracts"] }); toast.success("Contract terminated"); setTerminateTarget(null); },
  });

  const reopen = useMutation({
    mutationFn: (id: number) => api.post(`/api/contracts/${id}/reopen`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["contracts"] }); toast.success("Contract reopened"); },
  });

  const markKautionReturned = useMutation({
    mutationFn: () => api.post(`/api/contracts/${selectedContract!.id}/kaution-return`, kautionReturnForm),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["contracts"] }); toast.success("Kaution marked as returned"); },
  });

  const clearKautionReturn = useMutation({
    mutationFn: () => api.post(`/api/contracts/${selectedContract!.id}/kaution-return/clear`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["contracts"] }); toast.success("Kaution return cleared"); },
  });

  const save = useMutation({
    mutationFn: (data: typeof CONTRACT_EMPTY) => {
      const body = { ...data, end_date: data.end_date || null, kaution_paid_date: data.kaution_paid_date || null,
        kaution_returned_date: data.kaution_returned_date || null,
        kaution_amount: data.kaution_amount || null, kaution_returned_amount: data.kaution_returned_amount || null };
      return editing ? api.put(`/api/contracts/${editing.id}`, body) : api.post("/api/contracts/", body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["contracts"] }); toast.success(editing ? "Updated" : "Created"); setOpen(false); },
    onError: () => toast.error("Failed to save"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/contracts/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["contracts"] }); toast.success("Deleted"); },
  });

  const addCoTenant = useMutation({
    mutationFn: () => api.post("/api/co-tenants/", { ...ctForm, contract_id: selectedContract!.id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["co-tenants"] }); setCtForm({ name: "", gender: "diverse", email: "", in_contract: false }); toast.success("Co-tenant added"); },
  });

  const removeCoTenant = useMutation({
    mutationFn: (id: number) => api.delete(`/api/co-tenants/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["co-tenants"] }),
  });

  const addDeduction = useMutation({
    mutationFn: () => api.post("/api/kaution-deductions/", { ...kdForm, contract_id: selectedContract!.id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["kaution-deductions"] }); toast.success("Deduction added"); },
  });

  const removeDeduction = useMutation({
    mutationFn: (id: number) => api.delete(`/api/kaution-deductions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kaution-deductions"] }),
  });

  const updateDeduction = useMutation({
    mutationFn: (d: NonNullable<typeof editDed>) =>
      api.put(`/api/kaution-deductions/${d.id}`, {
        contract_id: selectedContract!.id, date: d.date, amount: d.amount,
        category: d.category, reason: d.reason || null,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["kaution-deductions"] }); setEditDed(null); toast.success("Deduction updated"); },
    onError: () => toast.error("Failed to update deduction"),
  });

  const addPayment = useMutation({
    mutationFn: () => api.post("/api/kaution-payments/", { ...kpForm, note: kpForm.note || null, contract_id: selectedContract!.id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["kaution-payments"] }); setKpForm({ date: new Date().toISOString().split("T")[0], amount: 0, note: "" }); toast.success("Installment added"); },
    onError: () => toast.error("Failed to add installment"),
  });

  const updatePayment = useMutation({
    mutationFn: (p: NonNullable<typeof editPay>) =>
      api.put(`/api/kaution-payments/${p.id}`, {
        contract_id: selectedContract!.id, date: p.date, amount: p.amount, note: p.note || null,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["kaution-payments"] }); setEditPay(null); toast.success("Installment updated"); },
    onError: () => toast.error("Failed to update installment"),
  });

  const removePayment = useMutation({
    mutationFn: (id: number) => api.delete(`/api/kaution-payments/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kaution-payments"] }),
  });

  function openCreate() { setEditing(null); setForm(CONTRACT_EMPTY); setOpen(true); }
  function openEdit(c: Contract) {
    setEditing(c);
    setForm({ tenant_id: c.tenant_id, apartment_id: c.apartment_id, rent: c.rent, currency: c.currency,
      start_date: c.start_date, end_date: c.end_date || "", terminated: c.terminated,
      kaution_amount: c.kaution_amount || 0, kaution_currency: c.kaution_currency,
      kaution_paid_date: c.kaution_paid_date || "", kaution_returned_date: c.kaution_returned_date || "",
      kaution_returned_amount: c.kaution_returned_amount || 0 });
    setOpen(true);
  }

  function openDetail(c: Contract) { setSelectedContract(c); setTab("detail"); }

  // Jump from the overview into a contract's detail (to record installments,
  // deductions or mark the deposit returned). The row may be a contract that
  // isn't in the current active-only list, so fetch it if needed.
  async function openContractById(id: number) {
    const found = contracts.find((c) => c.id === id);
    const c = found ?? (await api.get(`/api/contracts/${id}`)).data;
    openDetail(c);
  }

  const totalDeducted = kautionDeductions.reduce((s, d) => s + d.amount, 0);
  const kautionBalance = (selectedContract?.kaution_amount || 0) - totalDeducted;
  const installmentsPaid = kautionPayments.reduce((s, p) => s + p.amount, 0);
  // Legacy deposits (from old contracts) have no installments but a paid date,
  // which means the tenant paid the full deposit up front. Treat those as paid
  // in full so "Paid so far / Outstanding" isn't misleading.
  const legacyFullyPaid = kautionPayments.length === 0 && !!selectedContract?.kaution_paid_date;
  const totalPaid = legacyFullyPaid ? (selectedContract?.kaution_amount || 0) : installmentsPaid;
  const kautionOutstanding = (selectedContract?.kaution_amount || 0) - totalPaid;

  const statusColor = (c: Contract) => {
    if (c.terminated) return "bg-secondary text-secondary-foreground";
    if (c.end_date) {
      const days = Math.round((new Date(c.end_date).getTime() - Date.now()) / 86400000);
      if (days < 0) return "bg-destructive/15 text-destructive border-destructive/20";
      if (days <= 90) return "bg-amber-500/15 text-amber-400 border-amber-500/20";
    }
    return "bg-emerald-500/15 text-emerald-400 border-emerald-500/20";
  };

  return (
    <div className="max-w-5xl">
      {tab === "contracts" ? (
        <>
          <PageHeader title="Contracts" action={{ label: "New Contract", onClick: openCreate }}>
            <Button variant="outline" size="sm" onClick={() => setTab("kaution-overview")}>
              <BarChart2 className="size-4 mr-1" /> Kaution Overview
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Active only" : "Show all"}
            </Button>
          </PageHeader>
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Apartment</TableHead>
                  <TableHead>Rent</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-10">Loading…</TableCell></TableRow>
                ) : contracts.length === 0 ? (
                  <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-10">No contracts.</TableCell></TableRow>
                ) : (
                  contracts.map((c) => (
                    <TableRow key={c.id} className="cursor-pointer" onClick={() => openDetail(c)}>
                      <TableCell className="font-medium">{c.tenant_name}</TableCell>
                      <TableCell className="text-muted-foreground">{c.apartment_name}<br /><span className="text-xs">{c.property_name}</span></TableCell>
                      <TableCell>{c.rent.toFixed(2)} {c.currency}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{c.start_date}<br />{c.end_date || "open"}</TableCell>
                      <TableCell>
                        <Badge className={statusColor(c)}>{c.terminated ? "Terminated" : c.end_date && new Date(c.end_date) < new Date() ? "Expired" : "Active"}</Badge>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <div className="flex gap-1 justify-end">
                          <Button variant="ghost" size="icon" onClick={() => openEdit(c)}><Pencil className="size-4" /></Button>
                          {!c.terminated && (
                            <Button variant="ghost" size="icon" title="Terminate" onClick={() => {
                              setTerminateTarget(c);
                              setTerminateChoice(c.end_date ? "contract" : "today");
                              setTerminateCustom(c.end_date || new Date().toISOString().split("T")[0]);
                            }}>
                              <XCircle className="size-4 text-amber-400" />
                            </Button>
                          )}
                          {c.terminated && (
                            <Button variant="ghost" size="icon" title="Reopen" onClick={() => reopen.mutate(c.id)}>
                              <RotateCcw className="size-4 text-emerald-400" />
                            </Button>
                          )}
                          <ConfirmButton
                            onConfirm={() => remove.mutate(c.id)}
                            title="Delete contract?"
                            message={`Delete the contract for ${c.tenant_name}? This permanently removes its payments, co-tenants, and Kaution deductions.`}
                          >
                            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"><Trash2 className="size-4" /></Button>
                          </ConfirmButton>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Card>
        </>
      ) : tab === "detail" && selectedContract ? (
        // ── Detail view ──
        <>
          <PageHeader title={`${selectedContract?.tenant_name} — ${selectedContract?.apartment_name}`}>
            <Button variant="outline" size="sm" onClick={() => setTab("contracts")}>← Back</Button>
          </PageHeader>

          <div className="grid md:grid-cols-2 gap-4">
            {/* Kaution overview */}
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><CreditCard className="size-4" />Kaution</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div><p className="text-xs text-muted-foreground">Agreed amount</p><p className="font-semibold">{selectedContract?.kaution_amount?.toFixed(2) || "—"} {selectedContract?.kaution_currency}</p></div>
                  <div><p className="text-xs text-muted-foreground">Paid so far</p><p className="font-semibold text-emerald-400">{totalPaid.toFixed(2)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Outstanding</p><p className={`font-semibold ${kautionOutstanding <= 0.001 ? "text-emerald-400" : "text-amber-400"}`}>{kautionOutstanding.toFixed(2)}</p></div>
                </div>
                {legacyFullyPaid && (
                  <p className="text-xs text-muted-foreground -mt-1">
                    Marked paid in full on {selectedContract?.kaution_paid_date} (no installments recorded). Add installments below to track a Ratenzahlung instead.
                  </p>
                )}

                {/* Installments (Ratenzahlung) — deposit can be paid in parts */}
                <div className="space-y-2">
                  <p className="text-xs font-medium">Installments (Ratenzahlung)</p>
                  {kautionPayments.length > 0 && (
                    <Table>
                      <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Note</TableHead><TableHead className="text-right">Amount</TableHead><TableHead className="w-16" /></TableRow></TableHeader>
                      <TableBody>
                        {kautionPayments.map((p) => editPay?.id === p.id ? (
                          <TableRow key={p.id}>
                            <TableCell><Input type="date" className="h-7 text-xs" value={editPay.date} onChange={(e) => setEditPay({ ...editPay, date: e.target.value })} /></TableCell>
                            <TableCell><Input className="h-7 text-xs" placeholder="Note" value={editPay.note} onChange={(e) => setEditPay({ ...editPay, note: e.target.value })} /></TableCell>
                            <TableCell className="text-right"><Input type="number" step="0.01" className="h-7 text-xs w-24 ml-auto" value={editPay.amount || ""} onChange={(e) => setEditPay({ ...editPay, amount: Number(e.target.value) })} /></TableCell>
                            <TableCell className="flex gap-1">
                              <Button variant="ghost" size="icon" onClick={() => updatePayment.mutate(editPay)} disabled={!editPay.amount || updatePayment.isPending}><Check className="size-3 text-emerald-400" /></Button>
                              <Button variant="ghost" size="icon" onClick={() => setEditPay(null)}><X className="size-3" /></Button>
                            </TableCell>
                          </TableRow>
                        ) : (
                          <TableRow key={p.id}>
                            <TableCell className="text-muted-foreground">{p.date}</TableCell>
                            <TableCell className="text-muted-foreground text-xs">{p.note || "—"}</TableCell>
                            <TableCell className="text-right font-mono">{p.amount.toFixed(2)}</TableCell>
                            <TableCell className="flex gap-1">
                              <Button variant="ghost" size="icon" onClick={() => setEditPay({ id: p.id, date: p.date, amount: p.amount, note: p.note || "" })}><Pencil className="size-3" /></Button>
                              <ConfirmButton onConfirm={() => removePayment.mutate(p.id)} title="Delete installment?" message={`Delete the ${p.amount.toFixed(2)} installment?`}><Button variant="ghost" size="icon"><Trash2 className="size-3 text-destructive" /></Button></ConfirmButton>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                  <div className="flex gap-2">
                    <Input type="date" className="h-8 text-sm" value={kpForm.date} onChange={(e) => setKpForm((f) => ({ ...f, date: e.target.value }))} />
                    <Input type="number" step="0.01" className="h-8 text-sm w-28" placeholder="Amount" value={kpForm.amount || ""} onChange={(e) => setKpForm((f) => ({ ...f, amount: Number(e.target.value) }))} />
                    <Input className="h-8 text-sm" placeholder="Note (e.g. 1. Rate)" value={kpForm.note} onChange={(e) => setKpForm((f) => ({ ...f, note: e.target.value }))} />
                    <Button size="sm" onClick={() => addPayment.mutate()} disabled={!kpForm.amount || addPayment.isPending}><Plus className="size-4 mr-1" />Add</Button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm border-t border-border pt-3">
                  <div><p className="text-xs text-muted-foreground">Deducted</p><p className="font-semibold text-destructive">{totalDeducted.toFixed(2)}</p></div>
                  <div><p className="text-xs text-muted-foreground">Balance (after deductions)</p><p className={`font-semibold ${kautionBalance >= 0 ? "text-emerald-400" : "text-destructive"}`}>{kautionBalance.toFixed(2)}</p></div>
                </div>
                {kautionDeductions.length > 0 && (
                  <Table>
                    <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Category</TableHead><TableHead>Reason</TableHead><TableHead className="text-right">Amount</TableHead><TableHead className="w-16" /></TableRow></TableHeader>
                    <TableBody>
                      {kautionDeductions.map((d) => editDed?.id === d.id ? (
                        <TableRow key={d.id}>
                          <TableCell><Input type="date" className="h-7 text-xs" value={editDed.date} onChange={(e) => setEditDed({ ...editDed, date: e.target.value })} /></TableCell>
                          <TableCell>
                            <Select value={editDed.category} onValueChange={(v) => setEditDed({ ...editDed, category: v })}>
                              <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                              <SelectContent>{KAUTION_CATS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                            </Select>
                          </TableCell>
                          <TableCell><Input className="h-7 text-xs" placeholder="Reason" value={editDed.reason} onChange={(e) => setEditDed({ ...editDed, reason: e.target.value })} /></TableCell>
                          <TableCell className="text-right"><Input type="number" step="0.01" className="h-7 text-xs w-24 ml-auto" value={editDed.amount || ""} onChange={(e) => setEditDed({ ...editDed, amount: Number(e.target.value) })} /></TableCell>
                          <TableCell className="flex gap-1">
                            <Button variant="ghost" size="icon" onClick={() => updateDeduction.mutate(editDed)} disabled={!editDed.amount || updateDeduction.isPending}><Check className="size-3 text-emerald-400" /></Button>
                            <Button variant="ghost" size="icon" onClick={() => setEditDed(null)}><X className="size-3" /></Button>
                          </TableCell>
                        </TableRow>
                      ) : (
                        <TableRow key={d.id}>
                          <TableCell className="text-muted-foreground">{d.date}</TableCell>
                          <TableCell>{d.category}</TableCell>
                          <TableCell className="text-muted-foreground text-xs">{d.reason || "—"}</TableCell>
                          <TableCell className="text-right font-mono">{d.amount.toFixed(2)}</TableCell>
                          <TableCell className="flex gap-1">
                            <Button variant="ghost" size="icon" onClick={() => setEditDed({ id: d.id, date: d.date, amount: d.amount, category: d.category, reason: d.reason || "" })}><Pencil className="size-3" /></Button>
                            <ConfirmButton onConfirm={() => removeDeduction.mutate(d.id)} title="Delete deduction?" message={`Delete the ${d.amount.toFixed(2)} deduction (${d.category})?`}><Button variant="ghost" size="icon"><Trash2 className="size-3 text-destructive" /></Button></ConfirmButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {/* Kaution return section */}
                {selectedContract?.kaution_amount && !selectedContract.kaution_returned_date && (
                  <div className="border-t border-border pt-3 space-y-2">
                    <p className="text-xs font-medium text-emerald-400">Mark Kaution as Returned</p>
                    <div className="flex gap-2">
                      <Input type="date" className="h-8 text-sm" value={kautionReturnForm.date}
                        onChange={(e) => setKautionReturnForm((f) => ({ ...f, date: e.target.value }))} />
                      <Input type="number" step="0.01" className="h-8 text-sm w-32" placeholder="Amount"
                        value={kautionReturnForm.amount || kautionBalance}
                        onChange={(e) => setKautionReturnForm((f) => ({ ...f, amount: Number(e.target.value) }))} />
                      <Button size="sm" variant="outline" className="text-emerald-400 border-emerald-400/30"
                        onClick={() => markKautionReturned.mutate()} disabled={markKautionReturned.isPending}>
                        Mark Returned
                      </Button>
                    </div>
                  </div>
                )}
                {selectedContract?.kaution_returned_date && (
                  <div className="rounded-md bg-emerald-500/10 border border-emerald-500/20 p-3 flex justify-between items-center">
                    <p className="text-sm text-emerald-400">
                      Returned {selectedContract.kaution_returned_amount?.toFixed(2)} on {selectedContract.kaution_returned_date}
                    </p>
                    <Button size="sm" variant="ghost" onClick={() => clearKautionReturn.mutate()}>Clear</Button>
                  </div>
                )}

                <div className="border-t border-border pt-3 space-y-2">
                  <p className="text-xs font-medium">Add deduction</p>
                  <div className="grid grid-cols-2 gap-2">
                    <Input type="date" className="h-8 text-sm" value={kdForm.date} onChange={(e) => setKdForm((f) => ({ ...f, date: e.target.value }))} />
                    <Input type="number" step="0.01" className="h-8 text-sm" placeholder="Amount" value={kdForm.amount || ""} onChange={(e) => setKdForm((f) => ({ ...f, amount: Number(e.target.value) }))} />
                    <Select value={kdForm.category} onValueChange={(v) => setKdForm((f) => ({ ...f, category: v }))}>
                      <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>{KAUTION_CATS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                    </Select>
                    <Input className="h-8 text-sm" placeholder="Reason" value={kdForm.reason} onChange={(e) => setKdForm((f) => ({ ...f, reason: e.target.value }))} />
                  </div>
                  <Button size="sm" onClick={() => addDeduction.mutate()} disabled={!kdForm.amount || addDeduction.isPending}>
                    <Plus className="size-4 mr-1" /> Add
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Co-tenants */}
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><Users className="size-4" />Co-Tenants (Mitmieter)</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {coTenants.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No co-tenants.</p>
                ) : (
                  <Table>
                    <TableBody>
                      {coTenants.map((ct) => (
                        <TableRow key={ct.id}>
                          <TableCell>{ct.name}</TableCell>
                          <TableCell className="text-muted-foreground">{ct.gender}</TableCell>
                          <TableCell className="text-muted-foreground text-xs">{ct.email}</TableCell>
                          <TableCell><Badge variant={ct.in_contract ? "default" : "secondary"}>{ct.in_contract ? "In contract" : "Informal"}</Badge></TableCell>
                          <TableCell><ConfirmButton onConfirm={() => removeCoTenant.mutate(ct.id)} title="Remove co-tenant?" message={`Remove ${ct.name} from this contract?`} confirmLabel="Remove"><Button variant="ghost" size="icon"><Trash2 className="size-3 text-destructive" /></Button></ConfirmButton></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                <div className="border-t border-border pt-3 space-y-2">
                  <p className="text-xs font-medium">Add co-tenant</p>
                  <div className="grid grid-cols-2 gap-2">
                    <Input className="h-8 text-sm" placeholder="Name" value={ctForm.name} onChange={(e) => setCtForm((f) => ({ ...f, name: e.target.value }))} />
                    <Select value={ctForm.gender} onValueChange={(v) => setCtForm((f) => ({ ...f, gender: v }))}>
                      <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="male">Herr</SelectItem><SelectItem value="female">Frau</SelectItem><SelectItem value="diverse">Divers</SelectItem></SelectContent>
                    </Select>
                    <Input className="h-8 text-sm" placeholder="Email" value={ctForm.email} onChange={(e) => setCtForm((f) => ({ ...f, email: e.target.value }))} />
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ctForm.in_contract} onChange={(e) => setCtForm((f) => ({ ...f, in_contract: e.target.checked }))} className="accent-primary" />In contract</label>
                  </div>
                  <Button size="sm" onClick={() => addCoTenant.mutate()} disabled={!ctForm.name || addCoTenant.isPending}>
                    <Plus className="size-4 mr-1" /> Add
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      ) : null}

      {/* Kaution Overview tab */}
      {tab === "kaution-overview" && (
        <div className="max-w-5xl">
          <PageHeader title="Kaution Overview">
            <Button variant="outline" size="sm" onClick={() => setTab("contracts")}>← Back</Button>
          </PageHeader>
          <p className="text-sm text-muted-foreground mb-3">
            Every contract with a deposit on file. <span className="text-foreground">Paid</span> = installments received
            (amber shows what is still <em>offen</em>); <span className="text-foreground">Balance</span> = what you would owe
            back today (Kaution − deductions). Click a row to record an installment, add a deduction, or mark the deposit returned.
          </p>
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Apartment</TableHead>
                  <TableHead className="text-right">Kaution</TableHead>
                  <TableHead className="text-right">Paid</TableHead>
                  <TableHead className="text-right">Deducted</TableHead>
                  <TableHead className="text-right">Balance</TableHead>
                  <TableHead>Returned</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(kautionOverview as any[]).length === 0 ? (
                  <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-10">No Kaution on file.</TableCell></TableRow>
                ) : (
                  (kautionOverview as any[]).map((r: any) => (
                    <TableRow key={r.contract_id} className="cursor-pointer" onClick={() => openContractById(r.contract_id)}>
                      <TableCell className="font-medium">{r.tenant_name}</TableCell>
                      <TableCell className="text-muted-foreground">{r.apartment_name}<br /><span className="text-xs">{r.property_name}</span></TableCell>
                      <TableCell className="text-right font-mono">{r.kaution_amount?.toFixed(2)} {r.kaution_currency}</TableCell>
                      <TableCell className="text-right font-mono">
                        {(r.paid ?? 0) > 0 ? (
                          <>
                            <span className="text-emerald-400">{r.paid.toFixed(2)}</span>
                            {(r.outstanding ?? 0) > 0.001 && <span className="text-amber-400 text-xs block">−{r.outstanding.toFixed(2)} offen</span>}
                          </>
                        ) : (
                          <span className="text-muted-foreground text-xs">{r.kaution_paid_date || "—"}</span>
                        )}
                      </TableCell>
                      <TableCell className={`text-right font-mono ${r.deducted > 0 ? "text-destructive" : "text-muted-foreground"}`}>{r.deducted?.toFixed(2)}</TableCell>
                      <TableCell className={`text-right font-mono font-semibold ${r.balance >= 0 ? "text-emerald-400" : "text-destructive"}`}>{r.balance?.toFixed(2)}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {r.kaution_returned_date ? (
                          <span className="text-emerald-400 text-xs">{r.kaution_returned_amount?.toFixed(2)} on {r.kaution_returned_date}</span>
                        ) : "—"}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
              {(kautionOverview as any[]).length > 0 && (() => {
                const rows = kautionOverview as any[];
                const active = rows.filter((r) => !r.kaution_returned_date);
                const sum = (f: (r: any) => number) => active.reduce((s, r) => s + (f(r) || 0), 0);
                const totKaution = sum((r) => r.kaution_amount);
                // "offen" only means something for deposits tracked via installments;
                // legacy deposits (a paid_date, no installments) are already fully paid.
                const totOutstanding = active
                  .filter((r) => (r.paid ?? 0) > 0)
                  .reduce((s, r) => s + (r.outstanding || 0), 0);
                const totBalance = sum((r) => r.balance);
                return (
                  <TableBody className="border-t border-border font-medium">
                    <TableRow>
                      <TableCell colSpan={2} className="text-xs text-muted-foreground">Totals (deposits not yet returned)</TableCell>
                      <TableCell className="text-right font-mono">{totKaution.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono text-amber-400">{totOutstanding > 0.001 ? `−${totOutstanding.toFixed(2)} offen` : "—"}</TableCell>
                      <TableCell />
                      <TableCell className="text-right font-mono text-emerald-400">{totBalance.toFixed(2)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">held now</TableCell>
                    </TableRow>
                  </TableBody>
                );
              })()}
            </Table>
          </Card>
        </div>
      )}

      {/* Contract form dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing ? "Edit Contract" : "New Contract"}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Tenant</Label>
                <Select value={String(form.tenant_id || "")} onValueChange={(v) => setForm((f) => ({ ...f, tenant_id: Number(v) }))}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{tenants.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Apartment</Label>
                <Select value={String(form.apartment_id || "")} onValueChange={(v) => setForm((f) => ({ ...f, apartment_id: Number(v) }))}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{apartments.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.property_name} — {a.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><Label>Monthly Rent</Label><Input type="number" step="0.01" value={form.rent} onChange={(e) => setForm((f) => ({ ...f, rent: Number(e.target.value) }))} /></div>
              <div className="space-y-1.5"><Label>Currency</Label>
                <Select value={form.currency} onValueChange={(v) => setForm((f) => ({ ...f, currency: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><Label>Start Date</Label><Input type="date" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} /></div>
              <div className="space-y-1.5"><Label>End Date (optional)</Label><Input type="date" value={form.end_date} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><Label>Kaution Amount</Label><Input type="number" step="0.01" value={form.kaution_amount} onChange={(e) => setForm((f) => ({ ...f, kaution_amount: Number(e.target.value) }))} /></div>
              <div className="space-y-1.5"><Label>Kaution Currency</Label>
                <Select value={form.kaution_currency} onValueChange={(v) => setForm((f) => ({ ...f, kaution_currency: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><Label>Kaution Paid Date</Label><Input type="date" value={form.kaution_paid_date} onChange={(e) => setForm((f) => ({ ...f, kaution_paid_date: e.target.value }))} /></div>
              <div className="space-y-1.5"><Label>Kaution Returned Date</Label><Input type="date" value={form.kaution_returned_date} onChange={(e) => setForm((f) => ({ ...f, kaution_returned_date: e.target.value }))} /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={() => save.mutate(form)} disabled={!form.tenant_id || !form.apartment_id || !form.start_date || save.isPending}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Terminate confirmation — choose which date to record as the end date */}
      <Dialog open={!!terminateTarget} onOpenChange={(o) => { if (!o) setTerminateTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Terminate contract</DialogTitle>
          </DialogHeader>
          {terminateTarget && (
            <div className="space-y-3 text-sm">
              <p className="text-muted-foreground">
                Which date should be recorded as the end date for{" "}
                <span className="text-foreground font-medium">{terminateTarget.tenant_name}</span>
                {" "}({terminateTarget.apartment_name})?
              </p>
              <div className="space-y-2">
                {terminateTarget.end_date && (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="radio" className="accent-primary" checked={terminateChoice === "contract"}
                      onChange={() => setTerminateChoice("contract")} />
                    Contract end date — <b>{terminateTarget.end_date}</b> <span className="text-muted-foreground">(runs full term)</span>
                  </label>
                )}
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" className="accent-primary" checked={terminateChoice === "today"}
                    onChange={() => setTerminateChoice("today")} />
                  Today — <b>{new Date().toISOString().split("T")[0]}</b> <span className="text-muted-foreground">(early termination)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" className="accent-primary" checked={terminateChoice === "custom"}
                    onChange={() => setTerminateChoice("custom")} />
                  Custom date:
                  <Input type="date" className="h-8 w-40" value={terminateCustom}
                    onChange={(e) => { setTerminateCustom(e.target.value); setTerminateChoice("custom"); }} />
                </label>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setTerminateTarget(null)}>Cancel</Button>
            <Button onClick={() => {
              if (!terminateTarget) return;
              const end_date = terminateChoice === "contract" ? (terminateTarget.end_date || undefined)
                : terminateChoice === "today" ? new Date().toISOString().split("T")[0]
                : (terminateCustom || undefined);
              terminate.mutate({ id: terminateTarget.id, end_date });
            }} disabled={terminate.isPending || (terminateChoice === "custom" && !terminateCustom)}>
              {terminate.isPending ? "Terminating…" : "Terminate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
