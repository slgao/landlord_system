"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Contract, GasMeter, StromMeter, MeterReading, BillingProfile } from "@/lib/types";
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

// ── Tarifwechsel (price change inside a billing period) ───────────────────────
// When the Strom tariff changes mid-period, each price period is billed with its
// own Arbeits-/Grundpreis. That needs the meter reading on the change date.
// StromGVV requires it to be determined "zeitanteilig" when nobody read the meter
// that day — i.e. linear interpolation over the elapsed days, which is exactly
// what Vattenfall's rechnerische Zwischenablesung does. A real value always wins:
// enter the reading (Selbstablesung, or the figure printed on the provider's
// invoice) on the change row and no interpolation happens at that boundary.

function addDays(isoStr: string, n: number) {
  return new Date(new Date(isoStr).getTime() + n * 86_400_000).toISOString().split("T")[0];
}
function dayDiff(a: string, b: string) {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);
}

// A reading we actually have, as an interpolation anchor.
type Anchor = { day: number; value: number; src: "bill" | "reading" | "manual" };

function fmtDate(isoStr: string) { return isoStr.split("-").reverse().join("."); }

// A change row carries its own prices and, optionally, the readings it is
// interpolated from: `reading` is the exact stand on the change date (no
// interpolation at all), while prev_/next_ are the nearest readings before and
// after it — the two the provider itself would bracket the date with.
const defTarif = (from = "") => ({
  from, arbeitspreis: 0, grundpreis_monthly: 0, reading: "" as number | "",
  prev_date: "", prev_reading: "" as number | "",
  next_date: "", next_reading: "" as number | "",
});

// Valid change rows: dated strictly inside the billing period, in date order.
function tarifChanges(b: any) {
  if (!b || b.mode !== "meter" || !b.bill_start || !b.bill_end) return [];
  return (b.tarife || [])
    .filter((t: any) => t.from && dayDiff(b.bill_start, t.from) > 0 && dayDiff(t.from, b.bill_end) >= 0)
    .slice()
    .sort((x: any, y: any) => (x.from < y.from ? -1 : x.from > y.from ? 1 : 0));
}

const isNum = (v: any) => v !== "" && v !== null && v !== undefined && !isNaN(Number(v));
const numOrBlank = (v: any): number | "" => (isNum(v) ? Number(v) : "");

// Every reading we can anchor on, in "days elapsed since bill_start" order.
// Precedence at the same day: a value typed on the tariff row beats a stored
// Zwischenablesung, which beats nothing. The billing's own start/end readings
// own day 0 and the last day, so a stored reading cannot silently move them.
function buildAnchors(b: any, changes: any[], cuts: number[], total: number,
                      readings: { date: string; value: number }[]): Anchor[] {
  const m = new Map<number, Anchor>();
  m.set(0, { day: 0, value: Number(b.start_kwh) || 0, src: "bill" });
  m.set(total, { day: total, value: Number(b.end_kwh) || 0, src: "bill" });
  // billDays is inclusive of both endpoints, so the end reading belongs to day
  // `total` (the end of bill_end), not to dayDiff(bill_start, bill_end). Map a
  // reading dated bill_end onto that day, or it lands one day early and drags
  // the interpolation with it.
  const dayOf = (date: string) => (date === b.bill_end ? total : dayDiff(b.bill_start, date));
  for (const r of readings || []) {
    const d = dayOf(r.date);
    if (d > 0 && d < total && isNum(r.value)) m.set(d, { day: d, value: Number(r.value), src: "reading" });
  }
  changes.forEach((t: any, i: number) => {
    const cut = cuts[i];
    // The readings typed on the change row itself. They may sit outside the
    // billing period (the nearest Ablesung before it often does) — that is fine,
    // it only widens the bracket. Days 0 and `total` stay owned by the billing's
    // own start/end readings, so a typed anchor can never move them. A "before"
    // reading that is not actually before the change date is ignored rather than
    // silently used as an anchor somewhere else.
    const side = (date: string, value: any, ok: (d: number) => boolean) => {
      if (!date || !isNum(value)) return;
      const d = dayOf(date);
      if (d !== 0 && d !== total && ok(d)) m.set(d, { day: d, value: Number(value), src: "manual" });
    };
    side(t.prev_date, t.prev_reading, (d) => d < cut);
    side(t.next_date, t.next_reading, (d) => d > cut);
    if (isNum(t.reading)) m.set(cut, { day: cut, value: Number(t.reading), src: "manual" });
  });
  const out = [...m.values()].sort((x, y) => x.day - y.day);
  // A meter cannot run backwards; drop anything that would make it (a typo, or a
  // reading left over from a replaced meter) rather than interpolate nonsense.
  return out.filter((a, i) => i === 0 || a.value >= out[i - 1].value);
}

