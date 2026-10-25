"use client";

/**
 * What a tenancy has cost, period by period — and how a rent increase is
 * recorded.
 *
 * The rent used to be one number on the contract, so raising it restated the
 * past: every month of every closed year was suddenly expected to have earned
 * the new figure. Here each price keeps its own dates, which is also what
 * German rent law produces on its own — §558 allows an increase every fifteen
 * months, §557a agrees the steps of a Staffelmiete years ahead, §557b follows
 * the index, §559 adds a modernisation surcharge.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { Contract, RentPeriod } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ConfirmButton } from "@/components/confirm-button";
import { toast } from "sonner";
import { CalendarClock, History, Trash2, TrendingUp } from "lucide-react";
import { todayISO } from "@/lib/utils";
import { eur } from "@/lib/nk-format";

const KINDS: { value: RentPeriod["kind"]; label: string }[] = [
  { value: "agreed", label: "Mieterhöhung (§558 BGB)" },
  { value: "staffel", label: "Staffelmiete (§557a BGB)" },
  { value: "index", label: "Indexmiete (§557b BGB)" },
  { value: "modernisation", label: "Modernisierung (§559 BGB)" },
];

/** Where a price sits relative to today: already over, in force, or agreed
 *  but not started yet — the same three states flat costs have. */
function phase(p: RentPeriod): "past" | "current" | "upcoming" {
  if (p.current) return "current";
  return p.valid_from > todayISO() ? "upcoming" : "past";
}

export function RentHistoryDialog({ contract, onClose }: {
  contract: Contract | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    valid_from: "", rent: 0, nebenkosten_vorauszahlung: "" as string | number,
    kind: "agreed" as RentPeriod["kind"], note: "",
  });

  const { data: periods = [], isLoading } = useQuery<RentPeriod[]>({
    queryKey: ["contract-rents", contract?.id],
    queryFn: () => api.get(`/api/contracts/${contract!.id}/rents`).then((r) => r.data),
    enabled: !!contract,
  });

  // Every figure that reads a rent moves with this, so they all refresh.
  function invalidate() {
    for (const k of ["contract-rents", "contracts", "contracts-all", "payments",
                     "balance-sheet", "balance-sheet-dash", "tax-report",
                     "flat-insights", "payment-reminders", "nk-splits"]) {
      qc.invalidateQueries({ queryKey: [k] });
    }
  }

  const add = useMutation({
    mutationFn: () => api.post(`/api/contracts/${contract!.id}/rents`, {
      valid_from: form.valid_from,
      rent: Number(form.rent),
      nebenkosten_vorauszahlung:
        form.nebenkosten_vorauszahlung === "" ? null : Number(form.nebenkosten_vorauszahlung),
      kind: form.kind,
      note: form.note.trim() || null,
    }),
    onSuccess: () => {
      invalidate();
      toast.success("Recorded — the months before it keep the old rent");
      setForm((f) => ({ ...f, note: "" }));
    },
    onError: (e) => toast.error(errorMessage(e, "Could not record the new rent")),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/contracts/${contract!.id}/rents/${id}`),
    onSuccess: () => { invalidate(); toast.success("Removed"); },
    onError: (e) => toast.error(errorMessage(e, "Could not remove that price")),
  });

  const current = periods.find((p) => p.current);
  const upcoming = periods.filter((p) => phase(p) === "upcoming");

  return (
    <Dialog open={!!contract} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Rent history</DialogTitle>
        </DialogHeader>
        {contract && (
          <div className="space-y-4 py-1">
            <p className="text-sm text-muted-foreground">
              {contract.tenant_name} · {contract.apartment_name}
              <br />
              Each price keeps its own dates, so recording an increase leaves
              the months before it at what was actually owed.
            </p>

            <div className="rounded-md border border-border divide-y divide-border">
              {isLoading ? (
                <p className="p-3 text-sm text-muted-foreground">Loading…</p>
              ) : periods.map((p) => {
                const ph = phase(p);
                return (
                  <div key={p.id}
                    className={`flex items-start justify-between gap-3 p-3 ${ph === "past" ? "opacity-60" : ""}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-medium tabular-nums">
                        {eur(p.rent)}
                        <span className="text-xs text-muted-foreground font-normal">
                          {" "}· kalt {eur(p.cold_rent)}
                        </span>
                        {ph === "current" && (
                          <Badge variant="secondary" className="ml-2 text-[10px] px-1.5 py-0">
                            charged now
                          </Badge>
                        )}
                        {ph === "upcoming" && (
                          <Badge variant="secondary" className="ml-2 text-[10px] px-1.5 py-0
                            bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/20">
                            <CalendarClock className="size-3 mr-1" /> from {p.valid_from}
                          </Badge>
                        )}
                        {ph === "past" && (
                          <Badge variant="secondary" className="ml-2 text-[10px] px-1.5 py-0">
                            <History className="size-3 mr-1" /> earlier rent
                          </Badge>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        from {p.valid_from || "the start"} · {p.kind_label}
                        {p.note ? ` · ${p.note}` : ""}
                      </p>
                    </div>
                    {periods.length > 1 && (
                      <ConfirmButton onConfirm={() => remove.mutate(p.id)}
                        title="Remove this price?"
                        message={`Remove ${eur(p.rent)} from ${p.valid_from}? The months it covered fall back to the price before it.`}>
                        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive shrink-0">
                          <Trash2 className="size-4" />
                        </Button>
                      </ConfirmButton>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="rounded-md border border-border p-3 space-y-3">
              <p className="text-sm font-medium flex items-center gap-1.5">
                <TrendingUp className="size-4" /> Record a new rent
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="rent-from">Charged from</Label>
                  <Input id="rent-from" type="date" value={form.valid_from}
                    onChange={(e) => setForm((f) => ({ ...f, valid_from: e.target.value }))} />
                  <p className="text-xs text-muted-foreground">
                    Usually ahead: an increase is owed from the start of the third
                    month after the tenant receives it.
                  </p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rent-amount">New rent (€)</Label>
                  <Input id="rent-amount" type="number" step="0.01" min="0"
                    value={form.rent || ""}
                    onChange={(e) => setForm((f) => ({ ...f, rent: Number(e.target.value) }))} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rent-nk">of it Nebenkosten (€)</Label>
                  <Input id="rent-nk" type="number" step="0.01" min="0"
                    placeholder={current?.nebenkosten_vorauszahlung?.toFixed(2) ?? ""}
                    value={form.nebenkosten_vorauszahlung}
                    onChange={(e) => setForm((f) => ({ ...f, nebenkosten_vorauszahlung: e.target.value }))} />
                </div>
                <div className="space-y-1.5">
                  <Label>Grounds</Label>
                  <Select value={form.kind}
                    onValueChange={(v) => setForm((f) => ({ ...f, kind: v as RentPeriod["kind"] }))}>
                    <SelectTrigger aria-label="Grounds"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {KINDS.map((k) => (
                        <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rent-note">Note (optional)</Label>
                <Input id="rent-note" placeholder="Mietspiegel 2026, Kappungsgrenze eingehalten"
                  value={form.note}
                  onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
              </div>
              <Button onClick={() => add.mutate()}
                disabled={!form.valid_from || !form.rent || add.isPending}>
                Record
              </Button>
            </div>

            {upcoming.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {upcoming.length} price{upcoming.length === 1 ? "" : "s"} already on file
                for later: {upcoming.map((p) => `${eur(p.rent)} from ${p.valid_from}`).join(", ")}.
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
