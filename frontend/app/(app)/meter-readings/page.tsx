"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { MeterReading, StromMeter, GasMeter, WasserMeter, HeizungMeter, Apartment } from "@/lib/types";
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
import { Trash2, Pencil } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

type ActiveTab = "readings" | "strom" | "gas" | "wasser" | "heizung";

const TYPE_BADGE: Record<string, string> = {
  strom: "bg-amber-500/15 text-amber-400 border-amber-500/20",
  gas: "bg-blue-500/15 text-blue-400 border-blue-500/20",
  wasser: "bg-cyan-500/15 text-cyan-400 border-cyan-500/20",
  heizung: "bg-orange-500/15 text-orange-400 border-orange-500/20",
};

function MeterReadingChart({ readings }: { readings: MeterReading[] }) {
  if (readings.length < 2) return null;
  const sorted = [...readings].sort((a, b) => a.reading_date.localeCompare(b.reading_date));
  return (
    <ResponsiveContainer width="100%" height={120}>
      <LineChart data={sorted.map((r) => ({ date: r.reading_date, value: r.reading }))}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis dataKey="date" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} />
        <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} width={60} />
        <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6 }} />
        <Line type="monotone" dataKey="value" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function MeterReadingsPage() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<ActiveTab>("readings");
  const [readingOpen, setReadingOpen] = useState(false);
  const [meterOpen, setMeterOpen] = useState(false);
  const [meterType, setMeterType] = useState<"strom" | "gas" | "wasser" | "heizung">("strom");
  const [editingMeter, setEditingMeter] = useState<any>(null);
  const [readForm, setReadForm] = useState({ meter_type: "strom", meter_id: 0, reading_date: new Date().toISOString().split("T")[0], reading: 0, note: "" });

  // Meter forms
  const [stromForm, setStromForm] = useState({ apartment_id: 0, serial_number: "", description: "", scope: "shared" });
  const [gasForm, setGasForm] = useState({ apartment_id: 0, serial_number: "", description: "", z_zahl: 1.0, brennwert: 10.0, scope: "shared" });
  const [wasserForm, setWasserForm] = useState({ apartment_id: 0, serial_number: "", description: "", type: "kalt", scope: "shared" });
  const [heizungForm, setHeizungForm] = useState({ apartment_id: 0, serial_number: "", description: "", unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0, scope: "room" });

  const [filterApt, setFilterApt] = useState<string>("all");

  const { data: apartments = [] } = useQuery<Apartment[]>({ queryKey: ["apartments"], queryFn: () => api.get("/api/apartments/").then((r) => r.data) });
  const { data: readings = [], isLoading } = useQuery<MeterReading[]>({ queryKey: ["meter-readings"], queryFn: () => api.get("/api/meters/readings").then((r) => r.data) });
  const { data: stromMeters = [] } = useQuery<StromMeter[]>({ queryKey: ["strom-meters"], queryFn: () => api.get("/api/meters/strom").then((r) => r.data) });
  const { data: gasMeters = [] } = useQuery<GasMeter[]>({ queryKey: ["gas-meters"], queryFn: () => api.get("/api/meters/gas").then((r) => r.data) });
  const { data: wasserMeters = [] } = useQuery<WasserMeter[]>({ queryKey: ["wasser-meters"], queryFn: () => api.get("/api/meters/wasser").then((r) => r.data) });
  const { data: heizungMeters = [] } = useQuery<HeizungMeter[]>({ queryKey: ["heizung-meters"], queryFn: () => api.get("/api/meters/heizung").then((r) => r.data) });

  function filterMeters<T extends { apartment_id: number }>(meters: T[]): T[] {
    if (filterApt === "all") return meters;
    return meters.filter((m) => String(m.apartment_id) === filterApt);
  }

  function meterLabel(type: string, id: number) {
    const all = type === "strom" ? stromMeters : type === "gas" ? gasMeters : type === "wasser" ? wasserMeters : heizungMeters;
    const m = (all as any[]).find((x) => x.id === id);
    return m ? `${m.apartment_name} — ${m.serial_number || "no serial"}` : `ID ${id}`;
  }

  // Per-meter grouped readings for charts
  function readingsFor(type: string, id: number) {
    return readings.filter((r) => r.meter_type === type && r.meter_id === id)
      .sort((a, b) => a.reading_date.localeCompare(b.reading_date));
  }

  function avg_per_day(rs: MeterReading[]) {
    if (rs.length < 2) return null;
    const first = rs[0], last = rs[rs.length - 1];
    const days = Math.max(1, Math.round((new Date(last.reading_date).getTime() - new Date(first.reading_date).getTime()) / 86400000));
    return ((last.reading - first.reading) / days).toFixed(3);
  }

  const addReading = useMutation({
    mutationFn: () => api.post("/api/meters/readings", readForm),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["meter-readings"] }); setReadingOpen(false); toast.success("Reading added"); },
  });

  const deleteReading = useMutation({
    mutationFn: (id: number) => api.delete(`/api/meters/readings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meter-readings"] }),
  });

  async function saveMeter() {
    try {
      const isEdit = !!editingMeter;
      if (meterType === "strom") {
        isEdit ? await api.put(`/api/meters/strom/${editingMeter.id}`, stromForm) : await api.post("/api/meters/strom", stromForm);
        qc.invalidateQueries({ queryKey: ["strom-meters"] });
      } else if (meterType === "gas") {
        isEdit ? await api.put(`/api/meters/gas/${editingMeter.id}`, gasForm) : await api.post("/api/meters/gas", gasForm);
        qc.invalidateQueries({ queryKey: ["gas-meters"] });
      } else if (meterType === "wasser") {
        isEdit ? await api.put(`/api/meters/wasser/${editingMeter.id}`, wasserForm) : await api.post("/api/meters/wasser", wasserForm);
        qc.invalidateQueries({ queryKey: ["wasser-meters"] });
      } else {
        isEdit ? await api.put(`/api/meters/heizung/${editingMeter.id}`, heizungForm) : await api.post("/api/meters/heizung", heizungForm);
        qc.invalidateQueries({ queryKey: ["heizung-meters"] });
      }
      toast.success(isEdit ? "Updated" : "Meter created");
      setMeterOpen(false);
    } catch { toast.error("Failed"); }
  }

  async function deleteMeter(type: string, id: number) {
    await api.delete(`/api/meters/${type}/${id}`);
    qc.invalidateQueries({ queryKey: [`${type}-meters`] });
    qc.invalidateQueries({ queryKey: ["meter-readings"] });
    toast.success("Deleted");
  }

  function openNewMeter(type: "strom" | "gas" | "wasser" | "heizung") {
    setMeterType(type); setEditingMeter(null);
    setStromForm({ apartment_id: 0, serial_number: "", description: "", scope: "shared" });
    setGasForm({ apartment_id: 0, serial_number: "", description: "", z_zahl: 1.0, brennwert: 10.0, scope: "shared" });
    setWasserForm({ apartment_id: 0, serial_number: "", description: "", type: "kalt", scope: "shared" });
    setHeizungForm({ apartment_id: 0, serial_number: "", description: "", unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0, scope: "room" });
    setMeterOpen(true);
  }

  function openEditMeter(type: "strom" | "gas" | "wasser" | "heizung", m: any) {
    setMeterType(type); setEditingMeter(m);
    if (type === "strom") setStromForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", scope: m.scope });
    else if (type === "gas") setGasForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", z_zahl: m.z_zahl, brennwert: m.brennwert, scope: m.scope });
    else if (type === "wasser") setWasserForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", type: m.type, scope: m.scope });
    else setHeizungForm({ apartment_id: m.apartment_id, serial_number: m.serial_number || "", description: m.description || "", unit_price: m.unit_price, unit_label: m.unit_label, conversion_factor: m.conversion_factor, scope: m.scope });
    setMeterOpen(true);
  }

  const TABS: { id: ActiveTab; label: string }[] = [
    { id: "readings", label: "Readings" },
    { id: "strom", label: "⚡ Strom" },
    { id: "gas", label: "🔥 Gas" },
    { id: "wasser", label: "💧 Wasser" },
    { id: "heizung", label: "🌡️ Heizung" },
  ];

  function MeterTable({ type, meters }: { type: "strom" | "gas" | "wasser" | "heizung"; meters: any[] }) {
    return (
      <div className="space-y-4">
        <Button size="sm" onClick={() => openNewMeter(type)}>Add {type} meter</Button>
        {meters.map((m) => {
          const mrs = readingsFor(type, m.id);
          return (
            <Card key={m.id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{m.apartment_name}</p>
                    <p className="text-xs text-muted-foreground">{m.serial_number || "No serial"} · {m.description || "—"}</p>
                    {type === "gas" && <p className="text-xs text-muted-foreground">z_zahl: {m.z_zahl} · brennwert: {m.brennwert}</p>}
                    {type === "heizung" && <p className="text-xs text-muted-foreground">€/kWh: {m.unit_price} · factor: {m.conversion_factor}</p>}
                  </div>
                  <div className="flex gap-1">
                    {mrs.length >= 2 && <p className="text-xs text-muted-foreground mr-2 self-center">Avg: {avg_per_day(mrs)} /day</p>}
                    <Button variant="ghost" size="icon" onClick={() => openEditMeter(type, m)}><Pencil className="size-4" /></Button>
                    <Button variant="ghost" size="icon" onClick={() => deleteMeter(type, m.id)} className="text-destructive hover:text-destructive"><Trash2 className="size-4" /></Button>
                  </div>
                </div>
              </CardHeader>
              {mrs.length > 0 && (
                <CardContent className="space-y-3">
                  {mrs.length >= 2 && (() => {
                    const sorted = [...mrs].sort((a, b) => a.reading_date.localeCompare(b.reading_date));
                    const first = sorted[0], last = sorted[sorted.length - 1];
                    const total = (last.reading - first.reading).toFixed(3);
                    const days = Math.max(1, Math.round((new Date(last.reading_date).getTime() - new Date(first.reading_date).getTime()) / 86400000));
                    const apd = (parseFloat(total) / days).toFixed(3);
                    return (
                      <div className="grid grid-cols-3 gap-3">
                        <div className="rounded-md bg-muted/40 p-3"><p className="text-xs text-muted-foreground">Total consumption</p><p className="font-semibold">{total}</p></div>
                        <div className="rounded-md bg-muted/40 p-3"><p className="text-xs text-muted-foreground">Avg / day</p><p className="font-semibold">{apd}</p></div>
                        <div className="rounded-md bg-muted/40 p-3"><p className="text-xs text-muted-foreground">Period</p><p className="font-semibold text-xs">{first.reading_date} → {last.reading_date}</p></div>
                      </div>
                    );
                  })()}
                  <MeterReadingChart readings={mrs} />
                  <Table>
                    <TableHeader><TableRow><TableHead>Date</TableHead><TableHead className="text-right">Reading</TableHead><TableHead className="text-right">Δ</TableHead><TableHead>Note</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
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
                            <TableCell><Button variant="ghost" size="icon" onClick={() => deleteReading.mutate(r.id)}><Trash2 className="size-3 text-destructive" /></Button></TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </CardContent>
              )}
            </Card>
          );
        })}
        {meters.length === 0 && <p className="text-sm text-muted-foreground">No {type} meters registered.</p>}
      </div>
    );
  }

  // Filter readings table by apartment
  const filteredReadings = filterApt === "all" ? readings : readings.filter((r) => {
    const meterList: any[] = r.meter_type === "strom" ? stromMeters
      : r.meter_type === "gas" ? gasMeters
      : r.meter_type === "wasser" ? wasserMeters
      : heizungMeters;
    return meterList.some((m) => m.id === r.meter_id && m.apartment_id === Number(filterApt));
  });

  return (
    <div className="max-w-5xl">
      <PageHeader title="Meter Readings">
        <Select value={filterApt} onValueChange={setFilterApt}>
          <SelectTrigger className="w-52 h-8 text-sm"><SelectValue placeholder="All apartments" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All apartments</SelectItem>
            {apartments.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.property_name} — {a.name}</SelectItem>)}
          </SelectContent>
        </Select>
        {activeTab === "readings" && (
          <Button size="sm" onClick={() => setReadingOpen(true)}>Add Reading</Button>
        )}
      </PageHeader>

      {/* Tab bar */}
      <div className="flex gap-1 mb-4 border-b border-border">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${activeTab === t.id ? "border-primary text-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "readings" && (
        <Card>
          <Table>
            <TableHeader>
              <TableRow><TableHead>Date</TableHead><TableHead>Type</TableHead><TableHead>Meter</TableHead><TableHead className="text-right">Reading</TableHead><TableHead>Note</TableHead><TableHead className="w-10" /></TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-10">Loading…</TableCell></TableRow>
              ) : filteredReadings.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-10">No readings yet.</TableCell></TableRow>
              ) : (
                filteredReadings.slice(0, 200).map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="text-muted-foreground">{r.reading_date}</TableCell>
                    <TableCell><Badge className={TYPE_BADGE[r.meter_type] || ""}>{r.meter_type}</Badge></TableCell>
                    <TableCell className="text-muted-foreground text-sm">{meterLabel(r.meter_type, r.meter_id)}</TableCell>
                    <TableCell className="text-right font-mono">{r.reading.toFixed(3)}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{r.note || "—"}</TableCell>
                    <TableCell><Button variant="ghost" size="icon" onClick={() => deleteReading.mutate(r.id)}><Trash2 className="size-4 text-destructive" /></Button></TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Card>
      )}
      {activeTab === "strom" && <MeterTable type="strom" meters={filterMeters(stromMeters)} />}
      {activeTab === "gas" && <MeterTable type="gas" meters={filterMeters(gasMeters)} />}
      {activeTab === "wasser" && <MeterTable type="wasser" meters={filterMeters(wasserMeters)} />}
      {activeTab === "heizung" && <MeterTable type="heizung" meters={filterMeters(heizungMeters)} />}

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
                  <SelectContent>{["strom","gas","wasser","heizung"].map((t) => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Meter</Label>
                <Select value={String(readForm.meter_id || "")} onValueChange={(v) => setReadForm((f) => ({ ...f, meter_id: Number(v) }))}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    {(readForm.meter_type === "strom" ? stromMeters : readForm.meter_type === "gas" ? gasMeters : readForm.meter_type === "wasser" ? wasserMeters : heizungMeters).map((m: any) => (
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
          <DialogHeader><DialogTitle>{editingMeter ? "Edit" : "New"} {meterType} meter</DialogTitle></DialogHeader>
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
