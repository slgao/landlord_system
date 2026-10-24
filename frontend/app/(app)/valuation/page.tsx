"use client";

// What the flats are worth, and what is actually yours of them.
//
// There is no real-time valuation of German property to be had. What there is,
// is official: Berlin publishes the Bodenrichtwert for every zone once a year
// under a licence that asks nothing in return, and the Gutachterausschuss
// derives comparable €/m² from the real purchase cases. This page keeps both,
// says which Stichtag each figure was official on, and never calls an estimate
// a valuation.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { LandValue, ValuationOverview, PropertyValuation } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { RefreshCw, Info } from "lucide-react";
import Link from "next/link";

const eur = (n: number) =>
  `${n.toLocaleString("de-DE", { maximumFractionDigits: 0 })} €`;
const num = (n: number, d = 0) =>
  n.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });

const MISSING_LABEL: Record<string, string> = {
  living_sqm: "living area",
  comparable_per_sqm: "comparable €/m²",
};

function Stat({ label, value, sub, tone }: {
  label: string; value: string; sub?: string; tone?: "good" | "warn";
}) {
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${
        tone === "good" ? "text-emerald-600 dark:text-emerald-400"
        : tone === "warn" ? "text-amber-700 dark:text-amber-400" : ""}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </Card>
  );
}

