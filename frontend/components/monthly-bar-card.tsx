"use client";

/**
 * A year in months, with the one number it comes to.
 *
 * Both cards on Rent Tracking ask the same shape of question — what happened
 * month by month, and what that averages to — so they are the same card with
 * different data. Keeping them one component is what keeps them reading as a
 * pair rather than as two charts that happen to sit together.
 *
 * Drawn to the conventions already in this app: the Kontobuch palette, thin
 * bars with rounded data-ends, a hairline grid, no legend for a single series
 * (the title names it). The average is a dashed line named in the header, not
 * labelled in the plot, where the label lands on whichever bar happens to be
 * tall that month.
 */

import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { C, ChartTooltip, fmtAxis } from "@/components/chart";

export interface MonthPoint {
  month: string;
  value: number;
}

export function MonthlyBarCard({
  title, subtitle, hero, heroCaption, data, average, seriesName,
  diverging = false, empty, action,
}: {
  title: string;
  subtitle: string;
  hero: string;
  heroCaption: string;
  data: MonthPoint[];
  average: number | null;
  /** The name the tooltip gives the figure. */
  seriesName: string;
  /** Colour each bar by its sign and draw the zero line — for a figure that
   *  can go either way, where which side of zero a month fell is the point. */
  diverging?: boolean;
  /** Shown instead of the chart when there is nothing to draw. */
  empty?: string;
  /** A control for the card, shown beside the title. */
  action?: React.ReactNode;
}) {
  const rows = data.map((d) => ({ month: d.month, [seriesName]: d.value }));
  const nothingYet = !!empty;

  return (
    <Card className="mb-4">
      <CardHeader className="pb-2">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <CardTitle className="text-sm font-medium">{title}</CardTitle>
              {action}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {nothingYet ? empty : subtitle}
            </p>
            {!nothingYet && average != null && (
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
              {/* Proportional digits: tabular figures make a large standalone
                  number look loose. */}
              <p className="text-3xl font-semibold leading-none">{hero}</p>
              <p className="text-xs text-muted-foreground mt-1">{heroCaption}</p>
            </div>
          )}
        </div>
      </CardHeader>
      {!nothingYet && (
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} vertical={false} />
              <XAxis dataKey="month" tickLine={false} axisLine={false}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={fmtAxis}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />}
                cursor={{ fill: "hsl(var(--accent))", opacity: 0.35 }} />
              <Bar dataKey={seriesName} name={seriesName} maxBarSize={24}
                fill={C.actual} radius={[4, 4, 0, 0]}>
                {diverging && rows.map((r, i) => {
                  const v = r[seriesName] as number;
                  return (
                    <Cell key={i} fill={v < 0 ? C.costs : C.actual}
                      // The rounded end belongs at the data end, square at the
                      // baseline — which for a month below zero is the bottom.
                      radius={(v < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0]) as unknown as number} />
                  );
                })}
              </Bar>
              {/* A solid hairline for zero, because it is the baseline rather
                  than a threshold; the dashed one is the average. */}
              {diverging && (
                <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1} />
              )}
              {average != null && (
                <ReferenceLine y={average} stroke={C.net} strokeWidth={1.5}
                  strokeDasharray="4 4" ifOverflow="extendDomain" />
              )}
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      )}
    </Card>
  );
}

/** The months of a year, as the charts label them — the same short names the
 *  balance sheet's own rows use, so two charts never name a month two ways. */
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
