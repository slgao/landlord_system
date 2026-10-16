"use client";

// What a meter's consumption costs over a period, at a tariff you type in.
//
// The consumption comes from the meter's own readings; a bound nobody read is
// interpolated between the surrounding readings, or carried from the average
// daily rate when it lies outside them. The dialog says which, because that is
// the difference between a calculation and an estimate.

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { MeterReading, MeterType } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";

export interface CostEstimate {
  readings: number;
  source?: "no_readings";
  start_value?: number;
  start_source?: Source;
  end_value?: number;
  end_source?: Source;
  consumption?: number;
  billed_units?: number;
  conversion_factor?: number;
  days?: number;
  arbeitskosten?: number;
  grundkosten?: number;
  total?: number;
  per_month?: number;
  estimated?: boolean;
}

type Source = "measured" | "interpolated" | "extrapolated";

const SOURCE_NOTE: Record<Source, string> = {
  measured: "read on the day",
  interpolated: "between two readings",
  extrapolated: "beyond the readings",
};

// What the meter counts, and what the tariff is charged per.
const UNITS: Record<MeterType, { metered: string; billed: string }> = {
  strom: { metered: "kWh", billed: "kWh" },
  gas: { metered: "m³", billed: "kWh" },
  wasser: { metered: "m³", billed: "m³" },
  heizung: { metered: "units", billed: "units" },
};

