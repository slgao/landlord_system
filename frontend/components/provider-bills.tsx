"use client";

// Provider bills (Rechnungen): the supplier's Jahresabrechnung for Strom or
// Gas, the water bill, the Hausgeldabrechnung behind the Betriebskosten. Each
// is an expense row with a utility and a billing period, so the tax report and
// balance sheet already count what was paid. Tenant Nebenkostenabrechnungen
// link to the bills they pass on — one or several — and whether a bill is
// fully passed on is the landlord's call, not something the app derives: a WG
// bill is shared by several tenants.

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { todayISO } from "@/lib/utils";
import { ProviderBill, TaxExpense, Utility } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ConfirmButton } from "@/components/confirm-button";
import { toast } from "sonner";
import { FileDown, Pencil, Plus, Trash2, Receipt } from "lucide-react";
import { eur, fmtDate, invalidateSettlementViews } from "@/lib/nk-format";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const EMPTY_BILLS: ProviderBill[] = [];
const EMPTY_CANDIDATES: TaxExpense[] = [];

export const UTILITY_LABEL: Record<Utility, string> = {
  strom: "Strom", gas: "Gas", wasser: "Wasser", heizung: "Heizung / Warmwasser",
  betriebskosten: "Betriebskosten", muell: "Müll", sonstige: "Sonstiges",
};

export function billLabel(b: { utility: Utility; vendor?: string | null; period_start?: string | null; period_end?: string | null }) {
  const period = b.period_start && b.period_end ? ` ${fmtDate(b.period_start)}–${fmtDate(b.period_end)}` : "";
  return `${UTILITY_LABEL[b.utility]}${b.vendor ? ` · ${b.vendor}` : ""}${period}`;
}

function invalidateBills(qc: ReturnType<typeof useQueryClient>) {
  invalidateSettlementViews(qc);
  for (const key of ["provider-bills", "tax-expenses"]) qc.invalidateQueries({ queryKey: [key] });
}

async function downloadBillPdf(b: ProviderBill) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API}/api/tax/expenses/${b.id}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) { toast.error("Could not load the PDF"); return; }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `Rechnung_${UTILITY_LABEL[b.utility]}_${b.period_end || b.expense_date}.pdf`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Add / edit a bill ─────────────────────────────────────────────────────────