// Value at `day`: the anchor sitting on it, or a linear interpolation between the
// two nearest ones — which is the zeitanteilige Aufteilung StromGVV asks for, and
// what the provider computes when nobody read the meter that day.
function readingAt(anchors: Anchor[], day: number, dateOf: (d: number) => string) {
  const hit = anchors.find((a) => a.day === day);
  if (hit) {
    // A stored Zwischenablesung landing exactly on the change date needs no
    // interpolation at all — say where it came from.
    const n = hit.src === "reading" ? `Ablesung vom ${fmtDate(dateOf(hit.day))}` : "";
    return { value: hit.value, estimated: false, note: n, noteShort: n };
  }
  if (anchors.length < 2)
    return { value: anchors[0]?.value ?? 0, estimated: true, note: "", noteShort: "" };
  let lo = anchors[0], hi = anchors[anchors.length - 1];
  for (let i = 0; i < anchors.length - 1; i++) {
    if (day >= anchors[i].day && day <= anchors[i + 1].day) { lo = anchors[i]; hi = anchors[i + 1]; break; }
  }
  const span = hi.day - lo.day;
  const value = span === 0 ? hi.value : lo.value + ((hi.value - lo.value) * (day - lo.day)) / span;
  const d0 = fmtDate(dateOf(lo.day)), d1 = fmtDate(dateOf(hi.day));
  return {
    value, estimated: true,
    note: `zeitanteilig aus ${d0} (${lo.value} kWh) und ${d1} (${hi.value} kWh)`,
    noteShort: `zeitanteilig aus ${d0} / ${d1}`,
  };
}

// Split one metered billing into one sub-billing per price period. Each carries
// its own dates, readings and prices, so the existing "several billings per
// utility" machinery prices, prorates and prints them without further changes.
function tariffSegments(b: any, readings: { date: string; value: number }[] = []): any[] {
  const changes = tarifChanges(b);
  if (changes.length === 0) return [b];

  const total = dayDiff(b.bill_start, b.bill_end) + 1;   // inclusive length in days
  const cuts = changes.map((t: any) => dayDiff(b.bill_start, t.from));
  const bounds = [0, ...cuts, total];
  const anchors = buildAnchors(b, changes, cuts, total, readings);
  // Day `total` is the end reading, which belongs to the last day of the period.
  const dateOf = (d: number) => (d === total ? b.bill_end : addDays(b.bill_start, d));

  const es = b.eff_start || b.bill_start, ee = b.eff_end || b.bill_end;
  const r2 = (x: number) => Math.round(x * 100) / 100;
  const nSeg = bounds.length - 1;
  const segs: any[] = [];
  for (let i = 0; i < nSeg; i++) {
    const s0 = bounds[i], s1 = bounds[i + 1];
    const segStart = addDays(b.bill_start, s0);
    const segEnd = i === nSeg - 1 ? b.bill_end : addDays(b.bill_start, s1 - 1);
    // Clip the tenant's living period to this price period; skip periods they
    // were not there for (e.g. moved in after the change).
    const cs = es > segStart ? es : segStart;
    const ce = ee < segEnd ? ee : segEnd;
    if (ce < cs) continue;
    const tar = i === 0 ? b : changes[i - 1];
    const a0 = readingAt(anchors, s0, dateOf);
    const a1 = readingAt(anchors, s1, dateOf);
    segs.push({
      ...b,
      bill_start: segStart, bill_end: segEnd,
      eff_start: cs, eff_end: ce,
      start_kwh: i === 0 ? Number(b.start_kwh) || 0 : r2(a0.value),
      end_kwh: i === nSeg - 1 ? Number(b.end_kwh) || 0 : r2(a1.value),
      arbeitspreis: Number(tar.arbeitspreis) || 0,
      grundpreis_monthly: Number(tar.grundpreis_monthly) || 0,
      tarife: [],
      _tseg: i,
      _tariff_label: `Tarifzeitraum ${i + 1} von ${nSeg}`,
      _start_estimated: i > 0 && a0.estimated,
      _end_estimated: i < nSeg - 1 && a1.estimated,
      _start_note: i > 0 ? a0.note : "",
      _end_note: i < nSeg - 1 ? a1.note : "",
      _start_note_pdf: i > 0 ? a0.noteShort : "",
      _end_note_pdf: i < nSeg - 1 ? a1.noteShort : "",
    });
  }
  return segs.length ? segs : [b];
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
    // Ihr Zeitraum (tenant's living period) — auto-filled from the contract ∩ bill
    // period, editable. Lets a tenancy spanning several contracts (e.g. a rent
    // raise via Nachtrag) be billed over its true continuous living period.
    eff_start: "", eff_end: "",
    prepay_monthly: 0, is_pauschale: false, cost_flat: 0,
  };
}

