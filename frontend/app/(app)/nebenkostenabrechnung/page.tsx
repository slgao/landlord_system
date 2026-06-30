"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Contract, GasMeter, BillingProfile } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, Calculator, FileDown, Save, Upload } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── helpers ──────────────────────────────────────────────────────────────────

function effectiveDays(billStart: string, billEnd: string, contractStart: string, contractEnd: string | undefined) {
  if (!billStart || !billEnd) return 0;
  const bs = new Date(billStart), be = new Date(billEnd);
  const cs = new Date(contractStart);
  const ce = contractEnd ? new Date(contractEnd) : be;
  const effStart = bs > cs ? bs : cs;
  const effEnd = be < ce ? be : ce;
  if (effEnd < effStart) return 0;
  return Math.round((effEnd.getTime() - effStart.getTime()) / 86400000) + 1;
}

function billDays(start: string, end: string) {
  if (!start || !end) return 365;
  return Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 1;
}

function thisYear() { return new Date().getFullYear(); }
function isoDate(year: number, month: number, day: number) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}
function fmtPeriod(s: string, e: string) {
  return `${s.split("-").reverse().join(".")} – ${e.split("-").reverse().join(".")}`;
}
function monthsBetween(s: string, e: string) {
  if (!s || !e) return 1;
  return Math.max(1, (new Date(e).getFullYear() - new Date(s).getFullYear()) * 12
    + (new Date(e).getMonth() - new Date(s).getMonth()) + 1);
}
// Intersection of a billing period with the tenant's contract period (the
// tenant's actual living period within that bill). Falls back to the full
// billing period when no contract dates are given.
function clampPeriod(billStart: string, billEnd: string, cStart?: string, cEnd?: string) {
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  let s = new Date(billStart), e = new Date(billEnd);
  const cs = cStart ? new Date(cStart) : null;
  const ce = cEnd ? new Date(cEnd) : null;
  if (cs && cs > s) s = cs;
  if (ce && ce < e) e = ce;
  if (e < s) return { start: billStart, end: billEnd };
  return { start: iso(s), end: iso(e) };
}

// ── billing-entry factories ────────────────────────────────────────────────────
// Each utility holds a LIST of billing periods (e.g. one provider bill per year).
// Every billing is either meter-based or a direct total-cost figure (mode "sum").

type Mode = "meter" | "sum";

function baseBilling() {
  const Y = thisYear();
  return {
    mode: "meter" as Mode,
    bill_start: isoDate(Y, 1, 1), bill_end: isoDate(Y, 12, 31),
    prepay_monthly: 0, is_pauschale: false, cost_flat: 0,
  };
}
const defStrom = () => ({ ...baseBilling(), start_kwh: 0, end_kwh: 0, arbeitspreis: 0, grundpreis_monthly: 0 });
const defGas = () => ({ ...baseBilling(), start_m3: 0, end_m3: 0, umrechnungsfaktor: 10.0, arbeitspreis: 0, grundpreis_monthly: 0 });
const defWater = () => ({ ...baseBilling(), start_m3: 0, end_m3: 0, frischwasser_per_m3: 0, abwasser_per_m3: 0 });
const defWarm = () => ({ ...baseBilling(), meters: [{ start: 0, end: 0 }], frischwasser_per_m3: 0, abwasser_per_m3: 0, heizenergie_per_m3: 0 });
const defHeiz = () => ({ ...baseBilling(), meters: [{ start: 0, end: 0, unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0 }] });
const defBk = (tenants = 1) => ({
  cost_flat: 0, tenants,
  bk_start: isoDate(thisYear(), 1, 1), bk_end: isoDate(thisYear(), 12, 31),
  // Ihr Zeitraum (tenant's living period) — auto-filled from the contract, editable.
  eff_start: "", eff_end: "",
  limit_per_month: 206,
});

// Normalise a stored profile value (array OR legacy single object, with possible
// Streamlit field aliases) into an array of billing entries matching the default.
function billingsFrom(stored: any, def: () => any, hasMeters: boolean, heiz: boolean) {
  const arr = Array.isArray(stored) ? stored : (stored ? [stored] : []);
  return arr.map((s: any) => {
    const base = def();
    const out: any = { ...base };
    for (const k of Object.keys(base)) {
      if (k === "meters") continue;
      const v = s[k] ?? (k === "prepay_monthly" ? s.prepay_pm : undefined);
      if (v !== undefined && v !== null) out[k] = typeof base[k] === "number" ? Number(v) : v;
    }
    out.mode = s.mode === "sum" ? "sum" : "meter";
    if (hasMeters) {
      const ms = Array.isArray(s.meters) ? s.meters : null;
      if (ms && ms.length) {
        out.meters = ms.map((m: any) => heiz
          ? { start: Number(m.start) || 0, end: Number(m.end) || 0, unit_price: Number(m.unit_price ?? s.price_kwh) || 0, unit_label: m.unit_label || "Einheiten", conversion_factor: Number(m.conversion_factor) || 1.0 }
          : { start: Number(m.start) || 0, end: Number(m.end) || 0 });
      }
    }
    return out;
  });
}

// ── module-level sub-components (NOT redefined per render) ──────────────────────

