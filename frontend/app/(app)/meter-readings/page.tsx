"use client";

import { useState, useCallback, useMemo, memo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { MeterReading, StromMeter, GasMeter, WasserMeter, HeizungMeter, Apartment } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { GroupCard } from "@/components/group-card";
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
import { Trash2, Pencil, Plus } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

type MeterType = "strom" | "gas" | "wasser" | "heizung";

const TYPE_META: Record<MeterType, { label: string; icon: string; badge: string }> = {
  strom:   { label: "Strom",   icon: "⚡", badge: "bg-amber-500/15 text-amber-400 border-amber-500/20" },
  gas:     { label: "Gas",     icon: "🔥", badge: "bg-blue-500/15 text-blue-400 border-blue-500/20" },
  wasser:  { label: "Wasser",  icon: "💧", badge: "bg-cyan-500/15 text-cyan-400 border-cyan-500/20" },
  heizung: { label: "Heizung", icon: "🌡️", badge: "bg-orange-500/15 text-orange-400 border-orange-500/20" },
};
const TYPES: MeterType[] = ["strom", "gas", "wasser", "heizung"];

function MeterChart({ readings }: { readings: MeterReading[] }) {
  if (readings.length < 2) return null;
  const sorted = [...readings].sort((a, b) => a.reading_date.localeCompare(b.reading_date));
  return (
    <ResponsiveContainer width="100%" height={110}>
      <LineChart data={sorted.map((r) => ({ date: r.reading_date, value: r.reading }))} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis dataKey="date" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} />
        <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} width={55} />
        <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6 }} />
        <Line type="monotone" dataKey="value" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// One meter's detail block. Hoisted to module scope and memoized so that