// Fill each billing's living period (eff_start/eff_end) from the contract ∩ bill
// period, but only where the user hasn't set it yet — editable afterwards.
// `sField`/`eField` name the billing-period fields (bill_* for metered, bk_* for BK).
function fillEff(arr: any[], sField: string, eField: string, cStart?: string, cEnd?: string) {
  let changed = false;
  const next = arr.map((b) => {
    if (b.eff_start && b.eff_end) return b;
    const eff = clampPeriod(b[sField], b[eField], cStart, cEnd);
    changed = true;
    return { ...b, eff_start: b.eff_start || eff.start, eff_end: b.eff_end || eff.end };
  });
  return changed ? next : arr;
}
const defStrom = () => ({ ...baseBilling(), start_kwh: 0, end_kwh: 0, arbeitspreis: 0, grundpreis_monthly: 0, tarife: [] as any[] });
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
// legacy field aliases) into an array of billing entries matching the default.
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
    if (Array.isArray(base.tarife)) {
      out.tarife = (Array.isArray(s.tarife) ? s.tarife : []).map((t: any) => ({
        from: t.from || "",
        arbeitspreis: Number(t.arbeitspreis) || 0,
        grundpreis_monthly: Number(t.grundpreis_monthly) || 0,
        reading: numOrBlank(t.reading),
        prev_date: t.prev_date || "",
        prev_reading: numOrBlank(t.prev_reading),
        next_date: t.next_date || "",
        next_reading: numOrBlank(t.next_reading),
      }));
    }
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

// Optional numeric field: empty means "not known" (the caller interpolates).
function NumOpt({ label, value, onChange, step = "0.01", placeholder = "" }: {
  label: string; value: number | ""; onChange: (v: number | "") => void; step?: string; placeholder?: string;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input type="number" step={step} min="0" className="h-8 text-sm" placeholder={placeholder}
        value={value === "" || value === null || value === undefined ? "" : value}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
    </div>
  );
}

// A bracketing reading that does not actually bracket the change date is
// ignored by buildAnchors; say so rather than letting it look effective.
function bracketWarning(t: any): string {
  if (!t.from) return "";
  const bad: string[] = [];
  if (t.prev_date && isNum(t.prev_reading) && t.prev_date >= t.from)
    bad.push("„Ablesung davor“ is not before the change date — dropped");
  if (t.next_date && isNum(t.next_reading) && t.next_date <= t.from)
    bad.push("„Ablesung danach“ is not after the change date — dropped");
  if (isNum(t.prev_reading) && isNum(t.next_reading) && Number(t.next_reading) < Number(t.prev_reading))
    bad.push("„Stand danach“ is lower than „Stand davor“ — a meter cannot run backwards, so the lower one is dropped");
  return bad.length ? `${bad.join(". ")}.` : "";
}