export function BillDialog({
  open, onOpenChange, editing,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  // A bill to edit, or a plain expense to turn into one.
  editing?: TaxExpense | ProviderBill | null;
}) {
  const qc = useQueryClient();
  const { data: properties = [] } = useQuery<{ id: number; name: string }[]>({
    queryKey: ["properties"],
    queryFn: () => api.get("/api/properties/").then((r) => r.data),
    enabled: open,
  });
  const lastYear = new Date().getFullYear() - 1;
  const [f, setF] = useState({
    property_id: "", utility: "strom" as Utility, vendor: "", period_start: `${lastYear}-01-01`,
    period_end: `${lastYear}-12-31`, bill_total: "", direction: "nach" as "nach" | "guthaben",
    amount: "", expense_date: todayISO(), note: "",
  });
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    if (!open) return;
    const e = editing as (TaxExpense & ProviderBill) | null | undefined;
    setF({
      property_id: e ? String(e.property_id) : "",
      utility: (e?.utility as Utility) || (e?.category === "Hausgeld" ? "betriebskosten" : "strom"),
      vendor: e?.vendor || "",
      period_start: e?.period_start || `${lastYear}-01-01`,
      period_end: e?.period_end || `${lastYear}-12-31`,
      bill_total: e?.bill_total != null ? String(e.bill_total) : "",
      direction: (e?.amount ?? 0) < 0 ? "guthaben" : "nach",
      amount: e ? Math.abs(e.amount).toFixed(2) : "",
      expense_date: e?.expense_date || todayISO(),
      note: e?.note || "",
    });
    setFile(null);
  }, [open, editing, lastYear]);

  const value = Math.abs(Number(f.amount.replace(",", ".")) || 0);
  const valid = !!f.property_id && !!f.period_start && !!f.period_end
    && f.period_end >= f.period_start && !!f.expense_date && f.amount.trim() !== "";

  const save = useMutation({
    mutationFn: async () => {
      const e = editing as (TaxExpense & ProviderBill) | null | undefined;
      const body = {
        property_id: Number(f.property_id),
        apartment_id: (e as TaxExpense | undefined)?.apartment_id ?? null,
        expense_date: f.expense_date,
        amount: f.direction === "guthaben" ? -value : value,
        // A Hausgeldabrechnung stays under Hausgeld; any other bill is a
        // Versorgerabrechnung. An edited expense keeps the category it had.
        category: e?.category || (f.utility === "betriebskosten" ? "Hausgeld" : "Versorgerabrechnung"),
        vendor: f.vendor || null, note: f.note || null,
        deductible: (e as TaxExpense | undefined)?.deductible ?? 1,
        distribute_years: (e as TaxExpense | undefined)?.distribute_years ?? 1,
        source_file: (e as TaxExpense | undefined)?.source_file ?? null,
        utility: f.utility, period_start: f.period_start, period_end: f.period_end,
        bill_total: f.bill_total.trim() === "" ? null : Number(f.bill_total.replace(",", ".")),
      };
      const saved = e
        ? (await api.put(`/api/tax/expenses/${e.id}`, body)).data
        : (await api.post("/api/tax/expenses", body)).data;
      if (file) {
        const form = new FormData();
        form.append("file", file, file.name);
        await api.put(`/api/tax/expenses/${saved.id}/pdf`, form);
      }
      return saved;
    },
    onSuccess: () => {
      invalidateBills(qc);
      toast.success(editing ? "Bill updated" : "Bill recorded");
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e, "Could not save the bill")),
  });

  const segment = (on: boolean) => `flex-1 px-2 py-1.5 transition-colors ${on
    ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:text-foreground"}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{editing?.utility ? "Edit provider bill" : "Record provider bill"}</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Property</Label>
              <Select value={f.property_id} onValueChange={(v) => setF((x) => ({ ...x, property_id: v }))}>
                <SelectTrigger aria-label="Property"><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {properties.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Bills</Label>
              <Select value={f.utility} onValueChange={(v) => setF((x) => ({ ...x, utility: v as Utility }))}>
                <SelectTrigger aria-label="Utility"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(Object.keys(UTILITY_LABEL) as Utility[]).map((u) => (
                    <SelectItem key={u} value={u}>{UTILITY_LABEL[u]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bill-vendor">Provider</Label>
            <Input id="bill-vendor" value={f.vendor} placeholder="e.g. Stadtwerke, Vattenfall, Hausverwaltung"
              onChange={(e) => setF((x) => ({ ...x, vendor: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="bill-start">Billing period from</Label>
              <Input id="bill-start" type="date" value={f.period_start} onChange={(e) => setF((x) => ({ ...x, period_start: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bill-end">to</Label>
              <Input id="bill-end" type="date" value={f.period_end} onChange={(e) => setF((x) => ({ ...x, period_end: e.target.value }))} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bill-total">Total cost of the period (€)</Label>
            <Input id="bill-total" inputMode="decimal" value={f.bill_total} placeholder="Gesamtkosten laut Rechnung — optional"
              onChange={(e) => setF((x) => ({ ...x, bill_total: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Result</Label>
            <div className="grid grid-cols-[1fr_9rem] gap-3">
              <div className="flex rounded-md border border-border overflow-hidden text-sm" role="radiogroup" aria-label="Bill result">
                <button type="button" role="radio" aria-checked={f.direction === "nach"} className={segment(f.direction === "nach")}
                  onClick={() => setF((x) => ({ ...x, direction: "nach" }))}>You pay (Nachzahlung)</button>
                <button type="button" role="radio" aria-checked={f.direction === "guthaben"} className={segment(f.direction === "guthaben")}
                  onClick={() => setF((x) => ({ ...x, direction: "guthaben" }))}>You get back (Guthaben)</button>
              </div>
              <Input aria-label="Result amount (€)" inputMode="decimal" placeholder="0.00" value={f.amount}
                onChange={(e) => setF((x) => ({ ...x, amount: e.target.value }))} />
            </div>
            <p className="text-xs text-muted-foreground">
              What the bill leaves after your Abschläge — 0 if they covered it exactly. It is an expense
              (or, as a Guthaben, a refund) in the year it was paid.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bill-paid">Paid / received on</Label>
            <Input id="bill-paid" type="date" value={f.expense_date} onChange={(e) => setF((x) => ({ ...x, expense_date: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bill-note">Note</Label>
            <Input id="bill-note" value={f.note} placeholder="Optional" onChange={(e) => setF((x) => ({ ...x, note: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bill-pdf">Bill PDF</Label>
            <Input id="bill-pdf" type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            {(editing as ProviderBill | undefined)?.has_pdf && !file && (
              <p className="text-xs text-muted-foreground">A PDF is stored; choosing a file replaces it.</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => save.mutate()} disabled={!valid || save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── The list ─────────────────────────────────────────────────────────────────

export function BillsSection({ bills, candidates }: {
  // Both arrive with the page's overview request; undefined while it loads.
  bills?: ProviderBill[];
  candidates?: TaxExpense[];
}) {
  const qc = useQueryClient();
  const [onlyOpen, setOnlyOpen] = useState(true);
  const [dialog, setDialog] = useState<{ editing?: TaxExpense | ProviderBill } | null>(null);

  const isLoading = bills === undefined;
  const allBills = bills ?? EMPTY_BILLS;
  // Expenses that are not bills yet but could be — a Hausgeldabrechnung
  // recorded before bills existed, say. The server picks them, so the page
  // no longer downloads every expense (35 KB of notes) for a dropdown.
  const convertible = candidates ?? EMPTY_CANDIDATES;

  const settle = useMutation({
    mutationFn: ({ id, tenant_settled }: { id: number; tenant_settled: boolean }) =>
      api.put(`/api/nk-settlements/bills/${id}/settled`, { tenant_settled }),
    onSuccess: (_, v) => {
      invalidateBills(qc);
      toast.success(v.tenant_settled ? "Marked as fully settled with the tenants" : "Marked as open again");
    },
    onError: (e) => toast.error(errorMessage(e, "Could not update the bill")),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/tax/expenses/${id}`),
    onSuccess: () => { invalidateBills(qc); toast.success("Bill deleted"); },
    onError: (e) => toast.error(errorMessage(e, "Could not delete the bill")),
  });

  const shown = onlyOpen ? allBills.filter((b) => !b.tenant_settled) : allBills;
  const hidden = allBills.length - shown.length;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Receipt className="size-4" /> Provider bills (Rechnungen)
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} className="accent-primary" />
              Only not yet fully settled
            </label>
            {convertible.length > 0 && (
              <Select value="" onValueChange={(v) => setDialog({ editing: convertible.find((e) => String(e.id) === v) })}>
                <SelectTrigger className="h-8 w-52 text-xs" aria-label="Use an existing expense as a bill">
                  <SelectValue placeholder="Use an existing expense…" />
                </SelectTrigger>
                <SelectContent>
                  {convertible.map((e) => (
                    <SelectItem key={e.id} value={String(e.id)}>
                      {fmtDate(e.expense_date)} · {e.category} · {e.vendor || e.property_name} · {eur(e.amount)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <Button size="sm" onClick={() => setDialog({})}><Plus className="size-4 mr-1" /> Add bill</Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          The Rechnungen behind your Abrechnungen. Link them to a tenant settlement — one bill per
          Abrechnung or several in one — and tick a bill off once it is fully passed on.
        </p>
      </CardHeader>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Bill</TableHead>
              <TableHead>Property</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="text-right">Result</TableHead>
              <TableHead>Passed on in</TableHead>
              <TableHead>Fully settled</TableHead>
              <TableHead className="w-28" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">Loading…</TableCell></TableRow>
            ) : shown.length === 0 ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                {allBills.length === 0 ? "No provider bills yet." : "Every bill is fully settled with the tenants."}
              </TableCell></TableRow>
            ) : shown.map((b) => (
              <TableRow key={b.id}>
                <TableCell>
                  <span className="font-medium">{UTILITY_LABEL[b.utility]}</span>
                  {b.vendor && <span className="text-muted-foreground"> · {b.vendor}</span>}
                  <span className="block text-xs text-muted-foreground whitespace-nowrap">
                    {fmtDate(b.period_start)}–{fmtDate(b.period_end)}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground">{b.property_name}</TableCell>
                <TableCell className="text-right font-mono whitespace-nowrap">{b.bill_total != null ? eur(b.bill_total) : "—"}</TableCell>
                <TableCell className={`text-right font-mono whitespace-nowrap ${b.amount > 0 ? "text-destructive" : b.amount < 0 ? "text-primary" : ""}`}>
                  {b.amount > 0 ? `+${eur(b.amount)}` : b.amount < 0 ? `−${eur(-b.amount)}` : eur(0)}
                  <span className="block text-[11px] text-muted-foreground font-sans">{fmtDate(b.expense_date)}</span>
                </TableCell>
                <TableCell className="text-xs">
                  {b.settlements.length === 0
                    ? <span className="text-muted-foreground">not linked yet</span>
                    : b.settlements.map((s) => (
                        <span key={s.id} className="block">{s.tenant_name} · {s.period_end.slice(0, 4)}</span>
                      ))}
                </TableCell>
                <TableCell>
                  <label className="flex items-center gap-2 text-xs cursor-pointer">
                    <input type="checkbox" checked={b.tenant_settled} className="size-4 accent-primary"
                      aria-label={`Fully settled with tenants: ${billLabel(b)}`}
                      onChange={(e) => settle.mutate({ id: b.id, tenant_settled: e.target.checked })} />
                    {b.tenant_settled ? <Badge className="bg-primary/15 text-primary border-primary/20">Settled</Badge> : "open"}
                  </label>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-0.5">
                    {b.has_pdf && (
                      <Button variant="ghost" size="icon" title="Download bill" aria-label="Download bill" onClick={() => downloadBillPdf(b)}>
                        <FileDown className="size-4" />
                      </Button>
                    )}
                    <Button variant="ghost" size="icon" title="Edit" aria-label="Edit bill" onClick={() => setDialog({ editing: b })}>
                      <Pencil className="size-4" />
                    </Button>
                    <ConfirmButton onConfirm={() => remove.mutate(b.id)} title="Delete bill?"
                      message="It is an expense too: deleting it removes it from the tax report and the balance sheet, and from any settlement it is linked to.">
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label="Delete bill">
                        <Trash2 className="size-4" />
                      </Button>
                    </ConfirmButton>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {onlyOpen && hidden > 0 && (
        <CardContent className="pt-2 pb-3">
          <p className="text-xs text-muted-foreground">{hidden} fully settled bill{hidden !== 1 ? "s" : ""} hidden.</p>
        </CardContent>
      )}
      <BillDialog open={!!dialog} onOpenChange={(o) => { if (!o) setDialog(null); }} editing={dialog?.editing ?? null} />
    </Card>
  );
}

// ── Pick the bills an Abrechnung covers ──────────────────────────────────────

export function BillPicker({
  contractId, periodStart, periodEnd, selected, onChange,
}: {
  contractId: string;
  periodStart: string;
  periodEnd: string;
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const { data: bills = [] } = useQuery<ProviderBill[]>({
    queryKey: ["provider-bills", "contract", contractId],
    queryFn: () => api.get(`/api/nk-settlements/bills?contract_id=${contractId}`).then((r) => r.data),
    enabled: !!contractId,
  });
  // Bills overlapping the Abrechnung first; the rest stay reachable, since a
  // combined Abrechnung may pull in one from a neighbouring period.
  const sorted = useMemo(() => {
    const overlaps = (b: ProviderBill) => !!b.period_start && !!b.period_end
      && b.period_start <= periodEnd && b.period_end >= periodStart;
    return [...bills].sort((a, b) => Number(overlaps(b)) - Number(overlaps(a)));
  }, [bills, periodStart, periodEnd]);
  const offered = sorted.filter((b) => !b.tenant_settled || selected.includes(b.id));

  if (!contractId) return null;
  return (
    <div className="space-y-1.5">
      <Label>Rechnungen covered</Label>
      {offered.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No open provider bills for this property. Record them under Provider bills to link them here.
        </p>
      ) : (
        <div className="rounded-md border border-border divide-y divide-border max-h-44 overflow-y-auto">
          {offered.map((b) => (
            <label key={b.id} className="flex items-start gap-2 px-3 py-2 text-sm cursor-pointer">
              <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={selected.includes(b.id)}
                onChange={(e) => onChange(e.target.checked ? [...selected, b.id] : selected.filter((x) => x !== b.id))} />
              <span>
                {billLabel(b)}
                <span className="block text-xs text-muted-foreground">
                  {b.bill_total != null ? `Total ${eur(b.bill_total)}` : "Total not entered"}
                  {b.settlements.length > 0 && ` · already in ${b.settlements.map((s) => s.tenant_name).join(", ")}`}
                </span>
              </span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
