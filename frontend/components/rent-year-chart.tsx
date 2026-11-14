"use client";

/**
 * What came in per month this year, and the average across it.
 *
 * The page's month card answers "what arrived in October". This one answers
 * the question behind it — what the portfolio takes in a month — which is a
 * single number, so the number leads and the months give it its shape.
 *
 * Counted: payments of kind `rent`. A Nebenkosten Nachzahlung is not rent and
 * a refund would pull the figure down, so both stay out, exactly as the month
 * totals beside this already treat them. `amount` is the EUR value of a
 * payment whatever tender it arrived in, so foreign payments need no special
 * handling here.
 */

import { useMemo } from "react";
import { MONTHS, MonthlyBarCard } from "@/components/monthly-bar-card";
import { money } from "@/lib/fmt";
import { Payment } from "@/lib/types";

export function RentYearChart({ payments }: { payments: Payment[] }) {
  const now = new Date();
  const year = now.getFullYear();
  const currentMonth = now.getMonth() + 1;

  const { data, average, total, months } = useMemo(() => {
    const byMonth = new Array(12).fill(0);
    let lastWithRent = 0;
    for (const p of payments) {
      if (p.kind !== "rent") continue;
      if (!p.payment_date?.startsWith(String(year))) continue;
      const m = Number(p.payment_date.slice(5, 7));
      if (!(m >= 1 && m <= 12)) continue;
      byMonth[m - 1] += p.amount;
      if (m > lastWithRent) lastWithRent = m;
    }
    // Through the current month — rent is due monthly in advance (§556b BGB),
    // so this month's rent has normally arrived and belongs in the average;
    // dividing by twelve in March would understate it by three quarters. A
    // payment dated further ahead than that stretches the range rather than
    // being dropped: a figure that quietly leaves money out is worse than one
    // whose months are named.
    const count = Math.max(currentMonth, lastWithRent);
    const shown = byMonth.slice(0, count);
    const sum = shown.reduce((a, b) => a + b, 0);
    return {
      data: shown.map((value, i) => ({ month: MONTHS[i], value: +value.toFixed(2) })),
      average: sum / count,
      total: sum,
      months: count,
    };
  }, [payments, year, currentMonth]);

  return (
    <MonthlyBarCard
      title={`Rent received ${year}`}
      subtitle={`${MONTHS[0]}–${MONTHS[months - 1]} ${year} · ${money(total)} in total`}
      hero={money(average)}
      heroCaption="per month on average"
      data={data}
      average={average}
      seriesName="Received"
      empty={total === 0 ? `No rent recorded for ${year} yet.` : undefined}
    />
  );
}
