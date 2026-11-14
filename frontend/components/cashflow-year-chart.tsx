"use client";

/**
 * What was left each month this year, once everything had gone out.
 *
 * The card above it says what came in. This one subtracts what left: the
 * flat's running costs, the mortgage instalment, and the one-off bills that
 * actually fell in a month — a new boiler is real money out of the account,
 * however untypical the month it lands in. Net of what tenants paid or were
 * repaid on their Nebenkostenabrechnung, which is money moving the other way.
 *
 * It is deliberately not the Cashflow figure on the dashboard. That one is
 * what a typical month earns, recurring costs only, and it barely moves. This
 * is what the year actually did, month by month, so a month that paid for
 * itself and one that did not are told apart at a glance.
 *
 * The arithmetic is the balance sheet's own — `Actual received − Costs`, where
 * its costs already carry the mortgage under the rule in cost_types.py — so
 * this page and the Balance Sheet can never quote different figures.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { MONTHS, MonthlyBarCard } from "@/components/monthly-bar-card";
import { money, signed } from "@/lib/fmt";

interface MonthlyRow {
  Month: string;
  "Actual received (€)"?: number;
  "Costs (€)"?: number;
}

interface BalanceSheet {
  year: number;
  properties?: { monthly_rows?: MonthlyRow[] }[];
}

export function CashflowYearChart() {
  const year = new Date().getFullYear();
  // One boiler in August flattens every other month onto the zero line — true,
  // and unreadable. The Balance Sheet answers this with the same two buttons,
  // so the choice is made the same way in both places: the real cash by
  // default, the underlying rhythm one click away.
  const [withOneOff, setWithOneOff] = useState(true);

  // Keyed exactly as the Balance Sheet page keys its views, so opening both
  // does not fetch the same year twice.
  const { data: bs } = useQuery<BalanceSheet>({
    queryKey: ["balance-sheet", year, withOneOff],
    queryFn: () => api.get(`/api/reports/balance-sheet/${year}?include_one_off=${withOneOff}`)
      .then((r) => r.data),
  });

  const { data, average, inTotal, outTotal, months } = useMemo(() => {
    const received: number[] = [];
    const costs: number[] = [];
    for (const prop of bs?.properties ?? []) {
      (prop.monthly_rows ?? []).forEach((row, i) => {
        received[i] = (received[i] ?? 0) + (row["Actual received (€)"] ?? 0);
        costs[i] = (costs[i] ?? 0) + (row["Costs (€)"] ?? 0);
      });
    }
    const net = received.map((r, i) => r - (costs[i] ?? 0));
    const sum = net.reduce((a, b) => a + b, 0);
    return {
      data: net.map((value, i) => ({ month: MONTHS[i] ?? "", value: +value.toFixed(2) })),
      average: net.length ? sum / net.length : 0,
      inTotal: received.reduce((a, b) => a + b, 0),
      outTotal: costs.reduce((a, b) => a + b, 0),
      months: net.length,
    };
  }, [bs]);

  const toggle = (
    <div className="flex rounded-md border border-border overflow-hidden text-xs">
      <button
        onClick={() => setWithOneOff(false)}
        className={`px-2.5 py-1 transition-colors ${!withOneOff
          ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:text-foreground"}`}
        title="Rent against the running costs and the mortgage only — comparable month to month"
      >
        Running costs
      </button>
      <button
        onClick={() => setWithOneOff(true)}
        className={`px-2.5 py-1 border-l border-border transition-colors ${withOneOff
          ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground hover:text-foreground"}`}
        title="Also the one-off bills from Tax Setup — a repair, a Hausgeld settlement — in the month they were paid, net of what tenants paid or got back on their Nebenkostenabrechnung"
      >
        + one-off
      </button>
    </div>
  );

  const nothing = months === 0 || (inTotal === 0 && outTotal === 0);

  return (
    <MonthlyBarCard
      title={`Cashflow ${year}`}
      subtitle={`${MONTHS[0]}–${MONTHS[months - 1]} ${year} · ${money(inTotal)} in · ${money(outTotal)} out`
        + (withOneOff ? ", one-off bills included" : ", running costs and mortgage only")}
      hero={signed(average)}
      heroCaption="per month on average"
      data={data}
      average={average}
      seriesName="Net"
      diverging
      action={toggle}
      empty={nothing ? `No rent or costs recorded for ${year} yet.` : undefined}
    />
  );
}
