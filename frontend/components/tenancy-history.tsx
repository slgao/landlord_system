"use client";

/**
 * Who has lived in one flat or WG room — and what the empty months cost.
 *
 * Everywhere else the app looks at a tenancy and asks what is owed now. This
 * looks at a *unit* and asks what has happened to it: every tenant it has had,
 * how long each stayed, what the rent did across the handovers, and the gaps
 * in between. The gaps are the part no other view computes, and the reason
 * this one is worth opening: a room let at a good rent that stands empty two
 * months between tenants earns less than a cheaper one that never does.
 *
 * A WG room is a unit of its own here, because it is let on its own contract.
 * The flat's other rooms appear as context beside the timeline, never folded
 * into it — they have their own tenants and their own vacancy.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TenancyHistory, Tenancy, Apartment } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/page-header";
import { amount, money, date as fmtD, num } from "@/lib/fmt";
import { ArrowRight, DoorOpen, FileSignature, Users } from "lucide-react";

const DAY_MS = 86_400_000;

/** An ISO date as a whole day number, so spans are day arithmetic and never
 *  trip over a daylight-saving boundary. */
function dayOf(iso: string): number {
  return Math.floor(Date.parse(`${iso.slice(0, 10)}T00:00:00Z`) / DAY_MS);
}

/**
 * A stretch of days in words. Days below a month, because a vacancy of three
 * weeks is not "one month" and rounding it up overstates every gap; months up
 * to a year; years beyond that, where the month count stops being readable.
 */
export function spellDays(days: number | null | undefined): string {
  if (days == null) return "—";
  if (days === 0) return "none";
  if (days === 1) return "1 day";
  if (days < 31) return `${days} days`;
  if (days < 365) return `${Math.round(days / 30.44)} months`;
  return `${num(days / 365.25, 1)} years`;
}

function statusBadge(t: Tenancy): string {
  if (t.status === "current") return "bg-primary/15 text-primary border-primary/20";
  if (t.status === "upcoming") {
    return "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/20";
  }
  return "bg-secondary text-secondary-foreground";
}

function statusLabel(t: Tenancy): string {
  if (t.status === "current") return "Living here";
  if (t.status === "upcoming") return "Moving in";
  return t.end_known ? "Moved out" : "Ended — no date on file";
}

/** `1 Mar 2024 – 30 Jun 2025`, or an open end where there is none. */
function term(t: Tenancy): string {
  const from = t.start_date ? fmtD(t.start_date) : "date not on file";
  if (t.end_date) return `${from} – ${fmtD(t.end_date)}`;
  if (t.status === "current") return `${from} – open`;
  return from;
}

/**
 * The unit's letting history as one track: each tenancy a segment, each gap a
 * void. A single hue carries "let", separated by a surface gap so adjacent
 * tenancies stay distinct without a second colour, and the running tenancy
 * sits at full strength while the ones that ended recede.
 *
 * Positions come from the summary's own span rather than the browser clock, so
 * the strip agrees with the figures beside it even across a timezone.
 */