export default function ValuationPage() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<number | null>(null);

  const { data, isLoading } = useQuery<ValuationOverview>({
    queryKey: ["valuation-overview"],
    queryFn: () => api.get("/api/valuation/overview").then((r) => r.data),
  });

  // On demand, never on load: two requests to an external service, for a
  // number that changes once a year.
  const refresh = useMutation({
    mutationFn: (id: number) =>
      api.post(`/api/valuation/properties/${id}/land-value`).then((r) => r.data as LandValue),
    onMutate: (id) => setBusy(id),
    onSettled: () => setBusy(null),
    onSuccess: (lv) => {
      qc.invalidateQueries({ queryKey: ["valuation-overview"] });
      toast.success(
        `${lv.matched_address} — ${eur(lv.brw)}/m² as of ${lv.stichtag}`,
        lv.ambiguous
          ? { description: "Several addresses matched; check this is the right one." }
          : undefined,
      );
    },
    onError: (e) => toast.error(errorMessage(e, "Could not fetch the land value")),
  });

  const all = data?.properties ?? [];
  // Only the flats that are yours are valued. The rest are listed apart, so
  // they are visibly excluded rather than quietly absent.
  const rows = all.filter((p) => p.owned);
  const managed = all.filter((p) => !p.owned);
  const totals = data?.totals;
  const needInput = rows.filter((p) => p.missing.length > 0);
  const noLand = rows.filter((p) => p.brw == null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Valuation"
        description="What the flats are worth, the debt against them, and the equity left."
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          {/* The portfolio line. Withheld entirely while any flat has no
              value — a total that quietly omits them reads as the whole
              portfolio and understates it. */}
          {totals ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Portfolio value" value={eur(totals.value)}
                    sub={`${rows.length} flat${rows.length === 1 ? "" : "s"} you own`
                         + (totals.estimated ? ", includes estimates" : "")} />
              <Stat label="Debt" value={eur(totals.debt)} sub={`as of ${totals.as_of}`} />
              <Stat label="Equity" value={eur(totals.equity)} tone="good"
                    sub="value less what is still owed" />
              <Stat label="LTV" value={totals.ltv == null ? "—" : `${num(totals.ltv, 1)} %`}
                    sub="debt against value" />
            </div>
          ) : (
            <Card className="p-4">
              <p className="text-sm">
                No portfolio total yet — {needInput.length === 1 ? "one flat" : `${needInput.length} flats`}{" "}
                still {needInput.length === 1 ? "needs" : "need"} a figure.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                A total that left them out would read as the whole portfolio and understate it,
                so it is withheld until every flat has a value.
              </p>
            </Card>
          )}

          {needInput.length > 0 && (
            <Card className="p-4">
              <p className="text-sm font-medium">Needs a number before it can be valued</p>
              <ul className="mt-2 space-y-1 text-sm">
                {needInput.map((p) => (
                  <li key={p.property_id} className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{p.property_name}</span>
                    <span className="text-muted-foreground">
                      missing {p.missing.map((m) => MISSING_LABEL[m] ?? m).join(" and ")}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted-foreground">
                Set these on the{" "}
                <Link href="/properties" className="underline hover:no-underline">
                  Properties
                </Link>{" "}
                page. A WG&apos;s rooms do not add up to the flat&apos;s Wohnfläche, so it has
                to be entered.
              </p>
            </Card>
          )}

          {rows.length === 0 ? (
            <Card className="p-4">
              <p className="text-sm">No flats marked as yours yet.</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Tick <em>I own this flat</em> on the{" "}
                <Link href="/properties" className="underline hover:no-underline">
                  Properties
                </Link>{" "}
                page for the ones you own, and they will be valued here.
              </p>
            </Card>
          ) : (
          <Card className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Property</TableHead>
                  <TableHead className="text-right">m²</TableHead>
                  <TableHead className="text-right">€/m²</TableHead>
                  <TableHead className="text-right">Value</TableHead>
                  <TableHead>Land (Bodenrichtwert)</TableHead>
                  <TableHead className="text-right">Debt</TableHead>
                  <TableHead className="text-right">Equity</TableHead>
                  <TableHead className="text-right">LTV</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((p) => (
                  <Row key={p.property_id} p={p}
                       busy={busy === p.property_id}
                       onRefresh={() => refresh.mutate(p.property_id)} />
                ))}
              </TableBody>
            </Table>
          </Card>
          )}

          {managed.length > 0 && (
            <Card className="p-4">
              <p className="text-sm font-medium">
                Not owned — left out of the valuation
              </p>
              <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                {managed.map((p) => (
                  <li key={p.property_id}>
                    {p.property_name}
                    {(p.ortsteil || p.bezirk) && (
                      <span className="text-xs">
                        {" "}· {[p.ortsteil, p.bezirk].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted-foreground">
                These are tracked like any other flat — rent, meters,
                Nebenkosten — but their worth is not your asset, so no value,
                equity or LTV is computed for them. Change that with{" "}
                <em>I own this flat</em> on the{" "}
                <Link href="/properties" className="underline hover:no-underline">
                  Properties
                </Link>{" "}
                page.
              </p>
            </Card>
          )}

          <Card className="p-4">
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              <span>
                <strong className="text-foreground">Where these come from.</strong>{" "}
                The Bodenrichtwert is Berlin&apos;s official land value for the zone a house
                stands in, published once a year — fetched per flat with the button, never on
                a page load, and stored with the Stichtag it was official on.
                {data?.licence && ` Licence: ${data.licence}.`}{" "}
                The value itself is the living area times a comparable €/m², which is how a
                condo is actually valued; your own appraisal always overrides it. There is no
                real-time valuation of German property, so a figure marked{" "}
                <em>estimate</em> is exactly that.
                {noLand.length > 0 && ` ${noLand.length} flat${noLand.length === 1 ? " has" : "s have"} no land value fetched yet.`}
              </span>
            </p>
          </Card>
        </>
      )}
    </div>
  );
}

function Row({ p, busy, onRefresh }: {
  p: PropertyValuation; busy: boolean; onRefresh: () => void;
}) {
  return (
    <TableRow>
      <TableCell>
        <span className="font-medium">{p.property_name}</span>
        {p.we_label && <span className="ml-1 text-xs text-muted-foreground">{p.we_label}</span>}
        {(p.bezirk || p.ortsteil) && (
          <span className="block text-xs text-muted-foreground">
            {[p.ortsteil, p.bezirk].filter(Boolean).join(" · ")}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {p.living_sqm == null ? <span className="text-muted-foreground">—</span>
                              : num(p.living_sqm, 2)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {p.per_sqm == null ? <span className="text-muted-foreground">—</span> : eur(p.per_sqm)}
      </TableCell>
      <TableCell className="text-right">
        {p.value == null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <>
            <span className="font-medium tabular-nums">{eur(p.value)}</span>
            <span className="block text-[10px] text-muted-foreground">
              {p.basis === "own" ? `your figure${p.value_date ? `, ${p.value_date}` : ""}`
                                 : "estimate"}
            </span>
          </>
        )}
      </TableCell>
      <TableCell>
        {p.brw == null ? (
          <span className="text-xs text-muted-foreground">not fetched</span>
        ) : (
          <>
            <span className="tabular-nums text-sm">{eur(p.brw)}/m²</span>
            <span className="block text-[10px] text-muted-foreground">
              {p.stichtag}
              {p.gfz ? ` · GFZ ${num(p.gfz, 1)}` : ""}
              {p.land_per_floor_sqm ? ` · ${eur(p.land_per_floor_sqm)}/m² floor` : ""}
              {p.land_pct != null ? ` · ${num(p.land_pct, 0)} % of value is land` : ""}
            </span>
          </>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {p.debt ? eur(p.debt) : <span className="text-muted-foreground">—</span>}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {p.equity == null ? <span className="text-muted-foreground">—</span> : (
          <span className={p.equity < 0 ? "text-destructive" : ""}>{eur(p.equity)}</span>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {p.ltv == null ? <span className="text-muted-foreground">—</span> : `${num(p.ltv, 0)} %`}
      </TableCell>
      <TableCell>
        <Button variant="ghost" size="icon" onClick={onRefresh} disabled={busy}
                title={`Fetch the official land value for ${p.property_name}`}
                aria-label={`Fetch land value for ${p.property_name}`}>
          <RefreshCw className={`size-4 ${busy ? "animate-spin" : ""}`} />
        </Button>
      </TableCell>
    </TableRow>
  );
}
