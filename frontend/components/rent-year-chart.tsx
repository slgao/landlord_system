"use client";

/**
 * What came in per month this year, and the average across it.
 *
 * The page's other card answers "what arrived in October". This one answers
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
import {
  Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { C, ChartTooltip, fmtAxis } from "@/components/chart";
import { money } from "@/lib/fmt";
import { Payment } from "@/lib/types";

// The same short labels the other charts use, so two charts in one app do not
// name the months two ways.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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
      data: shown.map((received, i) => ({ month: MONTHS[i], Received: +received.toFixed(2) })),
      average: sum / count,
      total: sum,
      months: count,
    };
  }, [payments, year, currentMonth]);

  const nothingYet = total === 0;

  return (
    <Card className="mb-4">
      <CardHeader className="pb-2">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <CardTitle className="text-sm font-medium">Rent received {year}</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">
              {nothingYet
                ? `No rent recorded for ${year} yet.`
                : `${MONTHS[0]}–${MONTHS[months - 1]} ${year} · ${money(total)} in total`}
            </p>
            {!nothingYet && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground mt-1.5">
                <svg width="18" height="2" aria-hidden="true" className="shrink-0">
                  <line x1="0" y1="1" x2="18" y2="1" stroke="hsl(var(--foreground))"
                    strokeWidth="1.5" strokeDasharray="4 4" />
                </svg>
                the average, across the months
              </p>
            )}
          </div>
          {/* Right-aligned beside the title, left-aligned under it once the
              header wraps on a phone — otherwise the caption sits off the
              figure it belongs to. */}
          {!nothingYet && (
            <div className="text-left sm:text-right">
              {/* The headline. Proportional digits: tabular figures make a
                  large standalone number look loose. */}
              <p className="text-3xl font-semibold leading-none">{money(average)}</p>
              <p className="text-xs text-muted-foreground mt-1">per month on average</p>
            </div>
          )}
        </div>
      </CardHeader>
      {!nothingYet && (
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
              <XAxis dataKey="month" tickLine={false} axisLine={false}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
              <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={fmtAxis}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />}
                cursor={{ fill: "hsl(var(--accent))", opacity: 0.35 }} />
              {/* One series, so no legend: the title names it. The line is an
                  annotation rather than a second series, and carries its own
                  label so it is never identified by colour alone. */}
              <Bar dataKey="Received" name="Received" fill={C.actual}
                maxBarSize={24} radius={[4, 4, 0, 0]} />
              {/* No label on the line: inside the plot it lands on whichever
                  bar happens to be tall that month — in this portfolio,
                  November. The key in the header names it instead, where
                  nothing can collide with it. */}
              <ReferenceLine y={average} stroke={C.net} strokeWidth={1.5}
                strokeDasharray="4 4" ifOverflow="extendDomain" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      )}
    </Card>
  );
}
