"use client";

// Nebenkostenabrechnungen sent to tenants: recording one, attaching the PDF
// as sent, and booking the money that moves because of it. Shared by the NK
// Settlements page, the Nebenkostenabrechnung generator (which offers to save
// what it just produced) and Rent Tracking.

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { todayISO } from "@/lib/utils";
import { Contract, NKSettlement } from "@/lib/types";
import { contractStatusSuffix } from "@/lib/contract-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const eur = (n: number) =>
  `${n.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;

/** "Nachzahlung 180,00 €" / "Guthaben 95,00 €" — the sign spelled out, since
 *  a bare −95 reads differently depending on whose side you are on. */
export function resultLabel(amount: number) {
  if (Math.abs(amount) < 0.005) return "Ausgeglichen";
  return amount > 0 ? `Nachzahlung ${eur(amount)}` : `Guthaben ${eur(-amount)}`;
}

export function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

// Every query a settlement change can move. Payments feed the arrears, the
// tax report and the balance sheet, so those go stale too.
export function invalidateSettlementViews(qc: ReturnType<typeof useQueryClient>) {
  for (const key of ["nk-settlements", "nk-pending", "nk-unlinked-kaution", "payments",
                     "tenant-payments", "payment-reminders", "tax-report", "balance-sheet",
                     "balance-sheet-dash", "kaution-deductions", "kaution-overview"]) {
    qc.invalidateQueries({ queryKey: [key] });
  }
}

/** Fetch the stored PDF with the session token and hand it to the browser.
 *  A plain link would need the token in the URL, where it ends up in logs. */
export async function downloadSettlementPdf(s: NKSettlement) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API}/api/nk-settlements/${s.id}/pdf`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) { toast.error("Could not load the PDF"); return; }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `Nebenkostenabrechnung_${s.tenant_name || s.contract_id}_${s.period_end.slice(0, 4)}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Record / edit a settlement ────────────────────────────────────────────────

export interface SettlementDraft {
  contract_id?: number;
  period_start?: string;
  period_end?: string;
  amount?: number;          // signed
  issued_date?: string | null;
  note?: string | null;
  pdf?: Blob | null;        // the Abrechnung as sent, when it was just generated
  // An existing Kaution deduction that already settled it (the "import" path).
  kaution_deduction?: { id: number; date?: string | null; amount: number } | null;
  // The PDF offset the Nachzahlung against the deposit: offer to book it.
  offsetKaution?: boolean;
}

type Direction = "nach" | "guthaben";

export function SettlementDialog({
  open, onOpenChange, contracts, draft, editing, onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  contracts: Contract[];
  draft?: SettlementDraft;
  editing?: NKSettlement | null;
  onSaved?: (s: NKSettlement) => void;
}) {
  const qc = useQueryClient();
  const [contractId, setContractId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  // Direction and a positive figure rather than a signed number: which way
  // the money goes is the question people actually answer.
  const [direction, setDirection] = useState<Direction>("nach");
  const [amount, setAmount] = useState("");
  const [issued, setIssued] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [offset, setOffset] = useState(false);
  const fromDeduction = !editing && draft?.kaution_deduction ? draft.kaution_deduction : null;

  useEffect(() => {
    if (!open) return;
    const src = editing ?? draft ?? {};
    const lastYear = new Date().getFullYear() - 1;
    setContractId(src.contract_id ? String(src.contract_id) : "");
    setStart(src.period_start || `${lastYear}-01-01`);
    setEnd(src.period_end || `${lastYear}-12-31`);
    const signed = src.amount ?? 0;
    setDirection(signed < 0 ? "guthaben" : "nach");
    setAmount(signed ? Math.abs(signed).toFixed(2) : "");
    // A fresh one goes out today; an edited or imported one keeps what is
    // known — an Abrechnung settled months ago was not sent today.
    setIssued(src.issued_date ?? (editing || draft?.kaution_deduction ? "" : todayISO()));
    setNote(src.note || "");
    setFile(null);
    setOffset(!editing && !!draft?.offsetKaution);
  }, [open, draft, editing]);

  const pdf: Blob | null = file ?? draft?.pdf ?? null;
  const value = Number(amount.replace(",", "."));
  const valid = !!contractId && !!start && !!end && end >= start
    && Number.isFinite(value) && amount.trim() !== "";

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        contract_id: Number(contractId), period_start: start, period_end: end,
        amount: direction === "guthaben" ? -Math.abs(value) : Math.abs(value),
        issued_date: issued || null, note: note || null,
        ...(fromDeduction ? { kaution_deduction_id: fromDeduction.id } : {}),
      };
      let saved: NKSettlement = editing
        ? (await api.put(`/api/nk-settlements/${editing.id}`, body)).data
        : (await api.post("/api/nk-settlements/", body)).data;
      if (offset && direction === "nach") {
        if ((saved.kaution_available ?? 0) > 0.005) {
          // As much as the deposit covers; anything beyond stays open.
          saved = (await api.post(`/api/nk-settlements/${saved.id}/settle-from-kaution`,
                                  { date: todayISO() })).data;
        } else {
          toast.info("Nothing is left in the deposit to take it from — the Nachzahlung stays open.");
        }
      }
      if (pdf) {
        const form = new FormData();
        form.append("file", pdf, "Nebenkostenabrechnung.pdf");
        await api.put(`/api/nk-settlements/${saved.id}/pdf`, form);
      }
      return saved;
    },
    onSuccess: (saved) => {
      invalidateSettlementViews(qc);
      toast.success(editing ? "Settlement updated" : "Settlement recorded");
      onSaved?.(saved);
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e, "Could not save the settlement")),
  });

  const selectable = contracts.filter((c) => !c.terminated || String(c.id) === contractId
    || c.end_date && c.end_date >= `${new Date().getFullYear() - 2}-01-01`);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit settlement" : "Record NK settlement"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label>Tenant / contract</Label>
            <Select value={contractId} onValueChange={setContractId}>
              <SelectTrigger aria-label="Contract"><SelectValue placeholder="Select contract" /></SelectTrigger>
              <SelectContent>
                {selectable.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.tenant_name} — {c.apartment_name}{contractStatusSuffix(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {contracts.find((c) => String(c.id) === contractId)?.nk_mode === "flat" && (
            <p className="text-xs rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-400 px-3 py-2">
              This contract has an NK-Pauschale / Warmmiete — nothing is settled, so no Abrechnung is
              owed. Record one only if it covers an earlier period with Vorauszahlungen, or you agreed it.
            </p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="nk-start">Abrechnungszeitraum from</Label>
              <Input id="nk-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nk-end">to</Label>
              <Input id="nk-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Result</Label>
            <div className="grid grid-cols-[1fr_9rem] gap-3">
              <div className="flex rounded-md border border-border overflow-hidden text-sm" role="radiogroup" aria-label="Result direction">
                {([["nach", "Tenant pays (Nachzahlung)"], ["guthaben", "You refund (Guthaben)"]] as const).map(([d, label]) => (
                  <button key={d} type="button" role="radio" aria-checked={direction === d}
                    disabled={!!fromDeduction && d === "guthaben"}
                    onClick={() => setDirection(d)}
                    className={`flex-1 px-2 py-1.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${direction === d
                      ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:text-foreground"}`}>
                    {label}
                  </button>
                ))}
              </div>
              <Input aria-label="Amount (€)" inputMode="decimal" placeholder="0.00" value={amount}
                onChange={(e) => setAmount(e.target.value)} />
            </div>
          </div>
          {fromDeduction && (
            <p className="text-xs rounded-md bg-muted/60 px-3 py-2">
              Settled by the Kaution deduction of <b>{eur(fromDeduction.amount)}</b>
              {fromDeduction.date ? ` on ${fmtDate(fromDeduction.date)}` : ""} — it will be linked,
              so the settlement shows as paid from the deposit.
            </p>
          )}
          {!editing && draft?.offsetKaution && direction === "nach" && (
            <label className="flex items-start gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={offset} onChange={(e) => setOffset(e.target.checked)}
                className="mt-0.5 size-4 accent-primary" />
              <span>
                Take it from the deposit now
                <span className="block text-xs text-muted-foreground">
                  As in the PDF: books the Kaution deduction, up to what the deposit still holds.
                  Anything beyond stays open for the tenant to pay.
                </span>
              </span>
            </label>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="nk-issued">Sent to tenant on</Label>
            <Input id="nk-issued" type="date" value={issued} onChange={(e) => setIssued(e.target.value)} />
            <p className="text-xs text-muted-foreground">
              Must reach the tenant within 12 months after the period ends (§556 Abs. 3 BGB) —
              later, a Nachzahlung can no longer be claimed.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nk-note">Note</Label>
            <Input id="nk-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nk-pdf">Abrechnung PDF</Label>
            {draft?.pdf && !file ? (
              <p className="text-xs text-muted-foreground">The PDF you just generated will be attached.</p>
            ) : (
              <Input id="nk-pdf" type="file" accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            )}
            {editing?.has_pdf && !file && (
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

// ── Book the money against a settlement ──────────────────────────────────────

export function SettlementPaymentDialog({
  settlement, onOpenChange,
}: {
  settlement: NKSettlement | null;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayISO());
  const refund = (settlement?.amount ?? 0) < 0;

  useEffect(() => {
    if (!settlement) return;
    setAmount(Math.abs(settlement.open).toFixed(2));
    setDate(todayISO());
  }, [settlement]);

  const value = Math.abs(Number(amount.replace(",", ".")));

  const save = useMutation({
    mutationFn: () => api.post("/api/payments/", {
      contract_id: settlement!.contract_id,
      amount: refund ? -value : value,
      payment_date: date,
      kind: "nk_settlement",
      settlement_id: settlement!.id,
    }),
    onSuccess: () => {
      invalidateSettlementViews(qc);
      toast.success(refund ? "Refund recorded" : "Payment recorded");
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e, "Could not record the payment")),
  });

  return (
    <Dialog open={!!settlement} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{refund ? "Record refund to tenant" : "Record tenant's payment"}</DialogTitle>
        </DialogHeader>
        {settlement && (
          <div className="space-y-4 py-1">
            <p className="text-sm text-muted-foreground">
              {settlement.tenant_name} · {fmtDate(settlement.period_start)}–{fmtDate(settlement.period_end)}
              <br />
              {resultLabel(settlement.amount)} · open {eur(Math.abs(settlement.open))}
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="nkp-amount">{refund ? "Refunded (€)" : "Received (€)"}</Label>
              <Input id="nkp-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nkp-date">Date</Label>
              <Input id="nkp-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              <p className="text-xs text-muted-foreground">
                Counts for tax in the year the money moves.
                {!refund && (settlement.kaution_available ?? 0) > 0 &&
                  " Keeping it from the deposit instead? Use “Settle from Kaution” — it books the deduction too."}
              </p>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => save.mutate()} disabled={!value || !date || save.isPending}>
            {save.isPending ? "Saving…" : "Record"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Keep part of the deposit for an open Nachzahlung ─────────────────────────

export function KautionSettleDialog({
  settlement, onOpenChange,
}: {
  settlement: NKSettlement | null;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayISO());
  const most = settlement ? Math.min(settlement.open, settlement.kaution_available ?? 0) : 0;

  useEffect(() => {
    if (!settlement) return;
    setAmount(most.toFixed(2));
    setDate(todayISO());
  }, [settlement, most]);

  const value = Number(amount.replace(",", "."));

  const save = useMutation({
    mutationFn: () => api.post(`/api/nk-settlements/${settlement!.id}/settle-from-kaution`,
                               { date, amount: value }),
    onSuccess: () => {
      invalidateSettlementViews(qc);
      toast.success("Kept from the deposit");
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e, "Could not book the deduction")),
  });

  return (
    <Dialog open={!!settlement} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Settle from Kaution</DialogTitle></DialogHeader>
        {settlement && (
          <div className="space-y-4 py-1">
            <p className="text-sm text-muted-foreground">
              {settlement.tenant_name} · {fmtDate(settlement.period_start)}–{fmtDate(settlement.period_end)}
              <br />
              Open {eur(settlement.open)} · deposit still held {eur(settlement.kaution_available ?? 0)}
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="nkk-amount">Keep from deposit (€)</Label>
              <Input id="nkk-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
              {settlement.open > (settlement.kaution_available ?? 0) + 0.005 && (
                <p className="text-xs text-muted-foreground">
                  The deposit covers {eur(most)}; the remaining {eur(settlement.open - most)} stays open for the tenant to pay.
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nkk-date">Date of the offset</Label>
              <Input id="nkk-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              <p className="text-xs text-muted-foreground">
                Books an „NK Nachzahlung“ deduction on the contract&apos;s Kaution, linked to this
                Abrechnung. For tax it is Umlagen received on this date.
              </p>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => save.mutate()}
            disabled={!(value > 0) || value > most + 0.005 || !date || save.isPending}>
            {save.isPending ? "Saving…" : "Keep from deposit"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
