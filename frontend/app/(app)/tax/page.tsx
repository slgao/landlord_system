"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TaxReport, TaxReportProperty } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, FileDown, Check, X, Pencil } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const eur = (v: number) =>
  v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

const SOURCE_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "destructive" }> = {
  payments: { label: "from recorded payments", variant: "secondary" },
  estimate: { label: "ESTIMATE — verify against bank", variant: "destructive" },
  override: { label: "manually entered", variant: "default" },
  computed: { label: "computed (annuity)", variant: "secondary" },
  manual: { label: "manual (bank statement)", variant: "default" },
  none: { label: "no data", variant: "secondary" },
};

function SourceBadge({ source }: { source: string }) {
  const b = SOURCE_BADGE[source] ?? { label: source, variant: "secondary" as const };
  return <Badge variant={b.variant} className="text-[10px]">{b.label}</Badge>;
}

/** Inline-editable derived value: click the pencil, type, Apply — stored as a
 * (property, year, field) override. Reset returns to the computed value. */
function OverrideField({ propertyId, year, field, value, overridden, computedHint }: {
  propertyId: number; year: number; field: string; value: number;
  overridden: boolean; computedHint?: number;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const save = useMutation({
    mutationFn: (v: number | null) =>
      api.put(`/api/tax/overrides/${propertyId}/${year}`, { field, value: v }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tax-report", year] });
      setEditing(false);
      toast.success("Saved");
    },
    onError: () => toast.error("Failed to save"),
  });

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1">
        <Input type="number" step="0.01" autoFocus className="h-7 w-28 font-mono text-right"
          value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && draft !== "") save.mutate(parseFloat(draft));
            if (e.key === "Escape") setEditing(false);
          }} />
        <Button size="sm" variant="outline" className="h-7 px-2"
          disabled={draft === "" || save.isPending}
          onClick={() => save.mutate(parseFloat(draft))}>
          <Check className="size-3.5" />
        </Button>
        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditing(false)}>
          <X className="size-3.5" />
        </Button>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      {overridden && computedHint !== undefined && (
        <span className="text-[10px] text-muted-foreground line-through">{eur(computedHint)}</span>
      )}
      <span className="font-mono">{eur(value)}</span>
      <button className="text-muted-foreground hover:text-foreground"
        title="Edit manually"
        onClick={(e) => { e.stopPropagation(); setDraft(String(value)); setEditing(true); }}>
        <Pencil className="size-3.5" />
      </button>
      {overridden && (
        <button className="text-[10px] text-muted-foreground hover:text-foreground underline"
          title="Remove manual value, back to computed"
          onClick={(e) => { e.stopPropagation(); save.mutate(null); }}>
          reset
        </button>
      )}
    </span>
  );
}

