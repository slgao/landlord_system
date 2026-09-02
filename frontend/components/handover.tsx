"use client";

/**
 * Übergabeprotokoll — the sheet you fill in when the keys change hands.
 *
 * Two protocols matter per tenancy, Einzug and Auszug, and the card shows them
 * as two fixed slots rather than a list: "did I do this?" is the question a
 * landlord actually has, and a list of zero rows answers it badly.
 *
 * Zählerstände are written straight into meter_readings (tagged with the
 * protocol), so a move-out reading is immediately the one the
 * Nebenkostenabrechnung uses. Nothing has to be typed twice.
 */

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  Contract, HandoverProtocol, ProtocolItem, ProtocolReading, ProtocolKind,
  ItemCondition, StromMeter, GasMeter, WasserMeter, HeizungMeter,
} from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { ConfirmButton } from "@/components/confirm-button";
import {
  ClipboardList, Plus, Trash2, FileDown, KeyRound, Gauge, LogIn, LogOut,
  CheckCircle2, AlertTriangle, PenLine, Home,
} from "lucide-react";

const KIND_META: Record<ProtocolKind, { label: string; german: string; icon: typeof LogIn }> = {
  move_in:  { label: "Move-in",  german: "Einzug", icon: LogIn },
  move_out: { label: "Move-out", german: "Auszug", icon: LogOut },
};

// The three states are the legally meaningful split, not a severity scale:
// "wear" (normale Abnutzung) may never be charged to the tenant, "defect"
// (Mangel) may. The wording on the buttons says so, because that distinction is
// what the landlord is actually deciding when they tap one.
const CONDITIONS: { value: ItemCondition; label: string; hint: string; cls: string }[] = [
  { value: "ok",     label: "OK",     hint: "In Ordnung",                    cls: "bg-primary/15 text-primary border-primary/30" },
  { value: "wear",   label: "Wear",   hint: "Normale Abnutzung — not chargeable", cls: "bg-muted text-muted-foreground border-border" },
  { value: "defect", label: "Defect", hint: "Mangel — chargeable to tenant", cls: "bg-destructive/15 text-destructive border-destructive/30" },
];

const COMMON_AREAS = [
  "Küche", "Bad", "WC", "Wohnzimmer", "Schlafzimmer", "Flur", "Balkon",
  "Keller", "Böden", "Wände & Decken", "Fenster", "Türen", "Heizkörper",
];
const COMMON_KEYS = ["Wohnungstür", "Haustür", "Briefkasten", "Keller", "Garage", "Dachboden"];

const METER_LABEL: Record<string, string> = {
  strom: "Strom", gas: "Gas", wasser: "Wasser", heizung: "Heizung",
};

const today = () => new Date().toISOString().split("T")[0];

// Matches the Kaution card this sits under. A de-DE locale format would be more
// correct in isolation but puts "180,00" next to "1000.00" in the same view.
function fmt(n: number) {
  return n.toFixed(2);
}

// ─────────────────────────────────────────────────────────────────────────────
// Card — two slots on the contract detail page
// ─────────────────────────────────────────────────────────────────────────────