const eur = (n: number) =>
  `${n.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
const num = (n: number, digits = 2) =>
  n.toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });

function monthsAgo(iso: string, months: number) {
  const [y, m, d] = iso.split("-").map(Number);
  const t = new Date(y, m - 1 - months, d);
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
}

/** The tariff last used for this meter, so it is typed once, not every time. */
function rememberedTariff(key: string) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as { arbeitspreis: string; grundpreis: string }) : null;
  } catch {
    return null;
  }
}

export function CostEstimateDialog({
  open, onOpenChange, type, meter, readings,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  type: MeterType;
  meter: { id: number; serial_number?: string | null; description?: string | null;
           z_zahl?: number; brennwert?: number; unit_price?: number;
           conversion_factor?: number; unit_label?: string } | null;
  readings: MeterReading[];
}) {
  const units = UNITS[type];
  const unitLabel = type === "heizung" ? (meter?.unit_label || "units") : units.metered;
  const billedLabel = type === "heizung" ? (meter?.unit_label || "units") : units.billed;

  // Gas meters count m³ and are billed in kWh; heating meters carry their own
  // factor. Both come from the meter, and both stay editable.
  const meterFactor = useMemo(() => {
    if (!meter) return 1;
    if (type === "gas") return (meter.z_zahl ?? 1) * (meter.brennwert ?? 1);
    if (type === "heizung") return meter.conversion_factor ?? 1;
    return 1;
  }, [meter, type]);

  const dates = useMemo(
    () => readings.map((r) => r.reading_date).sort(),
    [readings],
  );
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [arbeitspreis, setArbeitspreis] = useState("");
  const [grundpreis, setGrundpreis] = useState("");
  const [factor, setFactor] = useState("1");
  const [result, setResult] = useState<CostEstimate | null>(null);
  const [busy, setBusy] = useState(false);

  const storeKey = meter ? `dachly.tariff.${type}.${meter.id}` : "";

  useEffect(() => {
    if (!open || !meter) return;
    const today = new Date().toISOString().slice(0, 10);
    setFrom(dates[0] || monthsAgo(today, 12));
    setTo(dates[dates.length - 1] || today);
    const saved = rememberedTariff(storeKey);
    setArbeitspreis(saved?.arbeitspreis ?? (type === "heizung" && meter.unit_price
      ? String(meter.unit_price) : ""));
    setGrundpreis(saved?.grundpreis ?? "");
    // 0.95 × 11.5 is 10.924999999999999 in binary floating point; nobody
    // wants to read that in a form field.
    setFactor(String(Math.round((meterFactor || 1) * 10000) / 10000));
    setResult(null);
  }, [open, meter, dates, storeKey, type, meterFactor]);

  const price = Number(arbeitspreis.replace(",", ".")) || 0;
  const base = Number(grundpreis.replace(",", ".")) || 0;
  const conv = Number(factor.replace(",", ".")) || 1;
  const valid = !!meter && !!from && !!to && to >= from;

  const run = useCallback(async () => {
    if (!valid || !meter) return;
    setBusy(true);
    try {
      const { data } = await api.post("/api/meters/cost-estimate", {
        meter_type: type, meter_id: meter.id, start_date: from, end_date: to,
        arbeitspreis: price, grundpreis_monthly: base, conversion_factor: conv,
      });
      setResult(data);
      try {
        localStorage.setItem(storeKey, JSON.stringify({ arbeitspreis, grundpreis }));
      } catch { /* a private window is no reason to fail the estimate */ }
    } catch (e) {
      toast.error(errorMessage(e, "Could not work out the cost"));
    } finally {
      setBusy(false);
    }
  }, [valid, meter, type, from, to, price, base, conv, arbeitspreis, grundpreis, storeKey]);

  // Recalculate shortly after typing stops, so the figures follow the inputs
  // without a request per keystroke.
  useEffect(() => {
    if (!open || !valid) return;
    const t = setTimeout(run, 450);
    return () => clearTimeout(t);
  }, [open, valid, run]);

  const quick = (months: number) => {
    const end = dates[dates.length - 1] || new Date().toISOString().slice(0, 10);
    setTo(end);
    setFrom(monthsAgo(end, months));
  };

  const noReadings = result?.source === "no_readings";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Estimate cost</DialogTitle>
        </DialogHeader>
        {meter && (
          <div className="space-y-4 py-1">
            <p className="text-sm text-muted-foreground">
              {meter.serial_number || "No serial"}
              {meter.description ? ` · ${meter.description}` : ""} · counts {unitLabel}
            </p>

            <div className="space-y-1.5">
              <Label>Period</Label>
              <div className="grid grid-cols-2 gap-3">
                <Input type="date" aria-label="From" value={from} onChange={(e) => setFrom(e.target.value)} />
                <Input type="date" aria-label="To" value={to} onChange={(e) => setTo(e.target.value)} />
              </div>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {([["Last 3 months", 3], ["Last 12 months", 12]] as const).map(([label, m]) => (
                  <button key={label} type="button" onClick={() => quick(m)}
                    className="text-xs rounded-full border border-border px-2.5 py-1 text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors">
                    {label}
                  </button>
                ))}
                {dates.length > 0 && (
                  <button type="button"
                    onClick={() => { setFrom(dates[0]); setTo(dates[dates.length - 1]); }}
                    className="text-xs rounded-full border border-border px-2.5 py-1 text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors">
                    All readings
                  </button>
                )}
              </div>
              {to < from && <p className="text-xs text-destructive">The end is before the start.</p>}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="ce-price">Arbeitspreis (€ per {billedLabel})</Label>
                <Input id="ce-price" inputMode="decimal" placeholder="0.3500" value={arbeitspreis}
                  onChange={(e) => setArbeitspreis(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ce-base">Grundpreis (€ per month)</Label>
                <Input id="ce-base" inputMode="decimal" placeholder="12.00" value={grundpreis}
                  onChange={(e) => setGrundpreis(e.target.value)} />
              </div>
            </div>

            {(type === "gas" || type === "heizung") && (
              <div className="space-y-1.5">
                <Label htmlFor="ce-factor">
                  {type === "gas" ? `${billedLabel} per m³ (Zustandszahl × Brennwert)` : "Conversion factor"}
                </Label>
                <Input id="ce-factor" inputMode="decimal" value={factor}
                  onChange={(e) => setFactor(e.target.value)} />
                <p className="text-xs text-muted-foreground">
                  From the meter; change it for a different bill.
                </p>
              </div>
            )}

            {/* The answer */}
            <div className="rounded-lg border border-border bg-muted/30 p-4">
              {noReadings ? (
                <p className="text-sm text-muted-foreground">
                  This meter has no readings yet — record two and the cost follows.
                </p>
              ) : !result ? (
                <p className="text-sm text-muted-foreground">{busy ? "Working it out…" : "Fill in the tariff."}</p>
              ) : (
                <>
                  <div className="flex items-end justify-between gap-3">
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">
                        Cost for {result.days} day{result.days === 1 ? "" : "s"}
                      </p>
                      <p className="text-3xl font-semibold tabular-nums mt-0.5">{eur(result.total ?? 0)}</p>
                    </div>
                    <p className="text-sm text-muted-foreground">≈ {eur(result.per_month ?? 0)}/month</p>
                  </div>
                  <div className="mt-3 space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Consumption {num(result.consumption ?? 0, 3)} {unitLabel}
                        {conv !== 1 && ` → ${num(result.billed_units ?? 0, 1)} ${billedLabel}`}
                      </span>
                      <span className="font-mono">{eur(result.arbeitskosten ?? 0)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Grundpreis {num(base)} €/month × {result.days} days
                      </span>
                      <span className="font-mono">{eur(result.grundkosten ?? 0)}</span>
                    </div>
                    <div className="flex justify-between border-t border-border pt-1 font-medium">
                      <span>Total</span>
                      <span className="font-mono">{eur(result.total ?? 0)}</span>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>
                      {num(result.start_value ?? 0, 1)} → {num(result.end_value ?? 0, 1)} {unitLabel}
                    </span>
                    {(["start_source", "end_source"] as const).map((k) => {
                      const src = result[k] as Source | undefined;
                      if (!src || src === "measured") return null;
                      return (
                        <Badge key={k} variant="secondary" className="text-[10px]">
                          {k === "start_source" ? "start" : "end"} {SOURCE_NOTE[src]}
                        </Badge>
                      );
                    })}
                  </div>
                  {result.estimated && (
                    <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                      A reading was derived rather than read, so this is an estimate. Record a
                      reading on the period&apos;s edges to make it exact.
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button onClick={run} disabled={!valid || busy}>{busy ? "Working…" : "Recalculate"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