// Tarifwechsel editor — only meaningful for a meter-based billing, so it is
// rendered inside BillingShell's `children` (which the "sum" mode replaces).
// Each row is a price change effective from a date inside the billing period;
// the billing is then split into one sub-billing per price period.
function TariffSplit({ b, anchors, onChange }: {
  b: any; anchors: { date: string; value: number }[]; onChange: (tarife: any[]) => void;
}) {
  const list: any[] = b.tarife || [];
  const segs = tariffSegments(b, anchors);
  const inPeriod = anchors.filter((a) => a.date > b.bill_start && a.date < b.bill_end);
  const upd = (i: number, patch: any) => onChange(list.map((t, j) => (j === i ? { ...t, ...patch } : t)));

  return (
    <div className="rounded-md border border-dashed border-border/80 p-3 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Label className="text-xs font-semibold">Tarifwechsel — price change inside this billing period</Label>
          <p className="text-xs text-muted-foreground">
            Each price period is billed with its own tariff. The stand on the change day is taken
            from the first of these that is filled in: the <b>Zählerstand am Wechseltag</b>, a
            zeitanteilige interpolation between the <b>two nearest readings</b> you enter around it,
            the stored Zwischenablesungen of this flat&apos;s Stromzähler, or — last resort — the
            start/end readings above, which span the whole period.
          </p>
          <div className="text-xs">
            <span className="font-medium">Stored Zwischenablesungen in this period: </span>
            {inPeriod.length > 0
              ? <span className="text-muted-foreground">
                  {inPeriod.map((a) => `${fmtDate(a.date)} · ${a.value} kWh`).join("   ·   ")}
                </span>
              : <span className="text-muted-foreground">
                  none — enter the two nearest readings on the change row below, or add
                  Zwischenablesungen under Meter Readings.
                </span>}
          </div>
        </div>
        <Button variant="outline" size="sm" className="shrink-0"
          onClick={() => onChange([...list, defTarif()])}>
          <Plus className="size-4 mr-1" /> Tarifwechsel
        </Button>
      </div>
      {list.map((t, i) => (
        <div key={i} className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">New tariff valid from…</span>
            <Button variant="ghost" size="icon" className="size-7"
              onClick={() => onChange(list.filter((_, j) => j !== i))}>
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
          <FieldRow>
            <DateF label="Valid from" value={t.from} onChange={(v) => upd(i, { from: v })} />
            <Num label="Arbeitspreis (€/kWh)" value={t.arbeitspreis} step="0.0001"
              onChange={(v) => upd(i, { arbeitspreis: v })} />
            <Num label="Grundpreis (€/month)" value={t.grundpreis_monthly}
              onChange={(v) => upd(i, { grundpreis_monthly: v })} />
            <NumOpt label="Zählerstand am Wechseltag (optional)" value={t.reading}
              placeholder="interpolated" onChange={(v) => upd(i, { reading: v })} />
          </FieldRow>
          {/* Only meaningful while the stand on the change day is unknown — with
              an exact reading there is nothing left to interpolate. */}
          {!isNum(t.reading) && (
            <div className="rounded-md bg-muted/30 border border-border/60 p-2 space-y-1">
              <p className="text-xs text-muted-foreground">
                Nearest readings around {t.from ? fmtDate(t.from) : "the change date"} — the stand on
                the change day is interpolated between these two. A nearer reading always wins, so
                one lying outside the billing period has no effect — the start/end readings above are
                closer. Leave empty to fall back to stored Zwischenablesungen, then to those endpoints.
              </p>
              <FieldRow>
                <DateF label="Ablesung davor — Datum" value={t.prev_date}
                  onChange={(v) => upd(i, { prev_date: v })} />
                <NumOpt label="Stand davor (kWh)" value={t.prev_reading}
                  onChange={(v) => upd(i, { prev_reading: v })} />
                <DateF label="Ablesung danach — Datum" value={t.next_date}
                  onChange={(v) => upd(i, { next_date: v })} />
                <NumOpt label="Stand danach (kWh)" value={t.next_reading}
                  onChange={(v) => upd(i, { next_reading: v })} />
              </FieldRow>
              {bracketWarning(t) && <p className="text-xs text-destructive">{bracketWarning(t)}</p>}
            </div>
          )}
        </div>
      ))}
      {segs.length > 1 && (
        <div className="rounded-md bg-muted/40 border border-border/70 p-2 space-y-1">
          <p className="text-xs font-medium">Resulting price periods</p>
          {segs.map((s, i) => (
            <div key={i} className="text-xs text-muted-foreground">
              <p>
                <b>{i + 1}.</b> {fmtPeriod(s.bill_start, s.bill_end)} · {billDays(s.bill_start, s.bill_end)} Tage ·{" "}
                {s.start_kwh.toFixed(2)} → {s.end_kwh.toFixed(2)} kWh ({(s.end_kwh - s.start_kwh).toFixed(2)} kWh) ·{" "}
                {s.arbeitspreis.toFixed(4)} €/kWh · {s.grundpreis_monthly.toFixed(2)} €/Mon
              </p>
              {/* Each internal boundary is the end of exactly one segment, so this
                  prints the provenance of every derived reading exactly once. */}
              {s._end_note && (
                <p className="pl-4 text-primary">
                  ↳ Zählerstand {s.end_kwh.toFixed(2)} kWh am {fmtDate(addDays(s.bill_end, 1))}: {s._end_note}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
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
          <span className={result.nach > 0 ? "text-destructive font-bold" : "text-primary font-bold"}>
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
      <div className="space-y-1">
        <Label className="text-xs text-muted-foreground">Abrechnungszeitraum (billing period)</Label>
        <FieldRow>
          <DateF label="Bill start" value={b.bill_start} onChange={(v) => set({ bill_start: v })} />
          <DateF label="Bill end" value={b.bill_end} onChange={(v) => set({ bill_end: v })} />
        </FieldRow>
      </div>
      <div className="space-y-1">
        <Label className="text-xs text-primary">Ihr Zeitraum (tenant&apos;s living period — from the contract, editable)</Label>
        <FieldRow>
          <DateF label="Start" value={b.eff_start} onChange={(v) => set({ eff_start: v })} />
          <DateF label="End" value={b.eff_end} onChange={(v) => set({ eff_end: v })} />
        </FieldRow>
        <p className="text-xs text-muted-foreground">
          = {b.eff_start && b.eff_end ? billDays(b.eff_start, b.eff_end) : "–"} Tage (used for proration)
        </p>
      </div>
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
  // Optional occupancy timeline (WG): spans where fewer/more people lived, e.g. a
  // vacant room. Applied to consumption utilities only. Empty = use numTenants.
  const [occTimeline, setOccTimeline] = useState<{ start: string; end: string; persons: number }[]>([]);
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

  // Append a new metered billing with its living period pre-filled from the contract.
  function addMeteredBilling(setter: React.Dispatch<React.SetStateAction<any[]>>, def: () => any) {
    setter((a) => {
      const nb = def();
      const eff = selected
        ? clampPeriod(nb.bill_start, nb.bill_end, selected.start_date, selected.end_date)
        : { start: "", end: "" };
      return [...a, { ...nb, eff_start: eff.start, eff_end: eff.end }];
    });
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

  // Stored Zwischenablesungen anchor the Tarifwechsel interpolation, so the
  // reading on a price-change date is derived from the two real readings around
  // it instead of from the billing's endpoints.
  const { data: stromMeters = [] } = useQuery<StromMeter[]>({
    queryKey: ["strom-meters-all"],
    queryFn: () => api.get("/api/meters/strom").then((r) => r.data),
  });
  const { data: stromReadings = [] } = useQuery<MeterReading[]>({
    queryKey: ["strom-readings-all"],
    queryFn: () => api.get("/api/meters/readings?meter_type=strom").then((r) => r.data),
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
  // sharing the same flat.
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

  // Occupancy timeline is contract-specific — clear it when the contract changes.
  useEffect(() => { setOccTimeline([]); }, [selected?.id]);

  // Changing the contract clears the "currently loaded profile" so Update can't
  // accidentally overwrite a different tenant's profile.
  useEffect(() => {
    setCurrentProfileId(null);
    setCurrentProfileLabel("");
    setDeductKaution(false);
  }, [selected?.id]);

  // Auto-fill each billing's "Ihr Zeitraum" (living period) from the contract ∩
  // billing period, only where the user hasn't set it yet. Editable afterwards.
  // Metered utilities key off bill_start/bill_end; Betriebskosten off bk_start/bk_end.
  useEffect(() => {
    if (!selected) return;
    const cs = selected.start_date, ce = selected.end_date;
    setStromB((a) => fillEff(a, "bill_start", "bill_end", cs, ce));
    setGasB((a) => fillEff(a, "bill_start", "bill_end", cs, ce));
    setWaterB((a) => fillEff(a, "bill_start", "bill_end", cs, ce));
    setWarmB((a) => fillEff(a, "bill_start", "bill_end", cs, ce));
    setHeizB((a) => fillEff(a, "bill_start", "bill_end", cs, ce));
    setBkB((a) => fillEff(a, "bk_start", "bk_end", cs, ce));
  }, [selected?.id]);

  // Keep the Betriebskosten per-billing tenant count in sync with the master
  // "Number of tenants" (auto-detected from occupancy or set manually), so BK is
  // divided by the same number of persons as the metered utilities.
  useEffect(() => {
    setBkB((arr) => (arr.every((b) => b.tenants === numTenants)
      ? arr : arr.map((b) => ({ ...b, tenants: numTenants }))));
  }, [numTenants]);

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

  // Readings of this apartment's Stromzähler, as interpolation anchors for one
  // billing period. A flat normally has a single Stromzähler; when it has more,
  // take the one with the most readings inside the period (ties → lowest id) so
  // readings from two different meters are never mixed into one curve.
  const stromAnchorsFor = (b: any) => {
    const ids = stromMeters.filter((m) => m.apartment_id === selected?.apartment_id).map((m) => m.id);
    if (ids.length === 0 || !b?.bill_start || !b?.bill_end) return [];
    const inPeriod = (r: MeterReading) => r.reading_date >= b.bill_start && r.reading_date <= b.bill_end;
    const mine = stromReadings.filter((r) => ids.includes(r.meter_id));
    const best = ids.slice().sort((x, y) => {
      const d = mine.filter((r) => r.meter_id === y && inPeriod(r)).length
              - mine.filter((r) => r.meter_id === x && inPeriod(r)).length;
      return d !== 0 ? d : x - y;
    })[0];
    return mine.filter((r) => r.meter_id === best)
               .map((r) => ({ date: r.reading_date, value: Number(r.reading) }));
  };

  // ── occupancy timeline → split each cost into sub-periods with an INTEGER
  //    person count, so every interval renders on its own (÷3 while everyone is
  //    there, ÷2 during a vacancy) and the parts sum. Reuses the existing
  //    "several billing periods per utility" machinery — no backend/PDF change.
  const occSegs = () => occTimeline.filter((s) => s.start && s.end && s.persons > 0);
  function occRuns(es: string, ee: string, base: number) {
    const occ = occSegs();
    const d0 = new Date(es), d1 = new Date(ee);
    if (occ.length === 0 || isNaN(+d0) || isNaN(+d1) || d1 < d0) return [{ start: es, end: ee, persons: base }];
    const iso = (d: Date) => d.toISOString().split("T")[0];
    const personsOn = (d: Date) => {
      for (const s of occ) if (d >= new Date(s.start) && d <= new Date(s.end)) return s.persons;
      return base;
    };
    const DAY = 86_400_000;
    const runs: { start: string; end: string; persons: number }[] = [];
    let runStart = new Date(d0), runP = personsOn(d0);
    for (let t = +d0 + DAY; t <= +d1; t += DAY) {
      const p = personsOn(new Date(t));
      if (p !== runP) { runs.push({ start: iso(runStart), end: iso(new Date(t - DAY)), persons: runP }); runStart = new Date(t); runP = p; }
    }
    runs.push({ start: iso(runStart), end: iso(d1), persons: runP });
    return runs;
  }
  const expandMetered = (list: any[]) => occSegs().length === 0 ? list : list.flatMap((b: any) => {
    const es = b.eff_start || b.bill_start, ee = b.eff_end || b.bill_end;
    if (!es || !ee) return [b];
    const base = b.num_tenants ?? numTenants;
    const runs = occRuns(es, ee, base);
    if (runs.length <= 1) return [b];
    return runs.map((r) => ({
      ...b, eff_start: r.start, eff_end: r.end, num_tenants: r.persons,
      // Cost is split by the persons present in this run, but the prepayment is a
      // fixed amount the tenant paid regardless of occupancy — keep it divided by
      // the ORIGINAL count. The backend divides prepay by num_tenants (= r.persons),
      // so pre-scale it here to cancel back to ÷base. _base_tenants/_prepay_base
      // carry the unscaled figure + original divisor for an honest PDF display.
      prepay_monthly: (b.prepay_monthly || 0) * r.persons / base,
      _base_tenants: base, _prepay_base: b.prepay_monthly || 0,
    }));
  });
  const expandBK = (list: any[]) => occSegs().length === 0 ? list : list.flatMap((b: any) => {
    const es = b.eff_start || b.bk_start, ee = b.eff_end || b.bk_end;
    if (!es || !ee) return [b];
    const base = b.tenants ?? numTenants;
    const runs = occRuns(es, ee, base);
    if (runs.length <= 1) return [b];
    // BK is month-based. When every split point lands on a month boundary (a room
    // re-let on the 1st — the common case) the runs' whole months already sum to
    // the period's months, so keep clean integers. Only when a boundary is mid-
    // month (no honest whole-month answer) fall back to day-proportional shares so
    // the runs still sum exactly (last run absorbs the rounding remainder) instead
    // of double-counting the boundary month.
    const totMonths = monthsBetween(es, ee), totDays = billDays(es, ee);
    const intMonths = runs.map((r) => monthsBetween(r.start, r.end));
    const aligned = intMonths.reduce((a, b) => a + b, 0) === totMonths;
    const r2 = (x: number) => Math.round(x * 100) / 100;
    let acc = 0;
    return runs.map((r, i) => {
      const m = aligned ? intMonths[i]
        : (i === runs.length - 1 ? r2(totMonths - acc) : r2(totMonths * billDays(r.start, r.end) / totDays));
      acc += m;
      return {
        ...b, eff_start: r.start, eff_end: r.end, tenants: r.persons, _occ_months: m,
        // BK prepay limit stays divided by the ORIGINAL count (see expandMetered).
        limit_per_month: (b.limit_per_month || 0) * r.persons / base,
        _base_tenants: base, _limit_base: b.limit_per_month || 0,
      };
    });
  });

  // ── expansion pipeline ──
  // Tag every form billing with its index so the expanded rows can be folded back
  // onto it no matter which splits produced them. Strom expands on two axes:
  // price periods (Tarifwechsel) first, then occupancy runs inside each.
  const withSrc = (list: any[]) => list.map((b, i) => ({ ...b, _src: i }));
  const expandTariff = (list: any[]) => list.flatMap((b: any) => tariffSegments(b, stromAnchorsFor(b)));
  const expStrom = () => expandMetered(expandTariff(withSrc(stromB)));
  const expGas = () => expandMetered(withSrc(gasB));
  const expWater = () => expandMetered(withSrc(waterB));
  const expWarm = () => expandMetered(withSrc(warmB));
  const expHeiz = () => expandMetered(withSrc(heizB));
  const expBk = () => expandBK(withSrc(bkB));

  // The calc returns one result per expanded interval; fold them back to one per
  // form billing so the on-screen preview total matches the PDF. The PDF itself
  // keeps the per-interval breakdown.
  //
  // Two stages, because the two axes fold differently: occupancy runs inside one
  // price period all carry the SAME meter readings (only the divisor changes), so
  // only money may be summed there. Price periods carry their own readings, so
  // their consumption sums too.
  const _ADD_MONEY = ["cost_tenant", "prepay", "nach", "period_cost", "limit_period"];
  const _ADD_USAGE = ["verbrauch", "verbrauch_tenant", "arbeitskosten", "grundkosten"];
  const foldResults = (slice: any[], fields: string[]) => {
    if (slice.length <= 1) return slice[0];
    const base = { ...slice[0] };
    for (const f of fields)
      if (slice.some((r) => r && r[f] != null))
        base[f] = Math.round(slice.reduce((s, r) => s + (r?.[f] || 0), 0) * 1000) / 1000;
    return base;
  };
  // Rows come out of the pipeline in source order, so every group is contiguous.
  const foldRows = (rows: any[], results: any[]) => {
    if (!results) return results;
    const out: any[] = [];
    let i = 0;
    while (i < rows.length) {
      const src = rows[i]._src;
      const parts: any[] = [];
      let j = i;
      while (j < rows.length && rows[j]._src === src) {
        const seg = rows[j]._tseg;
        let k = j;
        while (k < rows.length && rows[k]._src === src && rows[k]._tseg === seg) k++;
        parts.push(foldResults(results.slice(j, k), _ADD_MONEY));
        j = k;
      }
      out.push(parts.length <= 1 ? parts[0] : foldResults(parts, [..._ADD_MONEY, ..._ADD_USAGE]));
      i = j;
    }
    return out;
  };
  function foldPreview(calc: any) {
    return {
      ...calc,
      strom: foldRows(expStrom(), calc.strom), gas: foldRows(expGas(), calc.gas),
      water: foldRows(expWater(), calc.water), warmwater: foldRows(expWarm(), calc.warmwater),
      heizung: foldRows(expHeiz(), calc.heizung), bk: foldRows(expBk(), calc.bk),
    };
  }

  // ── payload builders ──
  function buildCalcPayload() {
    const cs = selected?.start_date || "";
    const ce = selected?.end_date;
    // Prefer the (editable) living period; fall back to contract ∩ bill period.
    const effDays = (b: any) => (b.eff_start && b.eff_end)
      ? billDays(b.eff_start, b.eff_end)
      : effectiveDays(b.bill_start, b.bill_end, cs, ce);
    const mk = (b: any) => ({
      ...b, num_tenants: b.num_tenants ?? numTenants,
      bill_days: billDays(b.bill_start, b.bill_end),
      eff_days: effDays(b),
    });
    const p: any = {};
    if (useStrom) p.strom = expStrom().map(mk);
    if (useGas) p.gas = expGas().map(mk);
    if (useWater) p.water = expWater().map(mk);
    if (useWarmwater) p.warmwater = expWarm().map((b: any) => ({ ...mk(b), meters: b.meters }));
    if (useHeizung) p.heizung = expHeiz().map((b: any) => ({ ...mk(b), meters: b.meters }));
    if (useBK) p.bk = expBk().map((b: any) => ({
      cost_flat: b.cost_flat, tenants: b.tenants,
      bk_start: b.bk_start, bk_end: b.bk_end, limit_per_month: b.limit_per_month,
      // effective living months drive the proration on the backend; occupancy runs
      // carry a day-proportional month share (_occ_months) so they sum correctly.
      months: b._occ_months ?? monthsBetween(b.eff_start || b.bk_start, b.eff_end || b.bk_end),
    }));
    return p;
  }

  function buildPdfPayload(calc: any) {
    const cs = selected?.start_date || "";
    const ce = selected?.end_date;
    const common = (b: any, c: any) => {
      const hasEff = b.eff_start && b.eff_end;
      const effS = hasEff ? b.eff_start : b.bill_start;
      const effE = hasEff ? b.eff_end : b.bill_end;
      return {
        // Abrechnungszeitraum = full bill period; Ihr Zeitraum = living period.
        bill_period: fmtPeriod(b.bill_start, b.bill_end),
        bill_days: billDays(b.bill_start, b.bill_end),
        period: fmtPeriod(effS, effE),
        days: hasEff ? billDays(effS, effE) : effectiveDays(b.bill_start, b.bill_end, cs, ce),
        // Integer person count for this sub-period (from the occupancy split, or
        // the flat's count when no timeline is set).
        num_tenants: b.num_tenants ?? numTenants,
        // Prepayment shown unscaled and divided by the original count (the tenant's
        // fixed prepayment) — the result still equals c.prepay. Defaults to the
        // cost divisor when there's no occupancy split.
        monthly_limit: b._prepay_base ?? b.prepay_monthly,
        prepay_tenants: b._base_tenants ?? (b.num_tenants ?? numTenants),
        cost: c.cost_tenant, limit: c.prepay, is_pauschale: b.is_pauschale, mode: b.mode,
        // Tarifwechsel: label the price period and flag interpolated readings, so
        // the tenant can see which Zählerstand was measured and which was computed.
        tariff_label: b._tariff_label, start_estimated: !!b._start_estimated,
        end_estimated: !!b._end_estimated,
        start_note: b._start_note_pdf || "", end_note: b._end_note_pdf || "",
      };
    };
    const zip = (list: any[], res: any[]) =>
      list.map((b, i) => ({ ...(res?.[i] || {}), ...b, ...common(b, res?.[i] || {}) }));
    const payload: any = {};
    // Expand the same way as the calc payload so results line up 1:1.
    if (useStrom && calc.strom) payload.strom = zip(expStrom(), calc.strom);
    if (useGas && calc.gas) payload.gas = zip(expGas(), calc.gas);
    if (useWater && calc.water) payload.water = zip(expWater(), calc.water);
    if (useWarmwater && calc.warmwater) payload.warmwater = zip(expWarm(), calc.warmwater);
    if (useHeizung && calc.heizung) payload.heizung = zip(expHeiz(), calc.heizung);
    if (useBK && calc.bk) {
      // Map each BK billing's form/calc fields onto the exact keys invoice_pdf expects.
      // Abrechnungszeitraum = full bill period; Ihr Zeitraum = tenant's living period.
      payload.bk = expBk().map((b, i) => {
        const c = calc.bk?.[i] || {};
        const effS = b.eff_start || b.bk_start;
        const effE = b.eff_end || b.bk_end;
        return {
          ...c,
          num_tenants: b.tenants,
          total_cost: b.cost_flat,
          // Unscaled prepay limit + original divisor for an honest display; the
          // result (c.limit_period) is unchanged. Defaults when no occupancy split.
          monthly_limit: b._limit_base ?? b.limit_per_month,
          prepay_tenants: b._base_tenants ?? b.tenants,
          bill_period: fmtPeriod(b.bk_start, b.bk_end),
          num_months: monthsBetween(b.bk_start, b.bk_end),
          period: fmtPeriod(effS, effE),
          months: b._occ_months ?? monthsBetween(effS, effE),
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
      setCalcResult(foldPreview(res.data));
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
          setCalcResult(foldPreview(res.data));
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

    // ── Betriebskosten — list (handles legacy single object + int aliases) ──
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

          {selected && (
            <div className="rounded-md border border-border p-3 space-y-2">
              <div>
                <p className="text-xs font-medium">Occupancy over time (optional)</p>
                <p className="text-[11px] text-muted-foreground">
                  WG only: if a room was vacant part of the period, add the span and how many
                  persons actually lived there. Every cost — consumption (Strom/Gas/Wasser/Heizung)
                  <b> and Betriebskosten</b> — is then split among the residents present each day;
                  days you don&apos;t list use the fixed count above. Your fixed prepayment stays
                  divided by the full tenant count.
                </p>
              </div>
              {occTimeline.map((seg, i) => (
                <div key={i} className="flex items-end gap-2">
                  <DateF label="From" value={seg.start}
                    onChange={(v) => setOccTimeline((a) => a.map((s, j) => (j === i ? { ...s, start: v } : s)))} />
                  <DateF label="To" value={seg.end}
                    onChange={(v) => setOccTimeline((a) => a.map((s, j) => (j === i ? { ...s, end: v } : s)))} />
                  <div className="w-24">
                    <Num label="Persons" value={seg.persons} step="1" min="1"
                      onChange={(v) => setOccTimeline((a) => a.map((s, j) => (j === i ? { ...s, persons: v } : s)))} />
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => setOccTimeline((a) => a.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                </div>
              ))}
              <Button variant="outline" size="sm"
                onClick={() => setOccTimeline((a) => [...a, { start: "", end: "", persons: Math.max(1, numTenants - 1) }])}>
                <Plus className="size-4 mr-1" /> Add vacancy / occupancy period
              </Button>
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
            <TariffSplit b={b} anchors={stromAnchorsFor(b)}
              onChange={(tarife) => updateAt(setStromB, i, { tarife })} />
          </BillingShell>
        ))}
        <Button variant="outline" size="sm" onClick={() => addMeteredBilling(setStromB, defStrom)}>
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
        <Button variant="outline" size="sm" onClick={() => addMeteredBilling(setGasB, defGas)}>
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
        <Button variant="outline" size="sm" onClick={() => addMeteredBilling(setWaterB, defWater)}>
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
        <Button variant="outline" size="sm" onClick={() => addMeteredBilling(setWarmB, defWarm)}>
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
        <Button variant="outline" size="sm" onClick={() => addMeteredBilling(setHeizB, defHeiz)}>
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
                    <span className={r.nach > 0 ? "text-destructive font-bold" : "text-primary font-bold"}>
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