export default function TaxReportPage() {
  const qc = useQueryClient();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear - 1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [incomeDraft, setIncomeDraft] = useState<Record<number, string>>({});

  const { data: report, isLoading } = useQuery<TaxReport>({
    queryKey: ["tax-report", year],
    queryFn: () => api.get(`/api/tax/report?year=${year}`).then((r) => r.data),
  });

  const setOverride = useMutation({
    mutationFn: (v: { property_id: number; value: number | null }) =>
      api.put(`/api/tax/overrides/${v.property_id}/${year}`, {
        field: "income_total", value: v.value,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tax-report", year] });
      toast.success("Income updated");
    },
    onError: () => toast.error("Failed to save"),
  });

  async function downloadPdf(propertyId?: number) {
    const token = localStorage.getItem("token");
    const url = `${API}/api/tax/report/pdf?year=${year}` +
      (propertyId ? `&property_id=${propertyId}` : "");
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { toast.error("PDF failed"); return; }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `Anlage_V_Ausfuellhilfe_${year}${propertyId ? `_${propertyId}` : ""}.pdf`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Tax Report"
        description="Anlage V helper — per-property income and Werbungskosten for a tax year"
      />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-1">
          {[currentYear - 3, currentYear - 2, currentYear - 1, currentYear].map((y) => (
            <Button key={y} size="sm" variant={y === year ? "default" : "outline"}
              onClick={() => { setYear(y); setExpanded(null); }}>
              {y}
            </Button>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={() => downloadPdf()}>
          <FileDown className="size-4 mr-1" /> PDF (all properties)
        </Button>
        <p className="text-xs text-muted-foreground">
          Figures are aids for ELSTER — not tax advice. Verify estimates against bank statements.
        </p>
      </div>

      {report && report.excluded_properties.length > 0 && (
        <p className="text-xs text-muted-foreground mb-3">
          Not in this report (excluded in Tax Setup): {report.excluded_properties.join(", ")}
        </p>
      )}

      {report && (
        <div className="grid grid-cols-3 gap-2 mb-4">
          <Card><CardContent className="p-3"><p className="text-[10px] uppercase tracking-wide text-muted-foreground">Income</p><p className="font-semibold">{eur(report.totals.income)}</p></CardContent></Card>
          <Card><CardContent className="p-3"><p className="text-[10px] uppercase tracking-wide text-muted-foreground">Werbungskosten</p><p className="font-semibold">{eur(report.totals.werbungskosten)}</p></CardContent></Card>
          <Card><CardContent className="p-3"><p className="text-[10px] uppercase tracking-wide text-muted-foreground">Result</p><p className={`font-semibold ${report.totals.result < 0 ? "text-destructive" : "text-emerald-400"}`}>{eur(report.totals.result)}</p></CardContent></Card>
        </div>
      )}

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : (
        <div className="space-y-3">
          {report?.properties.map((b: TaxReportProperty) => {
            const open = expanded === b.property_id;
            const wk = b.werbungskosten;
            const draft = incomeDraft[b.property_id] ?? String(b.income.final);
            return (
              <Card key={b.property_id}>
                <CardContent className="p-0">
                  <div
                    className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/20"
                    onClick={() => setExpanded(open ? null : b.property_id)}
                  >
                    <div className="flex items-center gap-3">
                      {open ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
                      <p className="font-medium">{b.property_name}</p>
                      <SourceBadge source={b.income.source} />
                    </div>
                    <div className="flex items-center gap-4 text-sm font-mono">
                      <span>{eur(b.income.final)}</span>
                      <span className="text-muted-foreground">− {eur(wk.total)}</span>
                      <span className={`font-semibold ${b.result < 0 ? "text-destructive" : "text-emerald-400"}`}>{eur(b.result)}</span>
                      <Button size="sm" variant="outline"
                        onClick={(e) => { e.stopPropagation(); downloadPdf(b.property_id); }}>
                        <FileDown className="size-4" />
                      </Button>
                    </div>
                  </div>

                  {open && (
                    <div className="border-t border-border text-sm">
                      {/* Income */}
                      <div className="p-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <p className="font-medium">Einnahmen</p>
                          <SourceBadge source={b.income.source} />
                        </div>
                        {b.income.source !== "payments" && b.income.estimate_rows.length > 0 && (
                          <Table>
                            <TableHeader><TableRow>
                              <TableHead>Tenant (contract est.)</TableHead>
                              <TableHead className="text-right">Months</TableHead>
                              <TableHead className="text-right">Rent</TableHead>
                              <TableHead className="text-right">Total</TableHead>
                            </TableRow></TableHeader>
                            <TableBody>
                              {b.income.estimate_rows.map((r, i) => (
                                <TableRow key={i}>
                                  <TableCell className="text-muted-foreground">{r.tenant}</TableCell>
                                  <TableCell className="text-right font-mono">{r.months}</TableCell>
                                  <TableCell className="text-right font-mono">{eur(r.rent)}</TableCell>
                                  <TableCell className="text-right font-mono">{eur(r.total)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        )}
                        {b.income.nk_known && b.income.kaltmiete !== null ? (
                          <div className="text-xs space-y-0.5">
                            <div className="flex justify-between items-center">
                              <span className="text-muted-foreground flex items-center gap-2">
                                Mieteinnahmen (Kaltmiete)
                                {b.income.split_source === "override" && <SourceBadge source="override" />}
                              </span>
                              <OverrideField propertyId={b.property_id} year={year}
                                field="income_kaltmiete" value={b.income.kaltmiete}
                                overridden={b.income.split_source === "override"} />
                            </div>
                            <div className="flex justify-between"><span className="text-muted-foreground">Umlagen (NK-Vorauszahlungen)</span><span className="font-mono">{eur(b.income.umlagen!)}</span></div>
                            <div className="flex justify-between font-medium"><span>Einnahmen gesamt</span><span className="font-mono">{eur(b.income.final)}</span></div>
                          </div>
                        ) : (
                          <div className="text-xs text-amber-500 flex items-center justify-between gap-2">
                            <span>
                              Kaltmiete/Umlagen split unavailable — set the NK-Vorauszahlung per
                              contract in Tax Setup, or enter the Kaltmiete manually:
                            </span>
                            <OverrideField propertyId={b.property_id} year={year}
                              field="income_kaltmiete" value={b.income.final} overridden={false} />
                          </div>
                        )}
                        {b.income.source === "payments" ? (
                          <div className="text-xs text-muted-foreground flex items-center justify-between">
                            <span>{b.income.payments_count} recorded payments · {eur(b.income.payments_total)} — total editable:</span>
                            <OverrideField propertyId={b.property_id} year={year} field="income_total"
                              value={b.income.final} overridden={false} />
                          </div>
                        ) : (
                          <div className="flex items-end gap-2">
                            <div>
                              <p className="text-xs text-muted-foreground mb-1">
                                Actual income {year} (from bank statements):
                              </p>
                              <Input type="number" step="0.01" className="h-8 w-40 font-mono"
                                value={draft}
                                onChange={(e) => setIncomeDraft((s) => ({ ...s, [b.property_id]: e.target.value }))} />
                            </div>
                            <Button size="sm" variant="outline"
                              disabled={setOverride.isPending || draft === ""}
                              onClick={() => setOverride.mutate({ property_id: b.property_id, value: parseFloat(draft) })}>
                              <Check className="size-4 mr-1" /> Apply
                            </Button>
                            {b.income.source === "override" && (
                              <Button size="sm" variant="ghost" className="text-muted-foreground"
                                onClick={() => { setIncomeDraft((s) => ({ ...s, [b.property_id]: "" })); setOverride.mutate({ property_id: b.property_id, value: null }); }}>
                                Reset to computed
                              </Button>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Werbungskosten */}
                      <div className="border-t border-border p-4 space-y-1">
                        <p className="font-medium mb-2">Werbungskosten</p>
                        <div className="flex justify-between items-center py-1">
                          <span className="text-muted-foreground">
                            AfA (building depreciation)
                            {wk.afa.source === "override" && <Badge variant="default" className="text-[10px] ml-2">manual</Badge>}
                            {wk.afa.source === "incomplete" && <span className="text-amber-500 ml-2 text-xs">purchase data missing — set up in Tax Setup or enter manually</span>}
                          </span>
                          <OverrideField propertyId={b.property_id} year={year} field="afa"
                            value={wk.afa.afa} overridden={wk.afa.source === "override"}
                            computedHint={wk.afa.computed_afa} />
                        </div>
                        <div className="flex justify-between items-center py-1">
                          <span className="text-muted-foreground flex items-center gap-2">
                            Schuldzinsen <SourceBadge source={wk.schuldzinsen.source} />
                          </span>
                          <OverrideField propertyId={b.property_id} year={year} field="schuldzinsen"
                            value={wk.schuldzinsen.final}
                            overridden={wk.schuldzinsen.source === "override"} />
                        </div>
                        {wk.schuldzinsen.computed.map((c, i) => (
                          <p key={i} className="text-xs text-muted-foreground pl-4">
                            {c.label}: interest {eur(c.interest)} · Tilgung {eur(c.tilgung)} · balance end {eur(c.balance_end)}
                          </p>
                        ))}
                        {wk.recurring_source !== "override" && wk.recurring.filter((r) => r.deductible).map((r, i) => (
                          <div key={i} className="flex justify-between py-1">
                            <span className="text-muted-foreground">{r.cost_type} <span className="text-xs">({r.months} × {eur(r.monthly)})</span></span>
                            <span className="font-mono">{eur(r.total)}</span>
                          </div>
                        ))}
                        <div className="flex justify-between items-center py-1">
                          <span className="text-muted-foreground flex items-center gap-2">
                            Recurring costs subtotal
                            {wk.recurring_source === "override" && <Badge variant="default" className="text-[10px]">manual</Badge>}
                          </span>
                          <OverrideField propertyId={b.property_id} year={year} field="recurring_total"
                            value={wk.recurring_total}
                            overridden={wk.recurring_source === "override"}
                            computedHint={wk.recurring_source === "override" ? wk.recurring_computed : undefined} />
                        </div>
                        {wk.one_off.map((e) => (
                          <div key={e.id} className="flex justify-between py-1">
                            <span className="text-muted-foreground">
                              {e.category}{e.vendor ? ` — ${e.vendor}` : ""} <span className="text-xs">({e.expense_date}{e.distribute_years > 1 ? ` · §82b /${e.distribute_years}y` : ""}{e.source_file ? ` · ${e.source_file.split("/").pop()}` : ""})</span>
                            </span>
                            <span className="font-mono">{eur(e.share_this_year)}</span>
                          </div>
                        ))}
                        <div className="flex justify-between py-1 border-t border-border mt-2 pt-2 font-medium">
                          <span>Total Werbungskosten</span>
                          <span className="font-mono">{eur(wk.total)}</span>
                        </div>
                        <div className="flex justify-between py-1 font-semibold">
                          <span>Überschuss / Verlust</span>
                          <span className={`font-mono ${b.result < 0 ? "text-destructive" : "text-emerald-400"}`}>{eur(b.result)}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
