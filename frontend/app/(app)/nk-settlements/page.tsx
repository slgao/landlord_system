"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { Contract, NKSettlement, PendingAbrechnung } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ConfirmButton } from "@/components/confirm-button";
import {
  SettlementDialog, SettlementPaymentDialog, SettlementDraft,
  downloadSettlementPdf, eur, fmtDate, invalidateSettlementViews, resultLabel,
} from "@/components/nk-settlements";
import { toast } from "sonner";
import { FileDown, Pencil, Trash2, Banknote, CalendarClock } from "lucide-react";

const STATUS: Record<NKSettlement["status"], { label: string; cls: string }> = {
  open:     { label: "Open",    cls: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/20" },
  partial:  { label: "Partly paid", cls: "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/20" },
  settled:  { label: "Settled", cls: "bg-primary/15 text-primary border-primary/20" },
};

export default function NKSettlementsPage() {
  const qc = useQueryClient();
  const [dialog, setDialog] = useState<{ draft?: SettlementDraft; editing?: NKSettlement } | null>(null);
  const [paying, setPaying] = useState<NKSettlement | null>(null);

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
                  <Button size="sm" variant="outline" onClick={() => setDialog({
                    draft: { contract_id: p.contract_id, period_start: p.period_start, period_end: p.period_end },
                  })}>
                    Record
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
                  </TableCell>
                  <TableCell className={`whitespace-nowrap ${s.amount > 0 ? "text-destructive" : "text-primary"}`}>
                    {resultLabel(s.amount)}
                  </TableCell>
                  <TableCell className="text-right font-mono whitespace-nowrap">{eur(Math.abs(s.paid))}</TableCell>
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

      <SettlementDialog
        open={!!dialog}
        onOpenChange={(o) => { if (!o) setDialog(null); }}
        contracts={contracts}
        draft={dialog?.draft}
        editing={dialog?.editing ?? null}
      />
      <SettlementPaymentDialog settlement={paying} onOpenChange={(o) => { if (!o) setPaying(null); }} />
    </div>
  );
}