// unrelated page re-renders (e.g. typing in a dialog) don't remount every
// block and its Recharts chart. `readings` is the React Query array (stable
// reference between renders), and the handlers are stabilized with useCallback,
// so memo can skip re-rendering while the user types.
const MeterBlock = memo(function MeterBlock({
  type, m, readings, onAddReading, onEditMeter, onDeleteMeter, onDeleteReading,
}: {
  type: MeterType;
  m: any;
  readings: MeterReading[];
  onAddReading: (type: MeterType, meterId: number) => void;
  onEditMeter: (type: MeterType, m: any) => void;
  onDeleteMeter: (type: string, id: number) => void;
  onDeleteReading: (id: number) => void;
}) {
  const mrs = useMemo(
    () => readings.filter((r) => r.meter_type === type && r.meter_id === m.id)
      .sort((a, b) => a.reading_date.localeCompare(b.reading_date)),
    [readings, type, m.id],
  );
  let stats = null;
  if (mrs.length >= 2) {
    const first = mrs[0], last = mrs[mrs.length - 1];
    const total = (last.reading - first.reading);
    const days = Math.max(1, Math.round((new Date(last.reading_date).getTime() - new Date(first.reading_date).getTime()) / 86400000));
    stats = { total: total.toFixed(3), perDay: (total / days).toFixed(3), from: first.reading_date, to: last.reading_date };
  }
  return (
    <div className="px-4 py-3 border-t border-border first:border-t-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge className={TYPE_META[type].badge}>{TYPE_META[type].icon} {TYPE_META[type].label}</Badge>
            <span className="text-sm font-medium">{m.serial_number || "No serial"}</span>
            {type === "wasser" && <span className="text-xs text-muted-foreground">({m.type})</span>}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {m.description || "—"}
            {type === "gas" && `  ·  z=${m.z_zahl} · Bw=${m.brennwert}`}
            {type === "heizung" && `  ·  ${m.unit_price} €/kWh · factor ${m.conversion_factor}`}
          </p>
        </div>
        <div className="flex gap-1 shrink-0">
          <Button variant="outline" size="sm" onClick={() => onAddReading(type, m.id)}>
            <Plus className="size-3.5 mr-1" /> Reading
          </Button>
          <Button variant="ghost" size="icon" onClick={() => onEditMeter(type, m)}><Pencil className="size-4" /></Button>
          <ConfirmButton
            onConfirm={() => onDeleteMeter(type, m.id)}
            title="Delete meter?"
            message={`Delete this ${TYPE_META[type].label} meter and all its readings?`}
          >
            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"><Trash2 className="size-4" /></Button>
          </ConfirmButton>
        </div>
      </div>

      {mrs.length === 0 ? (
        <p className="text-xs text-muted-foreground mt-2">No readings yet.</p>
      ) : (
        <div className="mt-3 space-y-3">
          {stats && (
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-md bg-muted/40 p-2"><p className="text-[10px] text-muted-foreground uppercase tracking-wide">Total used</p><p className="text-sm font-semibold">{stats.total}</p></div>
              <div className="rounded-md bg-muted/40 p-2"><p className="text-[10px] text-muted-foreground uppercase tracking-wide">Avg / day</p><p className="text-sm font-semibold">{stats.perDay}</p></div>
              <div className="rounded-md bg-muted/40 p-2"><p className="text-[10px] text-muted-foreground uppercase tracking-wide">Period</p><p className="text-[11px] font-medium">{stats.from} → {stats.to}</p></div>
            </div>
          )}
          <MeterChart readings={mrs} />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Reading</TableHead>
                <TableHead className="text-right">Δ</TableHead>
                <TableHead>Note</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...mrs].reverse().map((r, i, arr) => {
                const prev = arr[i + 1];
                const delta = prev ? (r.reading - prev.reading).toFixed(3) : "—";
                return (
                  <TableRow key={r.id}>
                    <TableCell className="text-muted-foreground">{r.reading_date}</TableCell>
                    <TableCell className="text-right font-mono">{r.reading.toFixed(3)}</TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">{delta}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">{r.note || "—"}</TableCell>
                    <TableCell><ConfirmButton onConfirm={() => onDeleteReading(r.id)} title="Delete reading?" message={`Delete the reading of ${r.reading.toFixed(3)} from ${r.reading_date}?`}><Button variant="ghost" size="icon"><Trash2 className="size-3 text-destructive" /></Button></ConfirmButton></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
});

export default function MeterReadingsPage() {
  const qc = useQueryClient();
  const [readingOpen, setReadingOpen] = useState(false);
  const [meterOpen, setMeterOpen] = useState(false);
  const [meterType, setMeterType] = useState<MeterType>("strom");
  const [editingMeter, setEditingMeter] = useState<any>(null);
  const [readForm, setReadForm] = useState({ meter_type: "strom", meter_id: 0, reading_date: new Date().toISOString().split("T")[0], reading: 0, note: "" });
  const [filterProp, setFilterProp] = useState("all");

  const [stromForm, setStromForm] = useState({ apartment_id: 0, serial_number: "", description: "", scope: "shared" });
  const [gasForm, setGasForm] = useState({ apartment_id: 0, serial_number: "", description: "", z_zahl: 1.0, brennwert: 10.0, scope: "shared" });
  const [wasserForm, setWasserForm] = useState({ apartment_id: 0, serial_number: "", description: "", type: "kalt", scope: "shared" });
  const [heizungForm, setHeizungForm] = useState({ apartment_id: 0, serial_number: "", description: "", unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0, scope: "room" });

  const { data: apartments = [] } = useQuery<Apartment[]>({ queryKey: ["apartments"], queryFn: () => api.get("/api/apartments/").then((r) => r.data) });
  const { data: readings = [], isLoading } = useQuery<MeterReading[]>({ queryKey: ["meter-readings"], queryFn: () => api.get("/api/meters/readings").then((r) => r.data) });
  const { data: stromMeters = [] } = useQuery<StromMeter[]>({ queryKey: ["strom-meters"], queryFn: () => api.get("/api/meters/strom").then((r) => r.data) });
  const { data: gasMeters = [] } = useQuery<GasMeter[]>({ queryKey: ["gas-meters"], queryFn: () => api.get("/api/meters/gas").then((r) => r.data) });
  const { data: wasserMeters = [] } = useQuery<WasserMeter[]>({ queryKey: ["wasser-meters"], queryFn: () => api.get("/api/meters/wasser").then((r) => r.data) });
  const { data: heizungMeters = [] } = useQuery<HeizungMeter[]>({ queryKey: ["heizung-meters"], queryFn: () => api.get("/api/meters/heizung").then((r) => r.data) });

  const metersByType = (type: MeterType): any[] =>
    type === "strom" ? stromMeters : type === "gas" ? gasMeters : type === "wasser" ? wasserMeters : heizungMeters;

  const addReading = useMutation({
    mutationFn: () => api.post("/api/meters/readings", readForm),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["meter-readings"] }); setReadingOpen(false); toast.success("Reading added"); },
    onError: () => toast.error("Failed to add reading"),
  });
  const deleteReading = useMutation({
    mutationFn: (id: number) => api.delete(`/api/meters/readings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meter-readings"] }),
  });

  async function saveMeter() {
    try {
      const isEdit = !!editingMeter;
      const endpoint = `/api/meters/${meterType}`;
      const body = meterType === "strom" ? stromForm : meterType === "gas" ? gasForm : meterType === "wasser" ? wasserForm : heizungForm;
      isEdit ? await api.put(`${endpoint}/${editingMeter.id}`, body) : await api.post(endpoint, body);
      qc.invalidateQueries({ queryKey: [`${meterType}-meters`] });
      toast.success(isEdit ? "Updated" : "Meter created");
      setMeterOpen(false);
    } catch { toast.error("Failed"); }
  }

  const deleteMeter = useCallback(async (type: string, id: number) => {
    await api.delete(`/api/meters/${type}/${id}`);
    qc.invalidateQueries({ queryKey: [`${type}-meters`] });
    qc.invalidateQueries({ queryKey: ["meter-readings"] });
    toast.success("Deleted");
  }, [qc]);

  function openNewMeter(type: MeterType, apartmentId?: number) {
    setMeterType(type); setEditingMeter(null);
    const apt = apartmentId ?? 0;
    setStromForm({ apartment_id: apt, serial_number: "", description: "", scope: "shared" });
    setGasForm({ apartment_id: apt, serial_number: "", description: "", z_zahl: 1.0, brennwert: 10.0, scope: "shared" });
    setWasserForm({ apartment_id: apt, serial_number: "", description: "", type: "kalt", scope: "shared" });
    setHeizungForm({ apartment_id: apt, serial_number: "", description: "", unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0, scope: "room" });
    setMeterOpen(true);
  }

  const openEditMeter = useCallback((type: MeterType, m: any) => {
    setMeterType(type); setEditingMeter(m);
    if (type === "strom") setStromForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", scope: m.scope });
    else if (type === "gas") setGasForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", z_zahl: m.z_zahl, brennwert: m.brennwert, scope: m.scope });
    else if (type === "wasser") setWasserForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", type: m.type, scope: m.scope });
    else setHeizungForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", unit_price: m.unit_price, unit_label: m.unit_label, conversion_factor: m.conversion_factor, scope: m.scope });
    setMeterOpen(true);
  }, []);

  const openAddReading = useCallback((type: MeterType, meterId: number) => {
    setReadForm({ meter_type: type, meter_id: meterId, reading_date: new Date().toISOString().split("T")[0], reading: 0, note: "" });
    setReadingOpen(true);
  }, []);

  const properties = Array.from(new Set(apartments.map((a) => a.property_name || "—"))).sort();
  const visibleProps = filterProp === "all" ? properties : properties.filter((p) => p === filterProp);

  function metersForApartment(aptId: number): { type: MeterType; m: any }[] {
    const out: { type: MeterType; m: any }[] = [];
    for (const t of TYPES) for (const m of metersByType(t)) if (m.apartment_id === aptId) out.push({ type: t, m });
    return out;
  }
  function readingCountForApartment(aptId: number): number {
    const meterIds = new Set<string>();
    for (const t of TYPES) for (const m of metersByType(t)) if (m.apartment_id === aptId) meterIds.add(`${t}:${m.id}`);
    return readings.filter((r) => meterIds.has(`${r.meter_type}:${r.meter_id}`)).length;
  }

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title="Meter Readings" description="Meters and readings grouped per apartment">
        <Select value={filterProp} onValueChange={setFilterProp}>
          <SelectTrigger className="w-48 h-8 text-sm"><SelectValue placeholder="All properties" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All properties</SelectItem>
            {properties.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
      </PageHeader>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : apartments.length === 0 ? (
        <p className="text-sm text-muted-foreground">No apartments yet — add one first.</p>
      ) : (
        visibleProps.map((propName) => {
          const apts = apartments.filter((a) => (a.property_name || "—") === propName);
          return (
            <div key={propName} className="space-y-2">
              <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground px-1 pt-2">{propName}</h2>
              {apts.map((apt) => {
                const meters = metersForApartment(apt.id);
                const readingCount = readingCountForApartment(apt.id);
                return (
                  <GroupCard
                    key={apt.id}
                    title={apt.name}
                    subtitle={apt.flat ? `Unit ${apt.flat}` : undefined}
                    defaultOpen={meters.length > 0}
                    summary={
                      <>
                        <Badge variant="secondary">{meters.length} meter{meters.length !== 1 ? "s" : ""}</Badge>
                        {readingCount > 0 && <Badge variant="secondary">{readingCount} reading{readingCount !== 1 ? "s" : ""}</Badge>}
                      </>
                    }
                  >
                    {meters.length === 0 ? (
                      <p className="px-4 py-3 text-sm text-muted-foreground">No meters registered for this apartment.</p>
                    ) : (
                      meters.map(({ type, m }) => (
                        <MeterBlock
                          key={`${type}-${m.id}`}
                          type={type}
                          m={m}
                          readings={readings}
                          onAddReading={openAddReading}
                          onEditMeter={openEditMeter}
                          onDeleteMeter={deleteMeter}
                          onDeleteReading={deleteReading.mutate}
                        />
                      ))
                    )}
                    {/* Add-meter toolbar */}
                    <div className="px-4 py-2 border-t border-border flex flex-wrap gap-1.5">
                      <span className="text-xs text-muted-foreground self-center mr-1">Add meter:</span>
                      {TYPES.map((t) => (
                        <Button key={t} variant="ghost" size="sm" onClick={() => openNewMeter(t, apt.id)}>
                          {TYPE_META[t].icon} {TYPE_META[t].label}
                        </Button>
                      ))}
                    </div>
                  </GroupCard>
                );
              })}
            </div>
          );
        })
      )}

      {/* Add reading dialog */}
      <Dialog open={readingOpen} onOpenChange={setReadingOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Meter Reading</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Type</Label>
                <Select value={readForm.meter_type} onValueChange={(v) => setReadForm((f) => ({ ...f, meter_type: v, meter_id: 0 }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{TYPE_META[t].icon} {TYPE_META[t].label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Meter</Label>
                <Select value={String(readForm.meter_id || "")} onValueChange={(v) => setReadForm((f) => ({ ...f, meter_id: Number(v) }))}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    {metersByType(readForm.meter_type as MeterType).map((m: any) => (
                      <SelectItem key={m.id} value={String(m.id)}>{m.apartment_name} — {m.serial_number || "no serial"}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><Label>Date</Label><Input type="date" value={readForm.reading_date} onChange={(e) => setReadForm((f) => ({ ...f, reading_date: e.target.value }))} /></div>
              <div className="space-y-1.5"><Label>Reading</Label><Input type="number" step="0.001" value={readForm.reading} onChange={(e) => setReadForm((f) => ({ ...f, reading: Number(e.target.value) }))} /></div>
            </div>
            <div className="space-y-1.5"><Label>Note</Label><Input value={readForm.note} onChange={(e) => setReadForm((f) => ({ ...f, note: e.target.value }))} placeholder="Optional" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReadingOpen(false)}>Cancel</Button>
            <Button onClick={() => addReading.mutate()} disabled={!readForm.meter_id || addReading.isPending}>Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add/edit meter dialog */}
      <Dialog open={meterOpen} onOpenChange={setMeterOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editingMeter ? "Edit" : "New"} {TYPE_META[meterType].label} meter</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Apartment</Label>
              <Select value={String((meterType === "strom" ? stromForm : meterType === "gas" ? gasForm : meterType === "wasser" ? wasserForm : heizungForm).apartment_id || "")}
                onValueChange={(v) => {
                  const n = Number(v);
                  if (meterType === "strom") setStromForm((f) => ({ ...f, apartment_id: n }));
                  else if (meterType === "gas") setGasForm((f) => ({ ...f, apartment_id: n }));
                  else if (meterType === "wasser") setWasserForm((f) => ({ ...f, apartment_id: n }));
                  else setHeizungForm((f) => ({ ...f, apartment_id: n }));
                }}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>{apartments.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.property_name} — {a.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><Label>Serial Number</Label>
                <Input value={(meterType === "strom" ? stromForm : meterType === "gas" ? gasForm : meterType === "wasser" ? wasserForm : heizungForm).serial_number}
                  onChange={(e) => { const v = e.target.value; meterType === "strom" ? setStromForm((f) => ({ ...f, serial_number: v })) : meterType === "gas" ? setGasForm((f) => ({ ...f, serial_number: v })) : meterType === "wasser" ? setWasserForm((f) => ({ ...f, serial_number: v })) : setHeizungForm((f) => ({ ...f, serial_number: v })); }} />
              </div>
              <div className="space-y-1.5"><Label>Description</Label>
                <Input value={(meterType === "strom" ? stromForm : meterType === "gas" ? gasForm : meterType === "wasser" ? wasserForm : heizungForm).description}
                  onChange={(e) => { const v = e.target.value; meterType === "strom" ? setStromForm((f) => ({ ...f, description: v })) : meterType === "gas" ? setGasForm((f) => ({ ...f, description: v })) : meterType === "wasser" ? setWasserForm((f) => ({ ...f, description: v })) : setHeizungForm((f) => ({ ...f, description: v })); }} />
              </div>
            </div>
            {meterType === "gas" && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5"><Label>Z-Zahl</Label><Input type="number" step="0.0001" value={gasForm.z_zahl} onChange={(e) => setGasForm((f) => ({ ...f, z_zahl: Number(e.target.value) }))} /></div>
                <div className="space-y-1.5"><Label>Brennwert</Label><Input type="number" step="0.0001" value={gasForm.brennwert} onChange={(e) => setGasForm((f) => ({ ...f, brennwert: Number(e.target.value) }))} /></div>
              </div>
            )}
            {meterType === "heizung" && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5"><Label>€/kWh</Label><Input type="number" step="0.0001" value={heizungForm.unit_price} onChange={(e) => setHeizungForm((f) => ({ ...f, unit_price: Number(e.target.value) }))} /></div>
                <div className="space-y-1.5"><Label>Conversion factor</Label><Input type="number" step="0.0001" value={heizungForm.conversion_factor} onChange={(e) => setHeizungForm((f) => ({ ...f, conversion_factor: Number(e.target.value) }))} /></div>
                <div className="space-y-1.5"><Label>Unit label</Label><Input value={heizungForm.unit_label} onChange={(e) => setHeizungForm((f) => ({ ...f, unit_label: e.target.value }))} /></div>
              </div>
            )}
            {meterType === "wasser" && (
              <div className="space-y-1.5"><Label>Type</Label>
                <Select value={wasserForm.type} onValueChange={(v) => setWasserForm((f) => ({ ...f, type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="kalt">Kaltwasser</SelectItem><SelectItem value="warm">Warmwasser</SelectItem></SelectContent>
                </Select>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMeterOpen(false)}>Cancel</Button>
            <Button onClick={saveMeter}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
