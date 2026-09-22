"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { Contract, NKSettlement, PendingAbrechnung, UnlinkedKaution } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ConfirmButton } from "@/components/confirm-button";
import {
  SettlementDialog, SettlementPaymentDialog, SettlementDraft, KautionSettleDialog,
  downloadSettlementPdf, eur, fmtDate, invalidateSettlementViews, resultLabel,
} from "@/components/nk-settlements";
import { toast } from "sonner";
import { BillsSection, UTILITY_LABEL } from "@/components/provider-bills";
import { FileDown, Pencil, Trash2, Banknote, CalendarClock, Vault, Link2, X } from "lucide-react";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const STATUS: Record<NKSettlement["status"], { label: string; cls: string }> = {
  open:     { label: "Open",    cls: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/20" },
  partial:  { label: "Partly paid", cls: "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/20" },
  settled:  { label: "Settled", cls: "bg-primary/15 text-primary border-primary/20" },
};

export default function NKSettlementsPage() {
  const qc = useQueryClient();
  const [dialog, setDialog] = useState<{ draft?: SettlementDraft; editing?: NKSettlement } | null>(null);
  const [paying, setPaying] = useState<NKSettlement | null>(null);
  const [fromKaution, setFromKaution] = useState<NKSettlement | null>(null);

  const { data: settlements = [], isLoading } = useQuery<NKSettlement[]>({
    queryKey: ["nk-settlements"],
    queryFn: () => api.get("/api/nk-settlements/").then((r) => r.data),
  });
  const { data: pending = [] } = useQuery<PendingAbrechnung[]>({
    queryKey: ["nk-pending"],
    queryFn: () => api.get("/api/nk-settlements/pending").then((r) => r.data),
  });
  const { data: contracts = [] } = useQuery<Contract[]>({
    queryKey: ["contracts-all"],
    queryFn: () => api.get("/api/contracts/").then((r) => r.data),
  });

  const { data: unlinked = [] } = useQuery<UnlinkedKaution[]>({
    queryKey: ["nk-unlinked-kaution"],
    queryFn: () => api.get("/api/nk-settlements/unlinked-kaution").then((r) => r.data),
  });

  const link = useMutation({
    mutationFn: ({ settlementId, deductionId }: { settlementId: number; deductionId: number }) =>
      api.post(`/api/nk-settlements/${settlementId}/kaution-links`, { deduction_id: deductionId }),
    onSuccess: () => { invalidateSettlementViews(qc); toast.success("Linked to the settlement"); },
    onError: (e) => toast.error(errorMessage(e, "Could not link the deduction")),
  });
  const unlink = useMutation({
    mutationFn: ({ settlementId, deductionId }: { settlementId: number; deductionId: number }) =>
      api.delete(`/api/nk-settlements/${settlementId}/kaution-links/${deductionId}`),
    onSuccess: () => { invalidateSettlementViews(qc); toast.success("Unlinked — the deduction stays on the Kaution"); },
    onError: (e) => toast.error(errorMessage(e, "Could not unlink the deduction")),
  });
  const byId = useMemo(() => new Map(settlements.map((s) => [s.id, s])), [settlements]);

  // An imported deduction most likely settled the year before it was taken.
  function importDraft(u: UnlinkedKaution): SettlementDraft {
    const y = u.date ? Number(u.date.slice(0, 4)) - 1 : new Date().getFullYear() - 1;
    return {
      contract_id: u.contract_id, period_start: `${y}-01-01`, period_end: `${y}-12-31`,
      amount: u.amount, issued_date: null, note: u.reason || null,
      kaution_deduction: { id: u.id, date: u.date, amount: u.amount },
    };
  }

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/nk-settlements/${id}`),
    onSuccess: () => { invalidateSettlementViews(qc); toast.success("Settlement deleted"); },
    onError: (e) => toast.error(errorMessage(e, "Could not delete the settlement")),
  });

  // What is still owed each way, across all tenants.
  const totals = useMemo(() => {
    let owedToYou = 0, youOwe = 0;
    for (const s of settlements) {
      if (s.open > 0) owedToYou += s.open; else youOwe += -s.open;
    }
    return { owedToYou, youOwe };
  }, [settlements]);

  return (
    <div className="max-w-6xl space-y-4">
      <PageHeader
        title="NK Settlements"
        description="Nebenkostenabrechnungen sent to tenants, what is still open on them, and which years still need one."
        action={{ label: "Record settlement", onClick: () => setDialog({}) }}
      />

      {pending.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <CalendarClock className="size-4" /> Abrechnung still to send
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Tenancies with an NK prepayment and no settlement recorded for a finished year.
              Assumes calendar-year billing periods; recording a settlement for any period
              overlapping the year clears it.
            </p>
          </CardHeader>
          <CardContent className="space-y-1">
            {pending.map((p) => (
              <div key={`${p.contract_id}-${p.year}`}
                className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-border last:border-0">
                <div>
                  <p className="text-sm font-medium">{p.tenant_name} · {p.year}</p>
                  <p className="text-xs text-muted-foreground">{p.apartment_name} · {p.property_name}</p>
                  {p.deposit_deductions.map((d) => (
                    <p key={d.id} className="text-xs text-primary mt-0.5">
                      {eur(d.amount)} Nebenkosten already kept from the deposit{d.date ? ` on ${fmtDate(d.date)}` : ""} —
                      probably what settled this year.
                    </p>
                  ))}
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <Badge variant={p.level === "missed" ? "destructive" : "secondary"}
                      className={p.level === "due" && p.days_remaining <= 60
                        ? "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/20" : ""}>
                      {p.level === "missed"
                        ? `Deadline passed ${-p.days_remaining}d ago`
                        : `${p.days_remaining}d left`}
                    </Badge>
                    <p className="text-xs text-muted-foreground mt-0.5">Deadline {fmtDate(p.deadline)}</p>
                  </div>
                  {p.deposit_deductions.map((d) => (
                    <Button key={d.id} size="sm" onClick={() => setDialog({
                      draft: {
                        contract_id: p.contract_id, period_start: p.period_start, period_end: p.period_end,
                        amount: d.amount, issued_date: null,
                        kaution_deduction: { id: d.id, date: d.date, amount: d.amount },
                      },
                    })}>
                      Record from deposit{p.deposit_deductions.length > 1 ? ` (${eur(d.amount)})` : ""}
                    </Button>
                  ))}
                  <Button size="sm" variant="outline" onClick={() => setDialog({
                    draft: { contract_id: p.contract_id, period_start: p.period_start, period_end: p.period_end },
                  })}>
                    {p.deposit_deductions.length ? "Record other" : "Record"}
                  </Button>
                </div>
              </div>
            ))}
            {pending.some((p) => p.level === "missed") && (
              <p className="text-xs text-muted-foreground pt-2">
                After the deadline a Nachzahlung can no longer be claimed, but a Guthaben is still owed.
                If you did send it in time, record it with its send date.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {unlinked.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Vault className="size-4" /> Already settled from a deposit
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Kaution deductions for Nebenkosten that no settlement points at yet. Turn each into a
              settlement — or link it to one you already recorded — so the year counts as done.
            </p>
          </CardHeader>
          <CardContent className="space-y-1">
            {unlinked.map((u) => (
              <div key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-border last:border-0">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{u.tenant_name} · {eur(u.amount)} kept on {fmtDate(u.date)}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {u.apartment_name} · {u.property_name} · {u.category}{u.reason ? ` — ${u.reason}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {u.candidates.length > 0 && (
                    <Select value="" onValueChange={(v) => link.mutate({ settlementId: Number(v), deductionId: u.id })}>
                      <SelectTrigger className="h-8 w-44 text-xs" aria-label="Link to settlement">
                        <SelectValue placeholder="Link to settlement…" />
                      </SelectTrigger>
                      <SelectContent>
                        {u.candidates.map((id) => {
                          const s = byId.get(id);
                          return s ? (
                            <SelectItem key={id} value={String(id)}>
                              {fmtDate(s.period_start)}–{fmtDate(s.period_end)} · open {eur(s.open)}
                            </SelectItem>
                          ) : null;
                        })}
                      </SelectContent>
                    </Select>
                  )}
                  <Button size="sm" variant="outline" onClick={() => setDialog({ draft: importDraft(u) })}>
                    Create settlement
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Tenants still owe you</p>
            <p className="text-2xl font-semibold mt-1 font-mono">{eur(totals.owedToYou)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">You still owe tenants</p>
            <p className="text-2xl font-semibold mt-1 font-mono">{eur(totals.youOwe)}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tenant</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Result</TableHead>
                <TableHead className="text-right">Paid</TableHead>
                <TableHead className="text-right">Open</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Sent</TableHead>
                <TableHead className="w-36" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10">Loading…</TableCell></TableRow>
              ) : settlements.length === 0 ? (
                <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10">
                  No settlements yet. Generate one under Nebenkostenabrechnung and save it, or record one done elsewhere.
                </TableCell></TableRow>
              ) : settlements.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <span className="font-medium">{s.tenant_name}</span>
                    <span className="block text-xs text-muted-foreground">{s.apartment_name} · {s.property_name}</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {fmtDate(s.period_start)}–{fmtDate(s.period_end)}
                    {s.bills.map((b) => (
                      <span key={b.id} className="block text-[11px]" title={b.tenant_settled ? "Bill fully settled" : "Bill still open"}>
                        {UTILITY_LABEL[b.utility]}{b.vendor ? ` · ${b.vendor}` : ""}{b.tenant_settled ? " ✓" : ""}
                      </span>
                    ))}
                  </TableCell>
                  <TableCell className={`whitespace-nowrap ${s.amount > 0 ? "text-destructive" : "text-primary"}`}>
                    {resultLabel(s.amount)}
                  </TableCell>
                  <TableCell className="text-right font-mono whitespace-nowrap">
                    {eur(Math.abs(s.paid))}
                    {s.kaution_deductions.map((d) => (
                      <span key={d.id} className="flex items-center justify-end gap-1 text-[11px] text-muted-foreground font-sans">
                        <Link2 className="size-3" /> Kaution {eur(d.amount)}
                        <button type="button" title="Unlink (the deduction stays on the Kaution)"
                          aria-label={`Unlink Kaution deduction of ${eur(d.amount)}`}
                          onClick={() => unlink.mutate({ settlementId: s.id, deductionId: d.id })}
                          className="hover:text-destructive">
                          <X className="size-3" />
                        </button>
                      </span>
                    ))}
                  </TableCell>
                  <TableCell className="text-right font-mono whitespace-nowrap">{eur(Math.abs(s.open))}</TableCell>
                  <TableCell><Badge className={STATUS[s.status].cls}>{STATUS[s.status].label}</Badge></TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    {s.issued_date ? fmtDate(s.issued_date) : <span className="text-muted-foreground">not recorded</span>}
                    {s.issued_on_time === false && (
                      <span className="block text-destructive" title={`Deadline was ${fmtDate(s.deadline)}`}>after deadline</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-0.5">
                      {s.status !== "settled" && s.amount > 0 && (s.kaution_available ?? 0) > 0.005 && (
                        <Button variant="ghost" size="icon" title="Settle from Kaution" aria-label="Settle from Kaution"
                          onClick={() => setFromKaution(s)}>
                          <Vault className="size-4" />
                        </Button>
                      )}
                      {s.status !== "settled" && (
                        <Button variant="ghost" size="icon" title={s.amount < 0 ? "Record refund" : "Record payment"}
                          aria-label={s.amount < 0 ? "Record refund" : "Record payment"} onClick={() => setPaying(s)}>
                          <Banknote className="size-4" />
                        </Button>
                      )}
                      {s.has_pdf && (
                        <Button variant="ghost" size="icon" title="Download PDF" aria-label="Download PDF"
                          onClick={() => downloadSettlementPdf(s)}>
                          <FileDown className="size-4" />
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" title="Edit" aria-label="Edit" onClick={() => setDialog({ editing: s })}>
                        <Pencil className="size-4" />
                      </Button>
                      <ConfirmButton onConfirm={() => remove.mutate(s.id)} title="Delete settlement?"
                        message={s.paid !== 0
                          ? `Payments of ${eur(Math.abs(s.paid))} are booked against it. They stay in Rent Tracking as NK settlement payments, just no longer linked.`
                          : "The settlement and its stored PDF will be removed."}>
                        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label="Delete">
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
      </Card>

      <BillsSection />

      <SettlementDialog
        open={!!dialog}
        onOpenChange={(o) => { if (!o) setDialog(null); }}
        contracts={contracts}
        draft={dialog?.draft}
        editing={dialog?.editing ?? null}
      />
      <SettlementPaymentDialog settlement={paying} onOpenChange={(o) => { if (!o) setPaying(null); }} />
      <KautionSettleDialog settlement={fromKaution} onOpenChange={(o) => { if (!o) setFromKaution(null); }} />
    </div>
  );
}