function OccupancyStrip({ history }: { history: TenancyHistory }) {
  const { summary, tenancies } = history;
  const { first_start: firstStart, span_days: span } = summary;
  if (!firstStart || !span || span < 1) return null;

  const base = dayOf(firstStart);
  const lastDay = base + span - 1;
  const segments = tenancies
    .filter((t) => t.start_date && t.status !== "upcoming")
    .map((t) => {
      const from = Math.max(dayOf(t.start_date!), base);
      const to = Math.min(t.end_date ? dayOf(t.end_date) : lastDay, lastDay);
      return { t, from, to };
    })
    .filter((s) => s.to >= s.from);

  // A tick per calendar year, so a five-year history can be read at a glance.
  const firstYear = new Date(firstStart).getUTCFullYear();
  const lastYear = new Date((lastDay + 0.5) * DAY_MS).getUTCFullYear();
  const ticks: { year: number; pct: number }[] = [];
  for (let y = firstYear + 1; y <= lastYear; y++) {
    const pct = ((dayOf(`${y}-01-01`) - base) / span) * 100;
    if (pct > 2 && pct < 98) ticks.push({ year: y, pct });
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{fmtD(firstStart)}</span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm bg-primary" />Let
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm border border-border bg-muted" />
            Empty
          </span>
        </span>
        <span>today</span>
      </div>

      <div className="relative h-6 w-full rounded bg-muted ring-1 ring-inset ring-border"
        role="img"
        aria-label={`Let for ${summary.occupancy_pct}% of the time since ${firstStart}`}>
        {ticks.map((tk) => (
          <span key={tk.year} aria-hidden
            className="absolute top-0 bottom-0 w-px bg-border"
            style={{ left: `${tk.pct}%` }} />
        ))}
        {segments.map(({ t, from, to }) => (
          <span
            key={t.contract_id}
            title={`${t.tenant_name ?? "—"}: ${term(t)}`}
            className={`absolute top-0 bottom-0 rounded-sm bg-primary ${
              t.status === "current" ? "" : "opacity-60"
            }`}
            style={{
              left: `${((from - base) / span) * 100}%`,
              // A 2px surface gap keeps back-to-back tenancies readable as two.
              width: `max(2px, calc(${((to - from + 1) / span) * 100}% - 2px))`,
            }}
          />
        ))}
      </div>

      {ticks.length > 0 && (
        <div className="relative h-3">
          {ticks.map((tk) => (
            <span key={tk.year}
              className="absolute -translate-x-1/2 text-[10px] text-muted-foreground"
              style={{ left: `${tk.pct}%` }}>
              {tk.year}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: {
  label: string; value: React.ReactNode; hint?: string;
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums leading-tight">{value}</p>
      {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
    </div>
  );
}

export function TenancyHistoryPanel({ apartment, onClose }: {
  apartment: Apartment;
  onClose: () => void;
}) {
  const { data, isLoading, isError } = useQuery<TenancyHistory>({
    queryKey: ["apartment-tenancies", apartment.id],
    queryFn: () => api.get(`/api/apartments/${apartment.id}/tenancies`)
      .then((r) => r.data),
  });

  const s = data?.summary;
  const where = [apartment.property_name, apartment.flat]
    .filter(Boolean).join(" · ");

  // The most recent tenancy with a price on it — the one whose rent stands.
  const latest = data?.tenancies.find((t) => t.status === "current")
    ?? data?.tenancies.find((t) => t.status === "past");
  // €/m² on the cold rent where the split is on file, exactly as the
  // apartments list does it: a Mietspiegel figure is cold, and a warm rent
  // divided by the floor area makes the flat look dearer than it is.
  const perSqm = (() => {
    if (!apartment.size_sqm || !latest?.rent_end) return null;
    const cold = latest.nkv_end != null ? latest.rent_end - latest.nkv_end : null;
    return { value: (cold ?? latest.rent_end) / apartment.size_sqm, cold: cold != null };
  })();

  return (
    <>
      <PageHeader title={apartment.name} description={where}>
        <Button variant="outline" size="sm" onClick={onClose}>← Back</Button>
      </PageHeader>

      {isLoading ? (
        <Card><CardContent className="py-10 text-center text-muted-foreground">
          Loading history…
        </CardContent></Card>
      ) : isError || !data || !s ? (
        <Card><CardContent className="py-10 text-center text-muted-foreground">
          Could not load the history of this unit.
        </CardContent></Card>
      ) : s.tenancies === 0 ? (
        <Card><CardContent className="py-10 text-center text-muted-foreground">
          No tenancy has been recorded for this unit yet.
        </CardContent></Card>
      ) : (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">
                Let {s.occupancy_pct != null ? `${num(s.occupancy_pct, 1)} %` : "—"} of
                the time since the first tenant moved in
              </CardTitle>
              {s.vacant_since && (
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  Empty since {fmtD(s.vacant_since)} — {spellDays(s.longest_gap_days)} and counting.
                </p>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              <OccupancyStrip history={data} />

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1">
                <Stat label="Tenants so far" value={s.tenancies}
                  hint={s.upcoming > 0 ? `${s.upcoming} still to move in` : undefined} />
                <Stat label="Stood empty"
                  value={spellDays(s.vacant_days)}
                  hint={s.vacant_days ? `of ${spellDays(s.span_days)}` : undefined} />
                <Stat label="Longest empty stretch"
                  value={spellDays(s.longest_gap_days)} />
                <Stat label="Average stay"
                  value={s.avg_tenancy_months != null
                    ? `${num(s.avg_tenancy_months, 1)} months` : "—"}
                  hint={s.completed > 0
                    ? `over ${s.completed} completed ${s.completed === 1 ? "tenancy" : "tenancies"}`
                    : "nobody has moved out yet"} />
              </div>

              {s.rent_now != null && (
                <div className="flex flex-wrap items-center gap-2 text-sm border-t border-border pt-3">
                  <span className="text-xs text-muted-foreground">
                    {s.vacant_since ? "Last let at" : "Rent"}
                  </span>
                  {/* An arrow only where the rent actually moved — "600 € →
                      600 €" says nothing and reads like a change. */}
                  {s.rent_first != null && s.rent_first !== s.rent_now && (
                    <>
                      <span className="tabular-nums">{money(s.rent_first)}</span>
                      <ArrowRight className="size-3.5 text-muted-foreground" />
                    </>
                  )}
                  <span className="tabular-nums font-medium">{money(s.rent_now)}</span>
                  {perSqm && (
                    <span className="text-xs text-muted-foreground">
                      ({money(perSqm.value)}/m² {perSqm.cold ? "kalt" : "warm"})
                    </span>
                  )}
                </div>
              )}

              {data.siblings.length > 0 && (
                <p className="text-xs text-muted-foreground border-t border-border pt-3">
                  <Users className="inline size-3.5 mr-1 -mt-0.5" />
                  A WG room in flat {apartment.flat}, shared with{" "}
                  {data.siblings.map((x) => x.name).join(", ")}. Each room is let on
                  its own contract, so each has its own history.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <Table className="stack-sm">
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Term</TableHead>
                  <TableHead className="text-right">Stayed</TableHead>
                  <TableHead className="text-right">Rent</TableHead>
                  <TableHead className="text-right">Kaution</TableHead>
                  <TableHead className="text-right">Empty before</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.tenancies.map((t) => (
                  <TableRow key={t.contract_id}>
                    <TableCell data-label="Tenant">
                      <span className="font-medium">{t.tenant_name ?? "—"}</span>
                      <Badge className={`ml-2 ${statusBadge(t)}`}>{statusLabel(t)}</Badge>
                      {t.co_tenants.length > 0 && (
                        <span className="block text-xs text-muted-foreground mt-0.5">
                          with {t.co_tenants.map((c) => c.name).join(", ")}
                        </span>
                      )}
                      {t.handovers.length > 0 && (
                        <span className="block text-xs text-muted-foreground mt-0.5">
                          {t.handovers.map((h) => (
                            <span key={`${h.kind}-${h.date}`} className="mr-2 inline-flex items-center gap-1">
                              {h.kind === "move_out"
                                ? <DoorOpen className="size-3" />
                                : <FileSignature className="size-3" />}
                              {h.kind === "move_out" ? "Auszug" : "Einzug"}
                              {h.date ? ` ${fmtD(h.date)}` : ""}
                              {h.signed ? "" : " (unsigned)"}
                            </span>
                          ))}
                        </span>
                      )}
                    </TableCell>
                    <TableCell data-label="Term" className="text-muted-foreground whitespace-nowrap">
                      {term(t)}
                    </TableCell>
                    <TableCell data-label="Stayed" className="text-right tabular-nums">
                      {t.months != null ? `${t.months} mo` : "—"}
                    </TableCell>
                    <TableCell data-label="Rent" className="text-right tabular-nums">
                      {t.rent_start == null ? (
                        <span className="text-muted-foreground">—</span>
                      ) : t.rent_changes > 0 && t.rent_end !== t.rent_start ? (
                        <>
                          {money(t.rent_start)}
                          <span className="block text-xs text-muted-foreground">
                            → {money(t.rent_end)} after {t.rent_changes}{" "}
                            {t.rent_changes === 1 ? "change" : "changes"}
                          </span>
                        </>
                      ) : (
                        money(t.rent_start)
                      )}
                    </TableCell>
                    <TableCell data-label="Kaution" className="text-right tabular-nums">
                      {t.kaution_amount
                        ? <>
                            {amount(t.kaution_amount, t.kaution_currency)}
                            {t.kaution_returned_date && (
                              <span className="block text-xs text-muted-foreground">
                                returned {fmtD(t.kaution_returned_date)}
                              </span>
                            )}
                          </>
                        : <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell data-label="Empty before" className="text-right tabular-nums">
                      {t.gap_days_before == null ? (
                        <span className="text-muted-foreground">—</span>
                      ) : t.gap_days_before === 0 ? (
                        <span className="text-muted-foreground">no gap</span>
                      ) : (
                        <span className="text-amber-700 dark:text-amber-400">
                          {spellDays(t.gap_days_before)}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {s.undated > 0 && (
              <p className="px-4 py-2 text-xs text-muted-foreground border-t border-border">
                {s.undated} {s.undated === 1 ? "tenancy has" : "tenancies have"} no
                usable start date, so {s.undated === 1 ? "it is" : "they are"} listed
                last and left out of the occupancy figures.
              </p>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