function FieldRow({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{children}</div>;
}

function Num({ label, value, onChange, step = "0.01", min = "0" }: {
  label: string; value: number; onChange: (v: number) => void; step?: string; min?: string;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input type="number" step={step} min={min} className="h-8 text-sm"
        value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function DateF({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input type="date" className="h-8 text-sm" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function CalcPreview({ label, result }: { label: string; result: any }) {
  if (!result) return null;
  return (
    <div className="rounded-md bg-primary/10 border border-primary/20 p-3 text-sm space-y-1">
      <p className="font-medium text-primary text-xs uppercase tracking-wide">{label} — Calculation Preview</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        {result.cost_flat != null && <span>Gesamt: <b>€ {result.cost_flat?.toFixed(2)}</b></span>}
        {result.verbrauch_m3 != null && <span>Verbrauch: <b>{result.verbrauch_m3} m³</b></span>}
        {result.verbrauch != null && <span>Verbrauch: <b>{result.verbrauch} kWh</b></span>}
        {result.verbrauch_kwh != null && <span>kWh: <b>{result.verbrauch_kwh}</b></span>}
        {result.cost_tenant != null && <span>Ihr Anteil: <b>€ {result.cost_tenant?.toFixed(2)}</b></span>}
        {result.prepay != null && <span>Vorauszahlung: <b>€ {result.prepay?.toFixed(2)}</b></span>}
        {result.nach != null && (
          <span className={result.nach > 0 ? "text-destructive font-bold" : "text-emerald-400 font-bold"}>
            Nachzahlung: € {result.nach?.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  );
}

function SectionCard({ id, title, enabled, onToggle, children }: {
  id: string; title: string; enabled: boolean; onToggle: (v: boolean) => void; children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)}
            className="size-4 accent-primary" id={`toggle-${id}`} />
          <label htmlFor={`toggle-${id}`} className="text-sm font-medium cursor-pointer">{title}</label>
        </div>
      </CardHeader>
      {enabled && <CardContent className="space-y-4">{children}</CardContent>}
    </Card>
  );
}

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div className="flex gap-5 text-sm">
      <label className="flex items-center gap-1.5 cursor-pointer">
        <input type="radio" checked={mode !== "sum"} onChange={() => onChange("meter")} className="accent-primary" />
        Meter readings
      </label>
      <label className="flex items-center gap-1.5 cursor-pointer">
        <input type="radio" checked={mode === "sum"} onChange={() => onChange("sum")} className="accent-primary" />
        Total cost only
      </label>
    </div>
  );
}

// Shared wrapper for one billing period: dates, mode toggle, total-cost field
// (sum mode) OR the utility-specific meter inputs (children), prepay + Pauschale.
function BillingShell({ idx, count, b, set, onRemove, costLabel, preview, children }: {
  idx: number; count: number; b: any; set: (patch: any) => void; onRemove: () => void;
  costLabel: string; preview: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border/70 bg-muted/20 p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground">Billing {idx + 1}</span>
        {count > 1 && (
          <Button variant="ghost" size="icon" className="size-7" onClick={onRemove}>
            <Trash2 className="size-4 text-destructive" />
          </Button>
        )}
      </div>
      <FieldRow>
        <DateF label="Bill start" value={b.bill_start} onChange={(v) => set({ bill_start: v })} />
        <DateF label="Bill end" value={b.bill_end} onChange={(v) => set({ bill_end: v })} />
      </FieldRow>
      <ModeToggle mode={b.mode} onChange={(m) => set({ mode: m })} />
      {b.mode === "sum"
        ? <div className="md:w-1/2"><Num label={costLabel} value={b.cost_flat} onChange={(v) => set({ cost_flat: v })} /></div>
        : children}
      <div className="flex items-center gap-4">
        <Num label="Prepay (€/month)" value={b.prepay_monthly} onChange={(v) => set({ prepay_monthly: v })} />
        <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
          <input type="checkbox" checked={b.is_pauschale} onChange={(e) => set({ is_pauschale: e.target.checked })} className="accent-primary" />
          Pauschale
        </label>
      </div>
      <p className="text-xs text-muted-foreground">
        Shared flat: enter the <b>total</b> monthly prepayment for <b>all persons</b> — it&apos;s divided across the number of persons automatically.
      </p>
      {preview}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function NebenkostenabrechnungPage() {
  const [contractId, setContractId] = useState("");
  const [numTenants, setNumTenants] = useState(1);
  const [calcResult, setCalcResult] = useState<any>({});
  const [calculating, setCalculating] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [profileLabel, setProfileLabel] = useState("");
  // id of the profile currently loaded (enables "Update" instead of only "Save new")
  const [currentProfileId, setCurrentProfileId] = useState<number | null>(null);
  const [currentProfileLabel, setCurrentProfileLabel] = useState("");
  // offset the Nachzahlung against the still-held deposit
  const [deductKaution, setDeductKaution] = useState(false);

  // section toggles
  const [useStrom, setUseStrom] = useState(false);
  const [useGas, setUseGas] = useState(false);
  const [useWater, setUseWater] = useState(false);
  const [useWarmwater, setUseWarmwater] = useState(false);
  const [useHeizung, setUseHeizung] = useState(false);
  const [useBK, setUseBK] = useState(false);
  const [useExtra, setUseExtra] = useState(false);

  // each utility is a list of billing periods
  const [stromB, setStromB] = useState<any[]>([defStrom()]);
  const [gasB, setGasB] = useState<any[]>([defGas()]);
  const [waterB, setWaterB] = useState<any[]>([defWater()]);
  const [warmB, setWarmB] = useState<any[]>([defWarm()]);
  const [heizB, setHeizB] = useState<any[]>([defHeiz()]);

  const [bkB, setBkB] = useState<any[]>([defBk()]);
  const [extras, setExtras] = useState<{ description: string; amount: number }[]>([]);

  const justLoadedProfile = useRef(false);
  const qc = useQueryClient();

  function updateAt(setter: React.Dispatch<React.SetStateAction<any[]>>, idx: number, patch: any) {
    setter((arr) => arr.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  // ── all contracts (active + expired) ──
  const { data: contracts = [] } = useQuery<Contract[]>({
    queryKey: ["contracts-all-nbk"],
    queryFn: () => api.get("/api/contracts/").then((r) => r.data),
  });

  const { data: gasMeters = [] } = useQuery<GasMeter[]>({
    queryKey: ["gas-meters-all"],
    queryFn: () => api.get("/api/meters/gas").then((r) => r.data),
  });

  const selected = contracts.find((c) => String(c.id) === contractId);

  const { data: profiles = [] } = useQuery<BillingProfile[]>({
    queryKey: ["billing-profiles", selected?.tenant_id],
    queryFn: () => api.get(`/api/billing-profiles/?tenant_id=${selected?.tenant_id}`).then((r) => r.data),
    enabled: !!selected?.tenant_id,
  });

  const { data: coTenants = [] } = useQuery<any[]>({
    queryKey: ["nk-co-tenants", selected?.id],
    queryFn: () => api.get(`/api/co-tenants/?contract_id=${selected!.id}`).then((r) => r.data),
    enabled: !!selected?.id,
  });

  // Auto person count from the backend: co-tenants on the contract, or — for a
  // WG where each room is a separate contract — the number of active tenants
  // sharing the same flat. Mirrors the Streamlit logic.
  const { data: occupancy } = useQuery<{ auto_count: number; co_tenant_count: number }>({
    queryKey: ["nk-occupancy", selected?.id],
    queryFn: () => api.get(`/api/contracts/${selected!.id}/occupancy`).then((r) => r.data),
    enabled: !!selected?.id,
  });

  // Auto-set tenant count from backend occupancy, once per contract selection.
  // Skipped right after loading a profile so the profile's value wins.
  useEffect(() => {
    if (!selected?.id || !occupancy) return;
    if (justLoadedProfile.current) { justLoadedProfile.current = false; return; }
    setNumTenants(occupancy.auto_count);
  }, [selected?.id, occupancy?.auto_count]);

  // Changing the contract clears the "currently loaded profile" so Update can't
  // accidentally overwrite a different tenant's profile.
  useEffect(() => {
    setCurrentProfileId(null);
    setCurrentProfileLabel("");
    setDeductKaution(false);
  }, [selected?.id]);

  // Auto-fill each BK billing's "Ihr Zeitraum" (living period) from the contract
  // ∩ billing period, only where the user hasn't set it yet. Editable afterwards.
  useEffect(() => {
    if (!selected) return;
    setBkB((arr) => {
      let changed = false;
      const next = arr.map((b) => {
        if (b.eff_start && b.eff_end) return b;
        const eff = clampPeriod(b.bk_start, b.bk_end, selected.start_date, selected.end_date);
        changed = true;
        return { ...b, eff_start: b.eff_start || eff.start, eff_end: b.eff_end || eff.end };
      });
      return changed ? next : arr;
    });
  }, [selected?.id]);

  // Auto-fill gas Umrechnungsfaktor from a registered gas meter (still-default
  // entries only), in an effect, never during render.
  useEffect(() => {
    if (!selected?.apartment_id) return;
    const apt = gasMeters.filter((m) => m.apartment_id === selected.apartment_id);
    if (apt.length > 0) {
      const gm = apt[0];
      const factor = parseFloat((gm.z_zahl * gm.brennwert).toFixed(4));
      setGasB((arr) => arr.map((b) => (b.umrechnungsfaktor === 10.0 ? { ...b, umrechnungsfaktor: factor } : b)));
    }
  }, [selected?.apartment_id, gasMeters]);

  const aptGasMeters = gasMeters.filter((m) => m.apartment_id === selected?.apartment_id);

  // ── payload builders ──
  function buildCalcPayload() {
    const cs = selected?.start_date || "";
    const ce = selected?.end_date;
    const mk = (b: any) => ({
      ...b, num_tenants: numTenants,
      bill_days: billDays(b.bill_start, b.bill_end),
      eff_days: effectiveDays(b.bill_start, b.bill_end, cs, ce),
    });
    const p: any = {};
    if (useStrom) p.strom = stromB.map(mk);
    if (useGas) p.gas = gasB.map(mk);
    if (useWater) p.water = waterB.map(mk);
    if (useWarmwater) p.warmwater = warmB.map((b) => ({ ...mk(b), meters: b.meters }));
    if (useHeizung) p.heizung = heizB.map((b) => ({ ...mk(b), meters: b.meters }));
    if (useBK) p.bk = bkB.map((b) => ({
      cost_flat: b.cost_flat, tenants: b.tenants,
      bk_start: b.bk_start, bk_end: b.bk_end, limit_per_month: b.limit_per_month,
      // effective living months drive the proration on the backend
      months: monthsBetween(b.eff_start || b.bk_start, b.eff_end || b.bk_end),
    }));
    return p;
  }

  function buildPdfPayload(calc: any) {
    const cs = selected?.start_date || "";
    const ce = selected?.end_date;
    const common = (b: any, c: any) => ({
      bill_period: fmtPeriod(b.bill_start, b.bill_end),
      bill_days: billDays(b.bill_start, b.bill_end),
      period: fmtPeriod(b.bill_start, b.bill_end),
      days: effectiveDays(b.bill_start, b.bill_end, cs, ce),
      num_tenants: numTenants, monthly_limit: b.prepay_monthly,
      cost: c.cost_tenant, limit: c.prepay, is_pauschale: b.is_pauschale, mode: b.mode,
    });
    const zip = (list: any[], res: any[]) =>
      list.map((b, i) => ({ ...(res?.[i] || {}), ...b, ...common(b, res?.[i] || {}) }));
    const payload: any = {};
    if (useStrom && calc.strom) payload.strom = zip(stromB, calc.strom);
    if (useGas && calc.gas) payload.gas = zip(gasB, calc.gas);
    if (useWater && calc.water) payload.water = zip(waterB, calc.water);
    if (useWarmwater && calc.warmwater) payload.warmwater = zip(warmB, calc.warmwater);
    if (useHeizung && calc.heizung) payload.heizung = zip(heizB, calc.heizung);
    if (useBK && calc.bk) {
      // Map each BK billing's form/calc fields onto the exact keys invoice_pdf expects.
      // Abrechnungszeitraum = full bill period; Ihr Zeitraum = tenant's living period.
      payload.bk = bkB.map((b, i) => {
        const c = calc.bk?.[i] || {};
        const effS = b.eff_start || b.bk_start;
        const effE = b.eff_end || b.bk_end;
        return {
          ...c,
          num_tenants: b.tenants,
          total_cost: b.cost_flat,
          monthly_limit: b.limit_per_month,
          bill_period: fmtPeriod(b.bk_start, b.bk_end),
          num_months: monthsBetween(b.bk_start, b.bk_end),
          period: fmtPeriod(effS, effE),
          months: monthsBetween(effS, effE),
          cost: c.period_cost,
          limit: c.limit_period,
          nach: c.nach,
        };
      });
    }
    if (useExtra && extras.length > 0) payload.extra = extras.filter((e) => e.description && e.amount > 0);
    return payload;
  }

  async function calculate() {
    const payload = buildCalcPayload();
    if (Object.keys(payload).length === 0) {
      toast.error("Enable at least one utility section first.");
      return;
    }
    setCalculating(true);
    try {
      const res = await api.post("/api/reports/nebenkostenabrechnung/calculate", payload);
      setCalcResult(res.data);
      toast.success("Calculation complete");
    } catch (e: any) {
      toast.error("Calculation failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setCalculating(false);
    }
  }

  async function generatePdf() {
    if (!selected) { toast.error("Select a contract first."); return; }
    setGenerating(true);
    try {
      // Ensure we have fresh calc results
      let calc = calcResult;
      const payload = buildCalcPayload();
      if (Object.keys(payload).length > 0) {
        try {
          const res = await api.post("/api/reports/nebenkostenabrechnung/calculate", payload);
          calc = res.data;
          setCalcResult(res.data);
        } catch (e: any) {
          toast.error("Calculation failed: " + (e.response?.data?.detail || e.message));
          return;
        }
      }
      const pdfPayload = buildPdfPayload(calc);
      const token = localStorage.getItem("token");
      let res: Response;
      try {
        res = await fetch(`${API}/api/reports/nebenkostenabrechnung/pdf`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            tenant: selected.tenant_name,
            // Leave blank so the backend resolves the full property address
            // (street + postcode + city) from the contract.
            address: "",
            gender: "diverse",
            contract_id: selected.id,
            deduct_kaution: deductKaution,
            ...pdfPayload,
          }),
        });
      } catch (e: any) {
        toast.error("Could not reach the API at " + API + " — " + (e?.message || "network error"));
        return;
      }
      if (!res.ok) {
        let detail = "";
        try { detail = await res.text(); } catch { /* ignore */ }
        toast.error(`PDF generation failed (HTTP ${res.status}). ${detail.slice(0, 200)}`);
        return;
      }
      const blob = await res.blob();
      if (!blob.size) { toast.error("API returned an empty PDF."); return; }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `NBK_${selected.tenant_name}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("PDF downloaded");
    } finally { setGenerating(false); }
  }

  function profileData() {
    return {
      numTenants,
      strom: stromB, gas: gasB, water: waterB, warmwater: warmB, heizung: heizB,
      bk: bkB, extras,
      useStrom, useGas, useWater, useWarmwater, useHeizung, useBK, useExtra,
    };
  }

  async function saveProfile() {
    if (!selected || !profileLabel) return;
    const res = await api.post("/api/billing-profiles/", {
      tenant_id: selected.tenant_id, label: profileLabel, data: profileData(),
    });
    setCurrentProfileId(res.data.id);
    setCurrentProfileLabel(res.data.label);
    qc.invalidateQueries({ queryKey: ["billing-profiles", selected.tenant_id] });
    toast.success(`Profile "${res.data.label}" saved`);
    setProfileLabel("");
  }

  async function updateProfile() {
    if (!selected || currentProfileId == null) return;
    const res = await api.put(`/api/billing-profiles/${currentProfileId}`, {
      tenant_id: selected.tenant_id, label: currentProfileLabel, data: profileData(),
    });
    qc.invalidateQueries({ queryKey: ["billing-profiles", selected.tenant_id] });
    toast.success(`Profile "${res.data.label}" updated`);
  }

  function loadProfile(profile: BillingProfile) {
    const d: any = profile.data || {};
    const num = (v: any, def = 0) => { const n = Number(v); return Number.isFinite(n) ? n : def; };
    const Y = thisYear();
    justLoadedProfile.current = true;  // prevent the auto-tenant effect from clobbering

    setNumTenants(num(d.numTenants ?? d.num_tenants, 1) || 1);

    // Restore the billing data AND the section's on/off state. The enabled state
    // comes from the saved useXxx flag (new schema); legacy profiles without the
    // flag fall back to "enabled if the section had data".
    const setSec = (
      val: any, savedFlag: any, setter: React.Dispatch<React.SetStateAction<any[]>>, def: () => any,
      enable: (v: boolean) => void, hasMeters = false, heiz = false,
    ) => {
      if (val) {
        const a = billingsFrom(val, def, hasMeters, heiz);
        setter(a.length ? a : [def()]);
      } else { setter([def()]); }
      enable(savedFlag !== undefined ? !!savedFlag : !!val);
    };

    setSec(d.strom, d.useStrom, setStromB, defStrom, setUseStrom);
    setSec(d.gas, d.useGas, setGasB, defGas, setUseGas);
    setSec(d.water, d.useWater, setWaterB, defWater, setUseWater);
    setSec(d.warmwater, d.useWarmwater, setWarmB, defWarm, setUseWarmwater, true, false);
    setSec(d.heizung, d.useHeizung, setHeizB, defHeiz, setUseHeizung, true, true);

    // ── Betriebskosten — list (handles legacy single object + Streamlit ints) ──
    if (d.bk) {
      const arr = Array.isArray(d.bk) ? d.bk : [d.bk];
      const mapped = arr.map((b: any) => {
        if (b.bill_s_year) {
          const bs = isoDate(num(b.bill_s_year), num(b.bill_s_month), 1);
          const lastDay = new Date(num(b.bill_e_year), num(b.bill_e_month), 0).getDate();
          const be = isoDate(num(b.bill_e_year), num(b.bill_e_month), lastDay);
          const effLast = new Date(num(b.eff_e_year), num(b.eff_e_month), 0).getDate();
          return {
            cost_flat: num(b.total_cost ?? b.cost_flat),
            tenants: num(b.tenants ?? d.numTenants ?? d.num_tenants, 1),
            bk_start: bs, bk_end: be,
            eff_start: isoDate(num(b.eff_s_year), num(b.eff_s_month), 1),
            eff_end: isoDate(num(b.eff_e_year), num(b.eff_e_month), effLast),
            limit_per_month: num(b.limit_per_month, 206),
          };
        }
        const bs = b.bk_start || isoDate(Y, 1, 1);
        const be = b.bk_end || isoDate(Y, 12, 31);
        const eff = clampPeriod(bs, be, selected?.start_date, selected?.end_date);
        return {
          cost_flat: num(b.cost_flat), tenants: num(b.tenants, 1),
          bk_start: bs, bk_end: be,
          eff_start: b.eff_start || eff.start, eff_end: b.eff_end || eff.end,
          limit_per_month: num(b.limit_per_month, 206),
        };
      });
      setBkB(mapped.length ? mapped : [defBk()]);
      setUseBK(d.useBK !== undefined ? !!d.useBK : true);
    } else { setBkB([defBk()]); setUseBK(false); }

    const extraItems = d.extras ?? d.extra_items;
    if (Array.isArray(extraItems) && extraItems.length) {
      setExtras(extraItems.map((e: any) => ({ description: e.description || "", amount: num(e.amount) })));
      setUseExtra(d.useExtra !== undefined ? !!d.useExtra : true);
    } else setUseExtra(false);

    setCurrentProfileId(profile.id);
    setCurrentProfileLabel(profile.label);
    setCalcResult({});
    toast.success(`Loaded profile: ${profile.label}`);
  }

  function contractLabel(c: Contract) {
    const status = c.terminated ? " (terminated)" :
      (c.end_date && new Date(c.end_date) < new Date() ? " (expired)" : "");
    return `${c.tenant_name} — ${c.apartment_name}${status}`;
  }

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title="Nebenkostenabrechnung" description="Utility cost settlement PDF" />

      {/* Contract + tenant selection */}
      <Card>
        <CardContent className="pt-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Contract</Label>
              <Select value={contractId} onValueChange={setContractId}>
                <SelectTrigger><SelectValue placeholder="Select tenant / contract" /></SelectTrigger>
                <SelectContent>
                  {contracts.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{contractLabel(c)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Num label="Number of tenants" value={numTenants} onChange={setNumTenants} step="1" min="1" />
          </div>
          {selected && (
            <div className="text-xs text-muted-foreground bg-muted/30 rounded p-2 space-y-0.5">
              <p><b>{selected.tenant_name}</b> · {selected.apartment_name} · {selected.property_name}</p>
              <p>Contract: {selected.start_date} → {selected.end_date || "open-ended"}</p>
              {coTenants.length > 0 ? (
                <p className="text-primary">
                  Co-tenants: {coTenants.map((ct) => ct.name).join(", ")} — named on the contract; main tenant is billed for the whole flat (divisor: 1 person)
                </p>
              ) : occupancy && occupancy.auto_count > 1 ? (
                <p className="text-primary">
                  Auto-detected {occupancy.auto_count} tenants sharing this flat (WG) — auto-set to {occupancy.auto_count} persons
                </p>
              ) : null}
            </div>
          )}

          {selected && profiles.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs">Load saved profile</Label>
              <div className="flex gap-2 flex-wrap">
                {profiles.map((p) => (
                  <Button key={p.id} variant={currentProfileId === p.id ? "default" : "outline"} size="sm" onClick={() => loadProfile(p)}>
                    <Upload className="size-3 mr-1" /> {p.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Strom ── */}
      <SectionCard id="strom" title="⚡ Strom (Electricity)" enabled={useStrom} onToggle={setUseStrom}>
        {stromB.map((b, i) => (
          <BillingShell key={i} idx={i} count={stromB.length} b={b}
            set={(patch) => updateAt(setStromB, i, patch)}
            onRemove={() => setStromB((a) => a.filter((_, j) => j !== i))}
            costLabel="Total Strom cost for period (€)"
            preview={<CalcPreview label="Strom" result={calcResult.strom?.[i]} />}>
            <FieldRow>
              <Num label="Start reading (kWh)" value={b.start_kwh} onChange={(v) => updateAt(setStromB, i, { start_kwh: v })} />
              <Num label="End reading (kWh)" value={b.end_kwh} onChange={(v) => updateAt(setStromB, i, { end_kwh: v })} />
              <Num label="Arbeitspreis (€/kWh)" value={b.arbeitspreis} step="0.0001" onChange={(v) => updateAt(setStromB, i, { arbeitspreis: v })} />
              <Num label="Grundpreis (€/month)" value={b.grundpreis_monthly} onChange={(v) => updateAt(setStromB, i, { grundpreis_monthly: v })} />
            </FieldRow>
          </BillingShell>
        ))}
        <Button variant="outline" size="sm" onClick={() => setStromB((a) => [...a, defStrom()])}>
          <Plus className="size-4 mr-1" /> Add billing
        </Button>
      </SectionCard>

      {/* ── Gas ── */}
      <SectionCard id="gas" title="🔥 Gas" enabled={useGas} onToggle={setUseGas}>
        {gasB.map((b, i) => (
          <BillingShell key={i} idx={i} count={gasB.length} b={b}
            set={(patch) => updateAt(setGasB, i, patch)}
            onRemove={() => setGasB((a) => a.filter((_, j) => j !== i))}
            costLabel="Total Gas cost for period (€)"
            preview={<CalcPreview label="Gas" result={calcResult.gas?.[i]} />}>
            <>
              <FieldRow>
                <Num label="Start reading (m³)" value={b.start_m3} step="0.001" onChange={(v) => updateAt(setGasB, i, { start_m3: v })} />
                <Num label="End reading (m³)" value={b.end_m3} step="0.001" onChange={(v) => updateAt(setGasB, i, { end_m3: v })} />
                <Num label="Umrechnung (kWh/m³)" value={b.umrechnungsfaktor} step="0.0001" onChange={(v) => updateAt(setGasB, i, { umrechnungsfaktor: v })} />
                <Num label="Arbeitspreis (€/kWh)" value={b.arbeitspreis} step="0.0001" onChange={(v) => updateAt(setGasB, i, { arbeitspreis: v })} />
              </FieldRow>
              <div className="md:w-1/2">
                <Num label="Grundpreis (€/month)" value={b.grundpreis_monthly} onChange={(v) => updateAt(setGasB, i, { grundpreis_monthly: v })} />
              </div>
              {aptGasMeters.length > 0 && (
                <p className="text-xs text-muted-foreground">Auto-filled from: {aptGasMeters[0].serial_number || "registered meter"} ({aptGasMeters[0].z_zahl} × {aptGasMeters[0].brennwert})</p>
              )}
            </>
          </BillingShell>
        ))}
        <Button variant="outline" size="sm" onClick={() => setGasB((a) => [...a, defGas()])}>
          <Plus className="size-4 mr-1" /> Add billing
        </Button>
      </SectionCard>

      {/* ── Kaltwasser ── */}
      <SectionCard id="water" title="💧 Kaltwasser (Cold Water)" enabled={useWater} onToggle={setUseWater}>
        {waterB.map((b, i) => (
          <BillingShell key={i} idx={i} count={waterB.length} b={b}
            set={(patch) => updateAt(setWaterB, i, patch)}
            onRemove={() => setWaterB((a) => a.filter((_, j) => j !== i))}
            costLabel="Total Kaltwasser cost for period (€)"
            preview={<CalcPreview label="Kaltwasser" result={calcResult.water?.[i]} />}>
            <FieldRow>
              <Num label="Start (m³)" value={b.start_m3} step="0.001" onChange={(v) => updateAt(setWaterB, i, { start_m3: v })} />
              <Num label="End (m³)" value={b.end_m3} step="0.001" onChange={(v) => updateAt(setWaterB, i, { end_m3: v })} />
              <Num label="Frischwasser (€/m³)" value={b.frischwasser_per_m3} step="0.001" onChange={(v) => updateAt(setWaterB, i, { frischwasser_per_m3: v })} />
              <Num label="Abwasser (€/m³)" value={b.abwasser_per_m3} step="0.001" onChange={(v) => updateAt(setWaterB, i, { abwasser_per_m3: v })} />
            </FieldRow>
          </BillingShell>
        ))}
        <Button variant="outline" size="sm" onClick={() => setWaterB((a) => [...a, defWater()])}>
          <Plus className="size-4 mr-1" /> Add billing
        </Button>
      </SectionCard>

      {/* ── Warmwasser ── */}
      <SectionCard id="warmwater" title="♨️ Warmwasser (Hot Water)" enabled={useWarmwater} onToggle={setUseWarmwater}>
        {warmB.map((b, i) => (
          <BillingShell key={i} idx={i} count={warmB.length} b={b}
            set={(patch) => updateAt(setWarmB, i, patch)}
            onRemove={() => setWarmB((a) => a.filter((_, j) => j !== i))}
            costLabel="Total Warmwasser cost for period (€)"
            preview={<CalcPreview label="Warmwasser" result={calcResult.warmwater?.[i]} />}>
            <>
              {b.meters.map((m: any, mi: number) => (
                <div key={mi} className="flex gap-3 items-end">
                  <Num label={`Meter ${mi + 1} start`} value={m.start} step="0.001"
                    onChange={(v) => updateAt(setWarmB, i, { meters: b.meters.map((mm: any, k: number) => k === mi ? { ...mm, start: v } : mm) })} />
                  <Num label="End" value={m.end} step="0.001"
                    onChange={(v) => updateAt(setWarmB, i, { meters: b.meters.map((mm: any, k: number) => k === mi ? { ...mm, end: v } : mm) })} />
                  {b.meters.length > 1 && (
                    <Button variant="ghost" size="icon" className="mb-0.5"
                      onClick={() => updateAt(setWarmB, i, { meters: b.meters.filter((_: any, k: number) => k !== mi) })}>
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  )}
                </div>
              ))}
              <Button variant="outline" size="sm"
                onClick={() => updateAt(setWarmB, i, { meters: [...b.meters, { start: 0, end: 0 }] })}>
                <Plus className="size-4 mr-1" /> Add meter
              </Button>
              <FieldRow>
                <Num label="Frischwasser (€/m³)" value={b.frischwasser_per_m3} step="0.001" onChange={(v) => updateAt(setWarmB, i, { frischwasser_per_m3: v })} />
                <Num label="Abwasser (€/m³)" value={b.abwasser_per_m3} step="0.001" onChange={(v) => updateAt(setWarmB, i, { abwasser_per_m3: v })} />
                <Num label="Heizenergie (€/m³)" value={b.heizenergie_per_m3} step="0.001" onChange={(v) => updateAt(setWarmB, i, { heizenergie_per_m3: v })} />
              </FieldRow>
            </>
          </BillingShell>
        ))}
        <Button variant="outline" size="sm" onClick={() => setWarmB((a) => [...a, defWarm()])}>
          <Plus className="size-4 mr-1" /> Add billing
        </Button>
      </SectionCard>

      {/* ── Heizung ── */}
      <SectionCard id="heizung" title="🌡️ Heizkosten (Heating)" enabled={useHeizung} onToggle={setUseHeizung}>
        {heizB.map((b, i) => (
          <BillingShell key={i} idx={i} count={heizB.length} b={b}
            set={(patch) => updateAt(setHeizB, i, patch)}
            onRemove={() => setHeizB((a) => a.filter((_, j) => j !== i))}
            costLabel="Total Heizkosten for period (€)"
            preview={<CalcPreview label="Heizkosten" result={calcResult.heizung?.[i]} />}>
            <>
              {b.meters.map((m: any, mi: number) => (
                <div key={mi} className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end border-b border-border pb-3">
                  <Num label="Start" value={m.start} step="0.001"
                    onChange={(v) => updateAt(setHeizB, i, { meters: b.meters.map((mm: any, k: number) => k === mi ? { ...mm, start: v } : mm) })} />
                  <Num label="End" value={m.end} step="0.001"
                    onChange={(v) => updateAt(setHeizB, i, { meters: b.meters.map((mm: any, k: number) => k === mi ? { ...mm, end: v } : mm) })} />
                  <Num label="€/kWh" value={m.unit_price} step="0.0001"
                    onChange={(v) => updateAt(setHeizB, i, { meters: b.meters.map((mm: any, k: number) => k === mi ? { ...mm, unit_price: v } : mm) })} />
                  <Num label="Conv. factor" value={m.conversion_factor} step="0.0001"
                    onChange={(v) => updateAt(setHeizB, i, { meters: b.meters.map((mm: any, k: number) => k === mi ? { ...mm, conversion_factor: v } : mm) })} />
                  {b.meters.length > 1 && (
                    <Button variant="ghost" size="icon" className="mb-0.5"
                      onClick={() => updateAt(setHeizB, i, { meters: b.meters.filter((_: any, k: number) => k !== mi) })}>
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  )}
                </div>
              ))}
              <Button variant="outline" size="sm"
                onClick={() => updateAt(setHeizB, i, { meters: [...b.meters, { start: 0, end: 0, unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0 }] })}>
                <Plus className="size-4 mr-1" /> Add meter
              </Button>
            </>
          </BillingShell>
        ))}
        <Button variant="outline" size="sm" onClick={() => setHeizB((a) => [...a, defHeiz()])}>
          <Plus className="size-4 mr-1" /> Add billing
        </Button>
      </SectionCard>

      {/* ── Betriebskosten ── */}
      <SectionCard id="bk" title="🏢 Betriebskosten (Operating Costs)" enabled={useBK} onToggle={setUseBK}>
        {bkB.map((b, i) => {
          const r = calcResult.bk?.[i];
          return (
            <div key={i} className="rounded-md border border-border/70 bg-muted/20 p-3 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">Billing {i + 1}</span>
                {bkB.length > 1 && (
                  <Button variant="ghost" size="icon" className="size-7" onClick={() => setBkB((a) => a.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                )}
              </div>
              <FieldRow>
                <Num label="Total cost (€)" value={b.cost_flat} onChange={(v) => updateAt(setBkB, i, { cost_flat: v })} />
                <Num label="Tenants" value={b.tenants} step="1" min="1" onChange={(v) => updateAt(setBkB, i, { tenants: v })} />
                <Num label="Prepay €/month (total, all persons)" value={b.limit_per_month} onChange={(v) => updateAt(setBkB, i, { limit_per_month: v })} />
              </FieldRow>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Abrechnungszeitraum (billing period)</Label>
                <FieldRow>
                  <DateF label="Start" value={b.bk_start} onChange={(v) => updateAt(setBkB, i, { bk_start: v })} />
                  <DateF label="End" value={b.bk_end} onChange={(v) => updateAt(setBkB, i, { bk_end: v })} />
                </FieldRow>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-primary">Ihr Zeitraum (tenant&apos;s living period — from the contract, editable)</Label>
                <FieldRow>
                  <DateF label="Start" value={b.eff_start} onChange={(v) => updateAt(setBkB, i, { eff_start: v })} />
                  <DateF label="End" value={b.eff_end} onChange={(v) => updateAt(setBkB, i, { eff_end: v })} />
                </FieldRow>
                <p className="text-xs text-muted-foreground">
                  = {monthsBetween(b.eff_start || b.bk_start, b.eff_end || b.bk_end)} Monate (used for proration)
                </p>
              </div>
              {r && (
                <div className="rounded-md bg-primary/10 border border-primary/20 p-3 text-sm space-y-1">
                  <p className="font-medium text-primary text-xs uppercase tracking-wide">Betriebskosten — Preview</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <span>Period cost: <b>€ {r.period_cost?.toFixed(2)}</b></span>
                    <span>Limit: <b>€ {r.limit_period?.toFixed(2)}</b></span>
                    <span className={r.nach > 0 ? "text-destructive font-bold" : "text-emerald-400 font-bold"}>
                      Nachzahlung: € {r.nach?.toFixed(2)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        <Button variant="outline" size="sm" onClick={() => setBkB((a) => {
          const nb = defBk(numTenants);
          const eff = selected ? clampPeriod(nb.bk_start, nb.bk_end, selected.start_date, selected.end_date) : { start: "", end: "" };
          return [...a, { ...nb, eff_start: eff.start, eff_end: eff.end }];
        })}>
          <Plus className="size-4 mr-1" /> Add billing
        </Button>
      </SectionCard>

      {/* ── Extra items ── */}
      <SectionCard id="extra" title="➕ Zusätzliche Positionen (Extra Items)" enabled={useExtra} onToggle={setUseExtra}>
        {extras.map((ex, i) => (
          <div key={i} className="flex gap-3 items-end">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Description</Label>
              <Input className="h-8 text-sm" value={ex.description}
                onChange={(e) => setExtras((es) => es.map((ee, ii) => ii === i ? { ...ee, description: e.target.value } : ee))} />
            </div>
            <div className="w-32 space-y-1">
              <Label className="text-xs">Amount (€)</Label>
              <Input type="number" step="0.01" className="h-8 text-sm" value={ex.amount}
                onChange={(e) => setExtras((es) => es.map((ee, ii) => ii === i ? { ...ee, amount: Number(e.target.value) } : ee))} />
            </div>
            <Button variant="ghost" size="icon" onClick={() => setExtras((es) => es.filter((_, ii) => ii !== i))} className="mb-0.5">
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setExtras((es) => [...es, { description: "", amount: 0 }])}>
          <Plus className="size-4 mr-1" /> Add item
        </Button>
      </SectionCard>

      {/* ── Deposit (Kaution) offset ── */}
      {selected && selected.kaution_amount && !selected.kaution_returned_date ? (
        <Card>
          <CardContent className="pt-4 space-y-1">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={deductKaution} onChange={(e) => setDeductKaution(e.target.checked)} className="size-4 accent-primary" />
              Deduct the outstanding amount from the deposit (Kaution: {selected.kaution_amount.toFixed(2)} {selected.kaution_currency})
            </label>
            <p className="text-xs text-muted-foreground">
              Adds a Kautionsverrechnung block to the PDF, offsetting the Nachzahlung against the still-held deposit.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {/* ── Actions ── */}
      <div className="flex gap-3 flex-wrap">
        <Button onClick={calculate} disabled={!selected || calculating} variant="outline">
          <Calculator className="size-4 mr-1" />
          {calculating ? "Calculating…" : "Calculate Preview"}
        </Button>
        <Button onClick={generatePdf}
          disabled={!selected || generating || (!useStrom && !useGas && !useWater && !useWarmwater && !useHeizung && !useBK && !useExtra)}>
          <FileDown className="size-4 mr-1" />
          {generating ? "Generating PDF…" : "Generate PDF"}
        </Button>
        {selected && (
          <div className="flex gap-2 items-center flex-wrap">
            {currentProfileId != null && (
              <Button variant="default" onClick={updateProfile}>
                <Save className="size-4 mr-1" /> Update “{currentProfileLabel}”
              </Button>
            )}
            <Input className="h-9 w-40 text-sm" placeholder="New profile name"
              value={profileLabel} onChange={(e) => setProfileLabel(e.target.value)} />
            <Button variant="outline" onClick={saveProfile} disabled={!profileLabel}>
              <Save className="size-4 mr-1" /> Save as new
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
