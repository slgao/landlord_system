"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Contract, GasMeter, BillingProfile } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      {enabled && <CardContent className="space-y-3">{children}</CardContent>}
    </Card>
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

  // section toggles
  const [useStrom, setUseStrom] = useState(false);
  const [useGas, setUseGas] = useState(false);
  const [useWater, setUseWater] = useState(false);
  const [useWarmwater, setUseWarmwater] = useState(false);
  const [useHeizung, setUseHeizung] = useState(false);
  const [useBK, setUseBK] = useState(false);
  const [useExtra, setUseExtra] = useState(false);

  const [strom, setStrom] = useState({
    bill_start: isoDate(thisYear(), 1, 1), bill_end: isoDate(thisYear(), 12, 31),
    start_kwh: 0, end_kwh: 0, arbeitspreis: 0, grundpreis_monthly: 0,
    prepay_monthly: 0, is_pauschale: false,
  });
  const [gas, setGas] = useState({
    bill_start: isoDate(thisYear(), 1, 1), bill_end: isoDate(thisYear(), 12, 31),
    start_m3: 0, end_m3: 0, umrechnungsfaktor: 10.0, arbeitspreis: 0,
    grundpreis_monthly: 0, prepay_monthly: 0, is_pauschale: false,
  });
  const [water, setWater] = useState({
    bill_start: isoDate(thisYear(), 1, 1), bill_end: isoDate(thisYear(), 12, 31),
    start_m3: 0, end_m3: 0, frischwasser_per_m3: 0, abwasser_per_m3: 0,
    prepay_monthly: 0, is_pauschale: false,
  });
  const [wwMeters, setWwMeters] = useState([{ start: 0, end: 0 }]);
  const [warmwater, setWarmwater] = useState({
    bill_start: isoDate(thisYear(), 1, 1), bill_end: isoDate(thisYear(), 12, 31),
    frischwasser_per_m3: 0, abwasser_per_m3: 0, heizenergie_per_m3: 0,
    prepay_monthly: 0, is_pauschale: false,
  });
  const [hzMeters, setHzMeters] = useState([{ start: 0, end: 0, unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0 }]);
  const [heizung, setHeizung] = useState({
    bill_start: isoDate(thisYear(), 1, 1), bill_end: isoDate(thisYear(), 12, 31),
    prepay_monthly: 0, is_pauschale: false,
  });
  const [bk, setBk] = useState({
    cost_flat: 0, tenants: 1, months: 12,
    bk_start: isoDate(thisYear(), 1, 1), bk_end: isoDate(thisYear(), 12, 31),
    limit_per_month: 206,
  });
  const [extras, setExtras] = useState<{ description: string; amount: number }[]>([]);

  // Tracks the contract id for which we last auto-set the tenant count,
  // so that loading a profile (which sets its own numTenants) isn't clobbered.
  const autoTenantContract = useRef<string | null>(null);
  const justLoadedProfile = useRef(false);

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

  // Auto-set tenant count = 1 (primary) + co-tenants, once per contract selection.
  // Skipped right after loading a profile so the profile's value wins.
  useEffect(() => {
    if (!selected?.id) return;
    if (justLoadedProfile.current) { justLoadedProfile.current = false; return; }
    setNumTenants(1 + coTenants.length);
    autoTenantContract.current = String(selected.id);
  }, [selected?.id, coTenants.length]);

  // Auto-fill gas Umrechnungsfaktor from a registered gas meter (in an effect,
  // never during render).
  useEffect(() => {
    if (!selected?.apartment_id) return;
    const apt = gasMeters.filter((m) => m.apartment_id === selected.apartment_id);
    if (apt.length > 0) {
      const gm = apt[0];
      const factor = parseFloat((gm.z_zahl * gm.brennwert).toFixed(4));
      setGas((g) => (g.umrechnungsfaktor === 10.0 ? { ...g, umrechnungsfaktor: factor } : g));
    }
  }, [selected?.apartment_id, gasMeters]);

  const aptGasMeters = gasMeters.filter((m) => m.apartment_id === selected?.apartment_id);

  // ── payload builders ──
  function buildCalcPayload() {
    const cs = selected?.start_date || "";
    const ce = selected?.end_date;
    const payload: any = {};
    if (useStrom) {
      payload.strom = { ...strom, num_tenants: numTenants,
        bill_days: billDays(strom.bill_start, strom.bill_end),
        eff_days: effectiveDays(strom.bill_start, strom.bill_end, cs, ce) };
    }
    if (useGas) {
      payload.gas = { ...gas, num_tenants: numTenants,
        bill_days: billDays(gas.bill_start, gas.bill_end),
        eff_days: effectiveDays(gas.bill_start, gas.bill_end, cs, ce) };
    }
    if (useWater) {
      payload.water = { ...water, num_tenants: numTenants,
        bill_days: billDays(water.bill_start, water.bill_end),
        eff_days: effectiveDays(water.bill_start, water.bill_end, cs, ce) };
    }
    if (useWarmwater) {
      payload.warmwater = { ...warmwater, meters: wwMeters, num_tenants: numTenants,
        bill_days: billDays(warmwater.bill_start, warmwater.bill_end),
        eff_days: effectiveDays(warmwater.bill_start, warmwater.bill_end, cs, ce) };
    }
    if (useHeizung) {
      payload.heizung = { ...heizung, meters: hzMeters, num_tenants: numTenants,
        bill_days: billDays(heizung.bill_start, heizung.bill_end),
        eff_days: effectiveDays(heizung.bill_start, heizung.bill_end, cs, ce) };
    }
    if (useBK) payload.bk = bk;
    return payload;
  }

  function buildPdfPayload(calc: any) {
    const cs = selected?.start_date || "";
    const ce = selected?.end_date;
    const payload: any = {};
    const common = (st: any, c: any) => ({
      bill_period: fmtPeriod(st.bill_start, st.bill_end),
      bill_days: billDays(st.bill_start, st.bill_end),
      period: fmtPeriod(st.bill_start, st.bill_end),
      days: effectiveDays(st.bill_start, st.bill_end, cs, ce),
      num_tenants: numTenants, monthly_limit: st.prepay_monthly,
      cost: c.cost_tenant, limit: c.prepay, is_pauschale: st.is_pauschale,
    });
    if (useStrom && calc.strom) payload.strom = { ...calc.strom, ...strom, ...common(strom, calc.strom) };
    if (useGas && calc.gas) payload.gas = { ...calc.gas, ...gas, ...common(gas, calc.gas) };
    if (useWater && calc.water) payload.water = { ...calc.water, ...water, ...common(water, calc.water) };
    if (useWarmwater && calc.warmwater) payload.warmwater = { ...calc.warmwater, ...warmwater, ...common(warmwater, calc.warmwater) };
    if (useHeizung && calc.heizung) payload.heizung = { ...calc.heizung, ...heizung, ...common(heizung, calc.heizung) };
    if (useBK && calc.bk) payload.bk = { ...calc.bk, ...bk, period: fmtPeriod(bk.bk_start, bk.bk_end), cost: calc.bk.period_cost, limit: calc.bk.limit_period };
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
    if (!selected) return;
    // Ensure we have fresh calc results
    let calc = calcResult;
    const payload = buildCalcPayload();
    if (Object.keys(payload).length > 0) {
      try {
        const res = await api.post("/api/reports/nebenkostenabrechnung/calculate", payload);
        calc = res.data;
        setCalcResult(res.data);
      } catch { /* fall back to existing calcResult */ }
    }
    setGenerating(true);
    try {
      const pdfPayload = buildPdfPayload(calc);
      const token = localStorage.getItem("token");
      const res = await fetch(`${API}/api/reports/nebenkostenabrechnung/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          tenant: selected.tenant_name,
          address: selected.property_name || "",
          gender: "diverse",
          contract_id: selected.id,
          ...pdfPayload,
        }),
      });
      if (!res.ok) { toast.error("PDF generation failed"); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `NBK_${selected.tenant_name}.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success("PDF downloaded");
    } finally { setGenerating(false); }
  }

  async function saveProfile() {
    if (!selected || !profileLabel) return;
    await api.post("/api/billing-profiles/", {
      tenant_id: selected.tenant_id,
      label: profileLabel,
      data: {
        numTenants, strom, gas, water, warmwater, heizung, bk,
        wwMeters, hzMeters, extras,
        useStrom, useGas, useWater, useWarmwater, useHeizung, useBK, useExtra,
      },
    });
    toast.success("Profile saved");
    setProfileLabel("");
  }

  function loadProfile(profile: BillingProfile) {
    // Handles BOTH the Streamlit schema (prepay_pm, num_tenants, extra_items,
    // section-presence = enabled, heizung price_kwh, bk month/year ints) and the
    // newer Next.js schema (prepay_monthly, numTenants, extras, useXxx toggles).
    const d: any = profile.data || {};
    const num = (v: any, def = 0) => { const n = Number(v); return Number.isFinite(n) ? n : def; };
    const Y = thisYear();
    justLoadedProfile.current = true;  // prevent the auto-tenant effect from clobbering

    setNumTenants(num(d.numTenants ?? d.num_tenants, 1));

    // ── Strom ──
    if (d.strom) {
      const s = d.strom;
      setStrom({
        bill_start: s.bill_start || isoDate(Y, 1, 1),
        bill_end: s.bill_end || isoDate(Y, 12, 31),
        start_kwh: num(s.start_kwh), end_kwh: num(s.end_kwh),
        arbeitspreis: num(s.arbeitspreis), grundpreis_monthly: num(s.grundpreis_monthly),
        prepay_monthly: num(s.prepay_monthly ?? s.prepay_pm),
        is_pauschale: !!s.is_pauschale,
      });
      setUseStrom(true);
    } else setUseStrom(false);

    // ── Gas ──
    if (d.gas) {
      const g = d.gas;
      setGas({
        bill_start: g.bill_start || isoDate(Y, 1, 1),
        bill_end: g.bill_end || isoDate(Y, 12, 31),
        start_m3: num(g.start_m3), end_m3: num(g.end_m3),
        umrechnungsfaktor: num(g.umrechnungsfaktor, 10.0),
        arbeitspreis: num(g.arbeitspreis), grundpreis_monthly: num(g.grundpreis_monthly),
        prepay_monthly: num(g.prepay_monthly ?? g.prepay_pm),
        is_pauschale: !!g.is_pauschale,
      });
      setUseGas(true);
    } else setUseGas(false);

    // ── Kaltwasser ──
    if (d.water) {
      const w = d.water;
      setWater({
        bill_start: w.bill_start || isoDate(Y, 1, 1),
        bill_end: w.bill_end || isoDate(Y, 12, 31),
        start_m3: num(w.start_m3), end_m3: num(w.end_m3),
        frischwasser_per_m3: num(w.frischwasser_per_m3), abwasser_per_m3: num(w.abwasser_per_m3),
        prepay_monthly: num(w.prepay_monthly ?? w.prepay_pm),
        is_pauschale: !!w.is_pauschale,
      });
      setUseWater(true);
    } else setUseWater(false);

    // ── Warmwasser ──
    if (d.warmwater) {
      const ww = d.warmwater;
      setWarmwater({
        bill_start: ww.bill_start || isoDate(Y, 1, 1),
        bill_end: ww.bill_end || isoDate(Y, 12, 31),
        frischwasser_per_m3: num(ww.frischwasser_per_m3), abwasser_per_m3: num(ww.abwasser_per_m3),
        heizenergie_per_m3: num(ww.heizenergie_per_m3),
        prepay_monthly: num(ww.prepay_monthly ?? ww.prepay_pm),
        is_pauschale: !!ww.is_pauschale,
      });
      if (Array.isArray(ww.meters) && ww.meters.length)
        setWwMeters(ww.meters.map((m: any) => ({ start: num(m.start), end: num(m.end) })));
      else if (Array.isArray(d.wwMeters)) setWwMeters(d.wwMeters);
      setUseWarmwater(true);
    } else setUseWarmwater(false);

    // ── Heizung (Streamlit stores a single price_kwh; apply to each meter) ──
    if (d.heizung) {
      const h = d.heizung;
      setHeizung({
        bill_start: h.bill_start || isoDate(Y, 1, 1),
        bill_end: h.bill_end || isoDate(Y, 12, 31),
        prepay_monthly: num(h.prepay_monthly ?? h.prepay_pm),
        is_pauschale: !!h.is_pauschale,
      });
      const price = num(h.price_kwh);
      if (Array.isArray(h.meters) && h.meters.length)
        setHzMeters(h.meters.map((m: any) => ({
          start: num(m.start), end: num(m.end),
          unit_price: num(m.unit_price ?? price),
          unit_label: m.unit_label || "Einheiten",
          conversion_factor: num(m.conversion_factor, 1.0),
        })));
      else if (Array.isArray(d.hzMeters)) setHzMeters(d.hzMeters);
      setUseHeizung(true);
    } else setUseHeizung(false);

    // ── Betriebskosten (Streamlit uses month/year ints; Next.js uses dates) ──
    if (d.bk) {
      const b = d.bk;
      if (b.bill_s_year) {
        const bs = isoDate(num(b.bill_s_year), num(b.bill_s_month), 1);
        const lastDay = new Date(num(b.bill_e_year), num(b.bill_e_month), 0).getDate();
        const be = isoDate(num(b.bill_e_year), num(b.bill_e_month), lastDay);
        const months = (num(b.eff_e_year) - num(b.eff_s_year)) * 12 + (num(b.eff_e_month) - num(b.eff_s_month)) + 1;
        setBk({
          cost_flat: num(b.total_cost ?? b.cost_flat),
          tenants: num(d.numTenants ?? d.num_tenants, 1),
          months: Math.max(1, months),
          bk_start: bs, bk_end: be,
          limit_per_month: num(b.limit_per_month, 206),
        });
      } else {
        setBk({
          cost_flat: num(b.cost_flat), tenants: num(b.tenants, 1), months: num(b.months, 12),
          bk_start: b.bk_start || isoDate(Y, 1, 1), bk_end: b.bk_end || isoDate(Y, 12, 31),
          limit_per_month: num(b.limit_per_month, 206),
        });
      }
      setUseBK(true);
    } else setUseBK(false);

    // ── Extra items ──
    const extraItems = d.extras ?? d.extra_items;
    if (Array.isArray(extraItems) && extraItems.length) {
      setExtras(extraItems.map((e: any) => ({ description: e.description || "", amount: num(e.amount) })));
      setUseExtra(true);
    } else setUseExtra(false);

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
              {coTenants.length > 0 && (
                <p className="text-primary">
                  Co-tenants: {coTenants.map((ct) => ct.name).join(", ")} — auto-set to {1 + coTenants.length} persons
                </p>
              )}
            </div>
          )}

          {selected && profiles.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs">Load saved profile</Label>
              <div className="flex gap-2 flex-wrap">
                {profiles.map((p) => (
                  <Button key={p.id} variant="outline" size="sm" onClick={() => loadProfile(p)}>
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
        <FieldRow>
          <DateF label="Bill start" value={strom.bill_start} onChange={(v) => setStrom((s) => ({ ...s, bill_start: v }))} />
          <DateF label="Bill end" value={strom.bill_end} onChange={(v) => setStrom((s) => ({ ...s, bill_end: v }))} />
        </FieldRow>
        <FieldRow>
          <Num label="Start reading (kWh)" value={strom.start_kwh} onChange={(v) => setStrom((s) => ({ ...s, start_kwh: v }))} />
          <Num label="End reading (kWh)" value={strom.end_kwh} onChange={(v) => setStrom((s) => ({ ...s, end_kwh: v }))} />
          <Num label="Arbeitspreis (€/kWh)" value={strom.arbeitspreis} step="0.0001" onChange={(v) => setStrom((s) => ({ ...s, arbeitspreis: v }))} />
          <Num label="Grundpreis (€/month)" value={strom.grundpreis_monthly} onChange={(v) => setStrom((s) => ({ ...s, grundpreis_monthly: v }))} />
        </FieldRow>
        <div className="flex items-center gap-4">
          <Num label="Prepay (€/month)" value={strom.prepay_monthly} onChange={(v) => setStrom((s) => ({ ...s, prepay_monthly: v }))} />
          <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
            <input type="checkbox" checked={strom.is_pauschale} onChange={(e) => setStrom((s) => ({ ...s, is_pauschale: e.target.checked }))} className="accent-primary" />
            Pauschale
          </label>
        </div>
        <CalcPreview label="Strom" result={calcResult.strom} />
      </SectionCard>

      {/* ── Gas ── */}
      <SectionCard id="gas" title="🔥 Gas" enabled={useGas} onToggle={setUseGas}>
        <FieldRow>
          <DateF label="Bill start" value={gas.bill_start} onChange={(v) => setGas((s) => ({ ...s, bill_start: v }))} />
          <DateF label="Bill end" value={gas.bill_end} onChange={(v) => setGas((s) => ({ ...s, bill_end: v }))} />
        </FieldRow>
        <FieldRow>
          <Num label="Start reading (m³)" value={gas.start_m3} step="0.001" onChange={(v) => setGas((s) => ({ ...s, start_m3: v }))} />
          <Num label="End reading (m³)" value={gas.end_m3} step="0.001" onChange={(v) => setGas((s) => ({ ...s, end_m3: v }))} />
          <Num label="Umrechnung (kWh/m³)" value={gas.umrechnungsfaktor} step="0.0001" onChange={(v) => setGas((s) => ({ ...s, umrechnungsfaktor: v }))} />
          <Num label="Arbeitspreis (€/kWh)" value={gas.arbeitspreis} step="0.0001" onChange={(v) => setGas((s) => ({ ...s, arbeitspreis: v }))} />
        </FieldRow>
        <div className="flex items-center gap-4">
          <Num label="Grundpreis (€/month)" value={gas.grundpreis_monthly} onChange={(v) => setGas((s) => ({ ...s, grundpreis_monthly: v }))} />
          <Num label="Prepay (€/month)" value={gas.prepay_monthly} onChange={(v) => setGas((s) => ({ ...s, prepay_monthly: v }))} />
          <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
            <input type="checkbox" checked={gas.is_pauschale} onChange={(e) => setGas((s) => ({ ...s, is_pauschale: e.target.checked }))} className="accent-primary" />
            Pauschale
          </label>
        </div>
        {aptGasMeters.length > 0 && (
          <p className="text-xs text-muted-foreground">Auto-filled from: {aptGasMeters[0].serial_number || "registered meter"} ({aptGasMeters[0].z_zahl} × {aptGasMeters[0].brennwert})</p>
        )}
        <CalcPreview label="Gas" result={calcResult.gas} />
      </SectionCard>

      {/* ── Kaltwasser ── */}
      <SectionCard id="water" title="💧 Kaltwasser (Cold Water)" enabled={useWater} onToggle={setUseWater}>
        <FieldRow>
          <DateF label="Bill start" value={water.bill_start} onChange={(v) => setWater((s) => ({ ...s, bill_start: v }))} />
          <DateF label="Bill end" value={water.bill_end} onChange={(v) => setWater((s) => ({ ...s, bill_end: v }))} />
          <Num label="Start (m³)" value={water.start_m3} step="0.001" onChange={(v) => setWater((s) => ({ ...s, start_m3: v }))} />
          <Num label="End (m³)" value={water.end_m3} step="0.001" onChange={(v) => setWater((s) => ({ ...s, end_m3: v }))} />
        </FieldRow>
        <FieldRow>
          <Num label="Frischwasser (€/m³)" value={water.frischwasser_per_m3} step="0.001" onChange={(v) => setWater((s) => ({ ...s, frischwasser_per_m3: v }))} />
          <Num label="Abwasser (€/m³)" value={water.abwasser_per_m3} step="0.001" onChange={(v) => setWater((s) => ({ ...s, abwasser_per_m3: v }))} />
          <Num label="Prepay (€/month)" value={water.prepay_monthly} onChange={(v) => setWater((s) => ({ ...s, prepay_monthly: v }))} />
          <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
            <input type="checkbox" checked={water.is_pauschale} onChange={(e) => setWater((s) => ({ ...s, is_pauschale: e.target.checked }))} className="accent-primary" />
            Pauschale
          </label>
        </FieldRow>
        <CalcPreview label="Kaltwasser" result={calcResult.water} />
      </SectionCard>

      {/* ── Warmwasser ── */}
      <SectionCard id="warmwater" title="♨️ Warmwasser (Hot Water)" enabled={useWarmwater} onToggle={setUseWarmwater}>
        <FieldRow>
          <DateF label="Bill start" value={warmwater.bill_start} onChange={(v) => setWarmwater((s) => ({ ...s, bill_start: v }))} />
          <DateF label="Bill end" value={warmwater.bill_end} onChange={(v) => setWarmwater((s) => ({ ...s, bill_end: v }))} />
        </FieldRow>
        {wwMeters.map((m, i) => (
          <div key={i} className="flex gap-3 items-end">
            <Num label={`Meter ${i + 1} start`} value={m.start} step="0.001" onChange={(v) => setWwMeters((ms) => ms.map((mm, ii) => ii === i ? { ...mm, start: v } : mm))} />
            <Num label="End" value={m.end} step="0.001" onChange={(v) => setWwMeters((ms) => ms.map((mm, ii) => ii === i ? { ...mm, end: v } : mm))} />
            {wwMeters.length > 1 && <Button variant="ghost" size="icon" onClick={() => setWwMeters((ms) => ms.filter((_, ii) => ii !== i))} className="mb-0.5"><Trash2 className="size-4 text-destructive" /></Button>}
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setWwMeters((ms) => [...ms, { start: 0, end: 0 }])}>
          <Plus className="size-4 mr-1" /> Add meter
        </Button>
        <FieldRow>
          <Num label="Frischwasser (€/m³)" value={warmwater.frischwasser_per_m3} step="0.001" onChange={(v) => setWarmwater((s) => ({ ...s, frischwasser_per_m3: v }))} />
          <Num label="Abwasser (€/m³)" value={warmwater.abwasser_per_m3} step="0.001" onChange={(v) => setWarmwater((s) => ({ ...s, abwasser_per_m3: v }))} />
          <Num label="Heizenergie (€/m³)" value={warmwater.heizenergie_per_m3} step="0.001" onChange={(v) => setWarmwater((s) => ({ ...s, heizenergie_per_m3: v }))} />
          <Num label="Prepay (€/month)" value={warmwater.prepay_monthly} onChange={(v) => setWarmwater((s) => ({ ...s, prepay_monthly: v }))} />
        </FieldRow>
        <CalcPreview label="Warmwasser" result={calcResult.warmwater} />
      </SectionCard>

      {/* ── Heizung ── */}
      <SectionCard id="heizung" title="🌡️ Heizkosten (Heating)" enabled={useHeizung} onToggle={setUseHeizung}>
        <FieldRow>
          <DateF label="Bill start" value={heizung.bill_start} onChange={(v) => setHeizung((s) => ({ ...s, bill_start: v }))} />
          <DateF label="Bill end" value={heizung.bill_end} onChange={(v) => setHeizung((s) => ({ ...s, bill_end: v }))} />
        </FieldRow>
        {hzMeters.map((m, i) => (
          <div key={i} className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end border-b border-border pb-3">
            <Num label="Start" value={m.start} step="0.001" onChange={(v) => setHzMeters((ms) => ms.map((mm, ii) => ii === i ? { ...mm, start: v } : mm))} />
            <Num label="End" value={m.end} step="0.001" onChange={(v) => setHzMeters((ms) => ms.map((mm, ii) => ii === i ? { ...mm, end: v } : mm))} />
            <Num label="€/kWh" value={m.unit_price} step="0.0001" onChange={(v) => setHzMeters((ms) => ms.map((mm, ii) => ii === i ? { ...mm, unit_price: v } : mm))} />
            <Num label="Conv. factor" value={m.conversion_factor} step="0.0001" onChange={(v) => setHzMeters((ms) => ms.map((mm, ii) => ii === i ? { ...mm, conversion_factor: v } : mm))} />
            {hzMeters.length > 1 && <Button variant="ghost" size="icon" onClick={() => setHzMeters((ms) => ms.filter((_, ii) => ii !== i))} className="mb-0.5"><Trash2 className="size-4 text-destructive" /></Button>}
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setHzMeters((ms) => [...ms, { start: 0, end: 0, unit_price: 0, unit_label: "Einheiten", conversion_factor: 1.0 }])}>
          <Plus className="size-4 mr-1" /> Add meter
        </Button>
        <Num label="Prepay (€/month)" value={heizung.prepay_monthly} onChange={(v) => setHeizung((s) => ({ ...s, prepay_monthly: v }))} />
        <CalcPreview label="Heizkosten" result={calcResult.heizung} />
      </SectionCard>

      {/* ── Betriebskosten ── */}
      <SectionCard id="bk" title="🏢 Betriebskosten (Operating Costs)" enabled={useBK} onToggle={setUseBK}>
        <FieldRow>
          <Num label="Total cost (€)" value={bk.cost_flat} onChange={(v) => setBk((s) => ({ ...s, cost_flat: v }))} />
          <Num label="Tenants" value={bk.tenants} step="1" min="1" onChange={(v) => setBk((s) => ({ ...s, tenants: v }))} />
          <Num label="Months" value={bk.months} step="1" min="1" onChange={(v) => setBk((s) => ({ ...s, months: v }))} />
          <Num label="Limit €/month/tenant" value={bk.limit_per_month} onChange={(v) => setBk((s) => ({ ...s, limit_per_month: v }))} />
        </FieldRow>
        <FieldRow>
          <DateF label="Period start" value={bk.bk_start} onChange={(v) => setBk((s) => ({ ...s, bk_start: v }))} />
          <DateF label="Period end" value={bk.bk_end} onChange={(v) => setBk((s) => ({ ...s, bk_end: v }))} />
        </FieldRow>
        {calcResult.bk && (
          <div className="rounded-md bg-primary/10 border border-primary/20 p-3 text-sm space-y-1">
            <p className="font-medium text-primary text-xs uppercase tracking-wide">Betriebskosten — Preview</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <span>Period cost: <b>€ {calcResult.bk.period_cost?.toFixed(2)}</b></span>
              <span>Limit: <b>€ {calcResult.bk.limit_period?.toFixed(2)}</b></span>
              <span className={calcResult.bk.nach > 0 ? "text-destructive font-bold" : "text-emerald-400 font-bold"}>
                Nachzahlung: € {calcResult.bk.nach?.toFixed(2)}
              </span>
            </div>
          </div>
        )}
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
          <div className="flex gap-2 items-center">
            <Input className="h-9 w-40 text-sm" placeholder="Profile name"
              value={profileLabel} onChange={(e) => setProfileLabel(e.target.value)} />
            <Button variant="outline" onClick={saveProfile} disabled={!profileLabel}>
              <Save className="size-4 mr-1" /> Save Profile
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