export function HandoverCard({
  contract, onKautionChanged,
}: {
  contract: Contract;
  onKautionChanged?: () => void;
}) {
  const qc = useQueryClient();
  const [openProtocol, setOpenProtocol] = useState<HandoverProtocol | null>(null);

  const { data: protocols = [] } = useQuery<HandoverProtocol[]>({
    queryKey: ["handover-protocols", contract.id],
    queryFn: () => api.get(`/api/handover-protocols/?contract_id=${contract.id}`).then((r) => r.data),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["handover-protocols", contract.id] });
    // A handover writes meter readings, so the readings pages must refetch too.
    qc.invalidateQueries({ queryKey: ["meter-readings"] });
    qc.invalidateQueries({ queryKey: ["strom-readings-all"] });
  };

  const create = useMutation({
    mutationFn: (kind: ProtocolKind) =>
      api.post("/api/handover-protocols/", {
        contract_id: contract.id,
        kind,
        // Prefilled from the contract: a handover happens on the day the
        // tenancy starts or ends far more often than not.
        date: (kind === "move_in" ? contract.start_date : contract.end_date) || today(),
      }).then((r) => r.data as HandoverProtocol),
    onSuccess: (p) => { invalidate(); setOpenProtocol(p); },
    onError: () => toast.error("Could not create the protocol"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/handover-protocols/${id}`),
    onSuccess: () => { invalidate(); toast.success("Protocol deleted"); },
  });

  async function downloadPdf(p: HandoverProtocol) {
    try {
      const res = await api.get(`/api/handover-protocols/${p.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Uebergabeprotokoll_${KIND_META[p.kind].german}_${contract.tenant_name || ""}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Could not generate the PDF");
    }
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <ClipboardList className="size-4" />Übergabeprotokoll
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            What was recorded when the keys changed hands. Meter readings taken here
            feed the Nebenkostenabrechnung directly.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {(["move_in", "move_out"] as ProtocolKind[]).map((kind) => {
              const list = protocols.filter((p) => p.kind === kind);
              const Icon = KIND_META[kind].icon;
              return (
                <div key={kind} className="rounded-md border border-border p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <Icon className="size-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{KIND_META[kind].german}</span>
                    <span className="text-xs text-muted-foreground">{KIND_META[kind].label}</span>
                  </div>

                  {list.length === 0 ? (
                    <>
                      <p className="text-xs text-muted-foreground">Not recorded yet.</p>
                      <Button size="sm" variant="outline" className="w-full"
                              onClick={() => create.mutate(kind)} disabled={create.isPending}>
                        <Plus className="size-4 mr-1" />Record {KIND_META[kind].german}
                      </Button>
                    </>
                  ) : (
                    <div className="space-y-2">
                      {list.map((p) => (
                        <div key={p.id} className="space-y-1.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-mono tabular-nums">{p.date || "—"}</span>
                            {p.signed ? (
                              <Badge variant="outline" className="bg-primary/15 text-primary border-primary/30 text-[10px]">
                                <CheckCircle2 className="size-3 mr-1" />Signed
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-[10px] text-muted-foreground">
                                <PenLine className="size-3 mr-1" />Draft
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {p.reading_count} Zählerstände · {p.item_count} {p.item_count === 1 ? "entry" : "entries"}
                            {p.defect_count > 0 && (
                              <span className="text-destructive">
                                {" · "}{p.defect_count} {p.defect_count === 1 ? "Mangel" : "Mängel"}
                              </span>
                            )}
                          </p>
                          <div className="flex gap-1">
                            <Button size="sm" variant="outline" className="h-7 text-xs"
                                    onClick={() => setOpenProtocol(p)}>Open</Button>
                            <Button size="sm" variant="ghost" className="h-7 text-xs"
                                    onClick={() => downloadPdf(p)}>
                              <FileDown className="size-3 mr-1" />PDF
                            </Button>
                            <ConfirmButton
                              onConfirm={() => remove.mutate(p.id)}
                              title="Delete protocol?"
                              message="The findings are deleted. Meter readings taken at this handover are kept — they belong to the Nebenkostenabrechnung."
                            >
                              <Button size="sm" variant="ghost" className="h-7 px-2">
                                <Trash2 className="size-3 text-destructive" />
                              </Button>
                            </ConfirmButton>
                          </div>
                        </div>
                      ))}
                      <Button size="sm" variant="ghost" className="h-7 text-xs w-full"
                              onClick={() => create.mutate(kind)} disabled={create.isPending}>
                        <Plus className="size-3 mr-1" />Add another
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <DefectBridge contract={contract} protocols={protocols} onKautionChanged={onKautionChanged} />
        </CardContent>
      </Card>

      {openProtocol && (
        <ProtocolDialog
          protocol={openProtocol}
          contract={contract}
          onClose={() => { setOpenProtocol(null); invalidate(); }}
        />
      )}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// The link the whole feature exists for: a Mangel found at Auszug is exactly a
// Kaution deduction. Without this the landlord writes the damage down twice, in
// two places that then disagree.
// ─────────────────────────────────────────────────────────────────────────────

function DefectBridge({
  contract, protocols, onKautionChanged,
}: {
  contract: Contract;
  protocols: HandoverProtocol[];
  onKautionChanged?: () => void;
}) {
  const qc = useQueryClient();
  const moveOuts = protocols.filter((p) => p.kind === "move_out" && p.defect_count > 0);
  const [busy, setBusy] = useState(false);

  if (moveOuts.length === 0) return null;

  const totalDefects = moveOuts.reduce((s, p) => s + p.defect_count, 0);
  const totalCost = moveOuts.reduce((s, p) => s + p.defect_cost, 0);

  // The reason line doubles as the identity of a converted defect. Pressing the
  // button twice must not charge the tenant twice, and there is no "converted"
  // flag on the item to key off — so a defect whose reason is already on the
  // ledger is skipped. Editing a deduction's reason afterwards un-links it, which
  // is the right trade: an edited row is the landlord's own, and re-adding is
  // visible and reversible where a silent double-charge would not be.
  const reasonFor = (it: ProtocolItem, p: HandoverProtocol) =>
    `${it.area || "Mangel"}${it.note ? ` — ${it.note}` : ""} (Übergabeprotokoll ${p.date})`;

  async function addDeductions() {
    setBusy(true);
    try {
      const existing: { reason?: string | null }[] =
        (await api.get(`/api/kaution-deductions/?contract_id=${contract.id}`)).data;
      const already = new Set(existing.map((d) => d.reason || ""));

      let made = 0;
      let skipped = 0;
      for (const p of moveOuts) {
        const items: ProtocolItem[] = (
          await api.get(`/api/protocol-items/?protocol_id=${p.id}`)
        ).data;
        for (const it of items.filter((i) => i.condition === "defect" && (i.estimated_cost || 0) > 0)) {
          const reason = reasonFor(it, p);
          if (already.has(reason)) { skipped++; continue; }
          await api.post("/api/kaution-deductions/", {
            contract_id: contract.id,
            date: p.date,
            amount: it.estimated_cost,
            category: "Schaden",
            reason,
          });
          already.add(reason);
          made++;
        }
      }
      qc.invalidateQueries({ queryKey: ["kaution-deductions", contract.id] });
      onKautionChanged?.();
      if (made) {
        toast.success(`${made} deduction${made === 1 ? "" : "s"} added to the Kaution`
          + (skipped ? ` · ${skipped} already there` : ""));
      } else if (skipped) {
        toast.info("Already added to the Kaution");
      } else {
        toast.info("No Mangel has an estimated cost yet");
      }
    } catch {
      toast.error("Could not create the deductions");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 space-y-2">
      <p className="text-sm flex items-center gap-2">
        <AlertTriangle className="size-4 text-amber-400 shrink-0" />
        <span>
          <span className="font-medium">
            {totalDefects} {totalDefects === 1 ? "Mangel" : "Mängel"} recorded at Auszug
          </span>
          {totalCost > 0 && <> · estimated {fmt(totalCost)}</>}
        </span>
      </p>
      <p className="text-xs text-muted-foreground">
        These are what you may charge against the deposit — normale Abnutzung is not.
        Adding them creates one Kaution deduction per defect, which you can still edit above.
      </p>
      <Button size="sm" variant="outline" onClick={addDeductions} disabled={busy || totalCost <= 0}>
        Add as Kaution deductions
      </Button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Editor
// ─────────────────────────────────────────────────────────────────────────────

function ProtocolDialog({
  protocol, contract, onClose,
}: {
  protocol: HandoverProtocol;
  contract: Contract;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const pid = protocol.id;
  const [head, setHead] = useState({
    date: protocol.date || today(),
    time: protocol.time || "",
    present_persons: protocol.present_persons || "",
    note: protocol.note || "",
    signed: protocol.signed,
  });

  const items = useQuery<ProtocolItem[]>({
    queryKey: ["protocol-items", pid],
    queryFn: () => api.get(`/api/protocol-items/?protocol_id=${pid}`).then((r) => r.data),
  });
  const readings = useQuery<ProtocolReading[]>({
    queryKey: ["protocol-readings", pid],
    queryFn: () => api.get(`/api/handover-protocols/${pid}/readings`).then((r) => r.data),
  });

  // Every meter registered on this flat, so the Zählerstand section is a
  // ready-made checklist instead of a blank form the landlord has to remember
  // the meters for.
  const aid = contract.apartment_id;
  const strom = useQuery<StromMeter[]>({ queryKey: ["strom-meters", aid], queryFn: () => api.get(`/api/meters/strom?apartment_id=${aid}`).then((r) => r.data) });
  const gas = useQuery<GasMeter[]>({ queryKey: ["gas-meters", aid], queryFn: () => api.get(`/api/meters/gas?apartment_id=${aid}`).then((r) => r.data) });
  const wasser = useQuery<WasserMeter[]>({ queryKey: ["wasser-meters", aid], queryFn: () => api.get(`/api/meters/wasser?apartment_id=${aid}`).then((r) => r.data) });
  const heizung = useQuery<HeizungMeter[]>({ queryKey: ["heizung-meters", aid], queryFn: () => api.get(`/api/meters/heizung?apartment_id=${aid}`).then((r) => r.data) });

  const meters = [
    ...(strom.data || []).map((m) => ({ type: "strom", ...m })),
    ...(gas.data || []).map((m) => ({ type: "gas", ...m })),
    ...(wasser.data || []).map((m: any) => ({ type: "wasser", ...m, description: m.description || m.type })),
    ...(heizung.data || []).map((m) => ({ type: "heizung", ...m })),
  ];

  const saveHead = useMutation({
    mutationFn: () => api.put(`/api/handover-protocols/${pid}`, head),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["handover-protocols", contract.id] }); toast.success("Saved"); },
    onError: () => toast.error("Could not save"),
  });

  const invalidateItems = () => qc.invalidateQueries({ queryKey: ["protocol-items", pid] });
  const invalidateReadings = () => {
    qc.invalidateQueries({ queryKey: ["protocol-readings", pid] });
    qc.invalidateQueries({ queryKey: ["meter-readings"] });
    qc.invalidateQueries({ queryKey: ["strom-readings-all"] });
  };

  const addItem = useMutation({
    mutationFn: (body: Partial<ProtocolItem>) =>
      api.post("/api/protocol-items/", { protocol_id: pid, sort_order: 0, ...body }),
    onSuccess: invalidateItems,
  });
  const patchItem = useMutation({
    mutationFn: (it: ProtocolItem) => api.put(`/api/protocol-items/${it.id}`, it),
    onSuccess: invalidateItems,
  });
  const dropItem = useMutation({
    mutationFn: (id: number) => api.delete(`/api/protocol-items/${id}`),
    onSuccess: invalidateItems,
  });
  const saveReading = useMutation({
    mutationFn: (body: { meter_type: string; meter_id: number; reading: number }) =>
      api.post(`/api/handover-protocols/${pid}/readings`, body),
    onSuccess: invalidateReadings,
    onError: () => toast.error("Could not save the reading"),
  });
  const dropReading = useMutation({
    mutationFn: (id: number) => api.delete(`/api/handover-protocols/${pid}/readings/${id}`),
    onSuccess: invalidateReadings,
  });

  const conditions = (items.data || []).filter((i) => i.kind === "condition");
  const keys = (items.data || []).filter((i) => i.kind === "key");
  const defectTotal = conditions
    .filter((i) => i.condition === "defect")
    .reduce((s, i) => s + (i.estimated_cost || 0), 0);

  const kindDe = KIND_META[protocol.kind].german;
  const usedAreas = new Set(conditions.map((c) => c.area));
  const usedKeys = new Set(keys.map((k) => k.area));

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Übergabeprotokoll · {kindDe}
            <span className="text-sm font-normal text-muted-foreground">
              {contract.tenant_name} — {contract.apartment_name}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* ── The meeting ── */}
          <section className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <Label className="text-xs">Date</Label>
                <Input type="date" value={head.date}
                       onChange={(e) => setHead({ ...head, date: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Time</Label>
                <Input type="time" value={head.time}
                       onChange={(e) => setHead({ ...head, time: e.target.value })} />
              </div>
              <div className="col-span-2">
                <Label className="text-xs">Present (Anwesend)</Label>
                <Input placeholder="Landlord, tenant, witness…" value={head.present_persons}
                       onChange={(e) => setHead({ ...head, present_persons: e.target.value })} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Changing the date moves the Zählerstände with it — they are dated by the handover.
            </p>
          </section>

          {/* ── Zählerstände ── */}
          <section className="space-y-2">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <Gauge className="size-4" />Zählerstände
            </h3>
            {meters.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No meters registered for this flat. Add them under Meter Readings first,
                then they appear here as a checklist.
              </p>
            ) : (
              <div className="space-y-1.5">
                {meters.map((m: any) => {
                  const existing = (readings.data || []).find(
                    (r) => r.meter_type === m.type && r.meter_id === m.id);
                  return (
                    <MeterRow
                      key={`${m.type}:${m.id}`}
                      meter={m}
                      existing={existing}
                      onSave={(v) => saveReading.mutate({ meter_type: m.type, meter_id: m.id, reading: v })}
                      onClear={() => existing && dropReading.mutate(existing.id)}
                    />
                  );
                })}
              </div>
            )}
          </section>

          {/* ── Zustand ── */}
          <section className="space-y-2">
            <div className="flex items-baseline justify-between">
              <h3 className="text-sm font-medium flex items-center gap-2">
                <Home className="size-4" />Zustand der Wohnung
              </h3>
              {defectTotal > 0 && (
                <span className="text-xs text-destructive">
                  Mängel estimated at {fmt(defectTotal)}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              <span className="text-muted-foreground">Wear</span> is normale Abnutzung and cannot be
              charged to the tenant. <span className="text-destructive">Defect</span> can — and becomes
              a deposit deduction.
            </p>

            <div className="flex flex-wrap gap-1">
              {COMMON_AREAS.filter((a) => !usedAreas.has(a)).map((a) => (
                <Button key={a} size="sm" variant="outline" className="h-7 text-xs"
                        onClick={() => addItem.mutate({ kind: "condition", area: a, condition: "ok" })}>
                  <Plus className="size-3 mr-1" />{a}
                </Button>
              ))}
              <Button size="sm" variant="ghost" className="h-7 text-xs"
                      onClick={() => addItem.mutate({ kind: "condition", area: "", condition: "ok" })}>
                <Plus className="size-3 mr-1" />Other…
              </Button>
            </div>

            {conditions.length > 0 && (
              <div className="space-y-1.5">
                {conditions.map((it) => (
                  <ConditionRow key={it.id} item={it}
                                onChange={(v) => patchItem.mutate(v)}
                                onDelete={() => dropItem.mutate(it.id)} />
                ))}
              </div>
            )}
          </section>

          {/* ── Schlüssel ── */}
          <section className="space-y-2">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <KeyRound className="size-4" />Schlüssel
              <span className="text-xs font-normal text-muted-foreground">
                {protocol.kind === "move_in" ? "handed to the tenant" : "returned by the tenant"}
              </span>
            </h3>
            <div className="flex flex-wrap gap-1">
              {COMMON_KEYS.filter((k) => !usedKeys.has(k)).map((k) => (
                <Button key={k} size="sm" variant="outline" className="h-7 text-xs"
                        onClick={() => addItem.mutate({ kind: "key", area: k, quantity: 1 })}>
                  <Plus className="size-3 mr-1" />{k}
                </Button>
              ))}
              <Button size="sm" variant="ghost" className="h-7 text-xs"
                      onClick={() => addItem.mutate({ kind: "key", area: "", quantity: 1 })}>
                <Plus className="size-3 mr-1" />Other…
              </Button>
            </div>
            {keys.length > 0 && (
              <div className="space-y-1.5">
                {keys.map((it) => (
                  <KeyRow key={it.id} item={it}
                          onChange={(v) => patchItem.mutate(v)}
                          onDelete={() => dropItem.mutate(it.id)} />
                ))}
              </div>
            )}
          </section>

          {/* ── Notes + signed ── */}
          <section className="space-y-2">
            <Label className="text-xs">Sonstige Vereinbarungen</Label>
            <Textarea rows={3} value={head.note}
                      placeholder="Agreements made at the handover…"
                      onChange={(e) => setHead({ ...head, note: e.target.value })} />
            <Button
              type="button" size="sm"
              variant={head.signed ? "default" : "outline"}
              onClick={() => setHead({ ...head, signed: !head.signed })}
            >
              <CheckCircle2 className="size-4 mr-1" />
              {head.signed ? "Signed by both parties" : "Mark as signed"}
            </Button>
          </section>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>Close</Button>
          <Button onClick={() => saveHead.mutate()} disabled={saveHead.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Rows ─────────────────────────────────────────────────────────────────────

function MeterRow({
  meter, existing, onSave, onClear,
}: {
  meter: any;
  existing?: ProtocolReading;
  onSave: (v: number) => void;
  onClear: () => void;
}) {
  const [value, setValue] = useState(existing ? String(existing.reading) : "");
  // A refetch after saving (or opening a protocol that already has readings)
  // has to win over the local draft, or the field would show a stale number.
  useEffect(() => { setValue(existing ? String(existing.reading) : ""); },
            [existing?.id, existing?.reading]);

  const dirty = value !== "" && Number(value) !== (existing?.reading ?? NaN);

  return (
    <div className="flex items-center gap-2 text-sm">
      <div className="flex-1 min-w-0">
        <span className="font-medium">{METER_LABEL[meter.type] || meter.type}</span>
        {meter.description && <span className="text-muted-foreground"> — {meter.description}</span>}
        {meter.serial_number && (
          <span className="text-xs text-muted-foreground font-mono"> · {meter.serial_number}</span>
        )}
      </div>
      <Input
        type="number" step="0.001" className="h-8 w-36 text-sm"
        placeholder="Zählerstand" value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && dirty) onSave(Number(value)); }}
      />
      <Button size="sm" variant={dirty ? "default" : "ghost"} className="h-8 text-xs"
              disabled={!dirty} onClick={() => onSave(Number(value))}>
        Save
      </Button>
      <Button size="sm" variant="ghost" className="h-8 px-2"
              disabled={!existing} onClick={onClear}>
        <Trash2 className="size-3 text-destructive" />
      </Button>
    </div>
  );
}

function ConditionRow({
  item, onChange, onDelete,
}: {
  item: ProtocolItem;
  onChange: (v: ProtocolItem) => void;
  onDelete: () => void;
}) {
  const [draft, setDraft] = useState(item);
  useEffect(() => { setDraft(item); }, [item.id, item.area, item.condition, item.note, item.estimated_cost]);

  const commit = (v: ProtocolItem) => { setDraft(v); onChange(v); };

  return (
    <div className="rounded-md border border-border p-2 space-y-2">
      <div className="flex items-center gap-2">
        <Input className="h-8 text-sm flex-1" placeholder="Area (e.g. Küche)"
               value={draft.area || ""}
               onChange={(e) => setDraft({ ...draft, area: e.target.value })}
               onBlur={() => draft.area !== item.area && onChange(draft)} />
        <div className="flex gap-1">
          {CONDITIONS.map((c) => (
            <Button
              key={c.value} size="sm" variant="outline" title={c.hint}
              className={`h-8 text-xs ${draft.condition === c.value ? c.cls : "text-muted-foreground"}`}
              onClick={() => commit({ ...draft, condition: c.value })}
            >
              {c.label}
            </Button>
          ))}
        </div>
        <Button size="sm" variant="ghost" className="h-8 px-2" onClick={onDelete}>
          <Trash2 className="size-3 text-destructive" />
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Input className="h-8 text-sm flex-1" placeholder="Note"
               value={draft.note || ""}
               onChange={(e) => setDraft({ ...draft, note: e.target.value })}
               onBlur={() => draft.note !== item.note && onChange(draft)} />
        {/* Only a Mangel carries a cost — asking for one next to "normale
            Abnutzung" would invite charging for exactly what may not be charged. */}
        {draft.condition === "defect" && (
          <Input type="number" step="0.01" className="h-8 w-32 text-sm" placeholder="Est. cost"
                 value={draft.estimated_cost ?? ""}
                 onChange={(e) => setDraft({ ...draft, estimated_cost: e.target.value === "" ? null : Number(e.target.value) })}
                 onBlur={() => draft.estimated_cost !== item.estimated_cost && onChange(draft)} />
        )}
      </div>
    </div>
  );
}

function KeyRow({
  item, onChange, onDelete,
}: {
  item: ProtocolItem;
  onChange: (v: ProtocolItem) => void;
  onDelete: () => void;
}) {
  const [draft, setDraft] = useState(item);
  useEffect(() => { setDraft(item); }, [item.id, item.area, item.quantity, item.note]);

  return (
    <div className="flex items-center gap-2">
      <Input className="h-8 text-sm flex-1" placeholder="Key type"
             value={draft.area || ""}
             onChange={(e) => setDraft({ ...draft, area: e.target.value })}
             onBlur={() => draft.area !== item.area && onChange(draft)} />
      <Input type="number" min="0" className="h-8 w-20 text-sm" placeholder="Qty"
             value={draft.quantity ?? ""}
             onChange={(e) => setDraft({ ...draft, quantity: e.target.value === "" ? null : Number(e.target.value) })}
             onBlur={() => draft.quantity !== item.quantity && onChange(draft)} />
      <Input className="h-8 text-sm flex-1" placeholder="Note"
             value={draft.note || ""}
             onChange={(e) => setDraft({ ...draft, note: e.target.value })}
             onBlur={() => draft.note !== item.note && onChange(draft)} />
      <Button size="sm" variant="ghost" className="h-8 px-2" onClick={onDelete}>
        <Trash2 className="size-3 text-destructive" />
      </Button>
    </div>
  );
}
