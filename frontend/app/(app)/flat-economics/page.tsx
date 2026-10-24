"use client";

// What each flat actually earns.
//
// The page exists to keep three answers apart, because they routinely disagree:
// what the bank account sees each month (cashflow), what the flat earns once
// you stop counting the Tilgung as a cost (operating result), and what that is
// as a return on the flat's worth (yield). A flat can be cashflow negative and
// still be a good investment — and nothing else in the app says so.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FlatEconomics, FlatInsights } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Info } from "lucide-react";
import Link from "next/link";

const eur = (n: number) =>
  `${n.toLocaleString("de-DE", { maximumFractionDigits: 0 })} €`;
const pct = (n: number, d = 2) =>
  `${n.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d })} %`;
const num = (n: number, d = 0) =>
  n.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
const dash = <span className="text-muted-foreground">—</span>;

/** Red below zero, green above — for a figure where the sign is the point. */
function signed(n: number) {
  return n < 0 ? "text-destructive" : "text-emerald-600 dark:text-emerald-400";
}

function Stat({ label, value, sub, className }: {
  label: string; value: string; sub?: string; className?: string;
}) {
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${className ?? ""}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </Card>
  );
}

export default function FlatEconomicsPage() {
  const { data, isLoading } = useQuery<FlatInsights>({
    queryKey: ["flat-insights"],
    queryFn: () => api.get("/api/insights/flats").then((r) => r.data),
  });

  const flats = data?.flats ?? [];
  const owned = flats.filter((f) => f.owned);
  const sublets = flats.filter((f) => !f.owned);
  const s = data?.summary;
  const sub = data?.sublets;
  const vacant = flats.filter((f) => f.vacant_rooms > 0);
  const owing = flats.filter((f) => f.arrears > 0);
  const unvalued = flats.filter((f) => f.owned && !f.value);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Flat Economics"
        description="What each flat earns, costs and owes, per month."
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !s ? (
        <Card className="p-4">
          <p className="text-sm">Nothing to show yet.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Tick <em>I own this flat</em> on the{" "}
            <Link href="/properties" className="underline hover:no-underline">Properties</Link>{" "}
            page for the flats that are yours.
          </p>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Rent in" value={eur(s.rent_monthly)}
                  sub={`${s.let_rooms} of ${s.rooms} rooms let`} />
            <Stat label="Running costs" value={eur(s.costs_monthly)}
                  sub="Hausgeld, Grundsteuer, Internet…" />
            <Stat label="Cashflow" value={eur(s.cashflow_monthly)}
                  className={signed(s.cashflow_monthly)}
                  sub={`after ${eur(s.instalment_monthly)} of instalments`} />
            <Stat label="Operating result" value={eur(s.operating_monthly)}
                  className={signed(s.operating_monthly)}
                  sub={s.split_unknown > 0
                    ? `at least — ${s.split_unknown} loan${s.split_unknown === 1 ? "" : "s"} not on file`
                    : `${eur(s.principal_monthly)} of it is Tilgung`} />
          </div>

          {/* The one number that explains the gap between the two above. */}
          <Card className="p-4">
            <p className="text-sm">
              Of the {eur(s.instalment_monthly)} leaving each month,{" "}
              <strong>{eur(s.interest_monthly)}</strong> is interest and{" "}
              <strong>{eur(s.principal_monthly)}</strong> buys the flats. The Tilgung is not a
              cost — it is the reason the cashflow and the operating result differ by{" "}
              {eur(s.operating_monthly - s.cashflow_monthly)} a month.
            </p>
            {s.gross_yield != null ? (
              <p className="mt-2 text-sm text-muted-foreground">
                On {eur(s.value ?? 0)} of value across {s.valued_flats} valued flat
                {s.valued_flats === 1 ? "" : "s"}: {pct(s.gross_yield)} gross,{" "}
                {pct(s.net_yield ?? 0)} net.
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">
                No yields yet — set a comparable €/m² on the{" "}
                <Link href="/valuation" className="underline hover:no-underline">Valuation</Link>{" "}
                page and they follow.
              </p>
            )}
          </Card>

          {/* Contradictions in the data. Each says which figure was used, so
              the numbers above are still readable while it is sorted out. */}
          {(data?.warnings?.length ?? 0) > 0 && (
            <Card className="p-4 border-amber-500/40">
              <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                Worth a look
              </p>
              <ul className="mt-2 space-y-2 text-sm">
                {data!.warnings.map((w, i) => (
                  <li key={`${w.property_id}-${w.kind}-${i}`}>
                    <span className="font-medium">{w.property_name}</span>{" "}
                    {w.kind === "mortgage_conflict" && (
                      <span className="text-muted-foreground">
                        — the mortgage is on file twice and the two disagree: the loan&apos;s
                        terms say {eur(w.loan_instalment ?? 0)}/month, a <em>Mortgage</em>{" "}
                        flat cost says {eur(w.mortgage_cost ?? 0)}{" "}
                        ({(w.difference ?? 0) > 0 ? "+" : ""}{eur(w.difference ?? 0)}).
                        The loan is used, because only its terms split interest from Tilgung.
                        Delete the duplicate cost, or correct whichever record is out of date.
                      </span>
                    )}
                    {w.kind === "rent_to_owner_on_owned" && (
                      <span className="text-muted-foreground">
                        — you own this flat, but it still has a <em>Miete</em> cost of{" "}
                        {eur(w.amount ?? 0)}/month. It is counted as an ordinary running
                        cost. That is right for a ground rent (Erbbauzins); if it is left
                        over from when the flat was a sublet, delete it.
                      </span>
                    )}
                    {w.kind === "loan_on_sublet" && (
                      <span className="text-muted-foreground">
                        — this flat is marked as not owned, but carries a loan of{" "}
                        {eur(w.amount ?? 0)}/month, which is subtracted from its margin.
                        Either it is yours after all, or the loan belongs elsewhere.
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {(vacant.length > 0 || owing.length > 0) && (
            <Card className="p-4">
              {vacant.length > 0 && (
                <p className="text-sm">
                  <strong>Standing empty:</strong>{" "}
                  {vacant.map((f) => `${f.property_name} (${f.vacant_rooms} of ${f.rooms})`)
                         .join(", ")}
                  {" — "}
                  {/* Everything that still has to be paid on it: the rent to its
                      owner does not stop because nobody is living there. */}
                  {eur(vacant.reduce((t, f) => t + f.costs_monthly
                                     + f.rent_to_owner_monthly + f.instalment_monthly, 0))}{" "}
                  a month with no rent against it.
                </p>
              )}
              {owing.length > 0 && (
                <p className={vacant.length > 0 ? "mt-2 text-sm" : "text-sm"}>
                  <strong>Rent outstanding:</strong>{" "}
                  {owing.map((f) => `${f.property_name} ${eur(f.arrears)}`).join(", ")}.{" "}
                  <Link href="/payment-reminders" className="underline hover:no-underline">
                    Payment Reminders
                  </Link>
                </p>
              )}
            </Card>
          )}

          <Card className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Flat</TableHead>
                  <TableHead className="text-right">Rent</TableHead>
                  <TableHead className="text-right">Costs</TableHead>
                  <TableHead className="text-right">Instalment</TableHead>
                  <TableHead className="text-right">Cashflow</TableHead>
                  <TableHead className="text-right">Operating</TableHead>
                  <TableHead className="text-right">Gross</TableHead>
                  <TableHead className="text-right">Net</TableHead>
                  <TableHead className="text-right">Factor</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {owned.map((f) => <Row key={f.property_id} f={f} />)}
              </TableBody>
            </Table>
          </Card>

          {/* What the flats were bought with. The Kaufpreis already lives in
              Tax Setup for the AfA; nothing is duplicated here. */}
          {data?.purchase && (
            <Card className="overflow-hidden">
              <div className="p-4 pb-3">
                <p className="text-sm font-medium">Since purchase</p>
                <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
                  <span className="tabular-nums">{eur(data.purchase.invested_total)} invested</span>
                  <span className="text-muted-foreground">−</span>
                  <span className="tabular-nums">{eur(data.purchase.loans_original)} borrowed</span>
                  <span className="text-muted-foreground">=</span>
                  <span className={`font-semibold tabular-nums ${signed(data.purchase.equity_invested)}`}>
                    {eur(data.purchase.equity_invested)} of your own money
                  </span>
                  {data.purchase.equity_return_invested != null && (
                    <span className="text-muted-foreground">
                      · earning <strong className="text-foreground">
                        {pct(data.purchase.equity_return_invested)}
                      </strong> a year on it
                    </span>
                  )}
                </div>
                {data.purchase.value_gain != null && (
                  <p className="mt-1 text-sm text-muted-foreground">
                    Worth {eur(data.purchase.value_gain)} more than the{" "}
                    {eur(data.purchase.purchase_price)} paid, on today&apos;s estimate.
                  </p>
                )}
                {data.purchase.costs_missing && (
                  <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                    Some Kaufnebenkosten are blank — Grunderwerbsteuer, Notar, Grundbuch,
                    Makler. Until they are filled in on{" "}
                    <Link href="/tax-setup" className="underline hover:no-underline">
                      Tax Setup
                    </Link>
                    , the equity above reads too low and the return on it too high. A loan
                    that covered them can exceed the purchase price on its own.
                  </p>
                )}
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Flat</TableHead>
                    <TableHead className="text-right">Kaufpreis</TableHead>
                    <TableHead className="text-right">Nebenkosten</TableHead>
                    <TableHead className="text-right">Borrowed</TableHead>
                    <TableHead className="text-right">Own money</TableHead>
                    <TableHead className="text-right">EK-Rendite</TableHead>
                    <TableHead className="text-right">Since then</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {owned.filter((f) => f.purchase).map((f) => (
                    <TableRow key={f.property_id}>
                      <TableCell>
                        <span className="font-medium">{f.property_name}</span>
                        {f.purchase_date && (
                          <span className="block text-xs text-muted-foreground">
                            bought {f.purchase_date}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {eur(f.purchase!.purchase_price)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {f.purchase!.purchase_costs != null
                          ? eur(f.purchase!.purchase_costs)
                          : <span className="text-amber-700 dark:text-amber-400">not set</span>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {eur(f.purchase!.loans_original)}
                        {f.purchase!.loan_to_price != null && (
                          <span className="block text-[10px] text-muted-foreground">
                            {num(f.purchase!.loan_to_price, 0)} % of the price
                          </span>
                        )}
                      </TableCell>
                      <TableCell className={`text-right tabular-nums ${
                        signed(f.purchase!.equity_invested)}`}>
                        {eur(f.purchase!.equity_invested)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {f.equity_return_invested != null
                          ? pct(f.equity_return_invested)
                          : dash}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {f.value_gain ? (
                          <span className={signed(f.value_gain.gain)}>
                            {eur(f.value_gain.gain)}
                            <span className="block text-[10px] text-muted-foreground">
                              {f.value_gain.gain_pct > 0 ? "+" : ""}
                              {num(f.value_gain.gain_pct, 0)} %
                            </span>
                          </span>
                        ) : dash}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}

          {sub && sublets.length > 0 && (
            <Card className="overflow-hidden">
              <div className="p-4 pb-3">
                <p className="text-sm font-medium">Sublet — rented from an owner, let on</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  A yield means nothing here: the value is somebody else&apos;s. What the
                  arrangement earns is the margin — rent in, less the rent to the owner, less
                  the costs that fall on you.
                </p>
                <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
                  <span className="tabular-nums">{eur(sub.rent_monthly)} in</span>
                  <span className="text-muted-foreground">−</span>
                  <span className="tabular-nums">{eur(sub.rent_to_owner_monthly)} to owners</span>
                  <span className="text-muted-foreground">−</span>
                  <span className="tabular-nums">{eur(sub.costs_monthly)} costs</span>
                  <span className="text-muted-foreground">=</span>
                  <span className={`font-semibold tabular-nums ${signed(sub.margin_monthly)}`}>
                    {eur(sub.margin_monthly)} a month
                  </span>
                  {sub.margin_pct != null && (
                    <span className="text-xs text-muted-foreground">
                      ({sub.margin_pct.toLocaleString("de-DE")} % of the rent taken in)
                    </span>
                  )}
                </div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Flat</TableHead>
                    <TableHead className="text-right">Rent in</TableHead>
                    <TableHead className="text-right">Rent to owner</TableHead>
                    <TableHead className="text-right">Other costs</TableHead>
                    <TableHead className="text-right">Margin</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sublets.map((f) => (
                    <TableRow key={f.property_id}>
                      <TableCell>
                        <span className="font-medium">{f.property_name}</span>
                        <span className="block text-xs text-muted-foreground">
                          {f.let_rooms} of {f.rooms} let
                          {f.vacant_rooms > 0 && (
                            <span className="text-destructive"> · {f.vacant_rooms} empty</span>
                          )}
                          {f.arrears > 0 && (
                            <span className="text-destructive"> · {eur(f.arrears)} owed</span>
                          )}
                          {f.instalment_monthly > 0 && (
                            <span className="text-destructive">
                              {" "}· plus {eur(f.instalment_monthly)} loan
                            </span>
                          )}
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {eur(f.rent_monthly)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {f.rent_to_owner_monthly
                          ? eur(f.rent_to_owner_monthly)
                          : <span className="text-muted-foreground">not recorded</span>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {eur(f.costs_monthly)}
                      </TableCell>
                      <TableCell className={`text-right tabular-nums font-medium ${
                        signed(f.cashflow_monthly)}`}>
                        {eur(f.cashflow_monthly)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}

          <Card className="p-4">
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              <span>
                <strong className="text-foreground">How these are worked out.</strong>{" "}
                Rent is what is currently contracted, one contract per room, not an average of
                what arrived. Costs are the recurring charges in force today — a superseded
                price does not count beside its successor. The instalment comes from the loan&apos;s
                own terms where they are on file, which is what splits interest from Tilgung;
                where only a <em>Mortgage</em> flat cost records it, the cashflow is still exact
                but the split is left blank rather than guessed.
                {" "}<strong className="text-foreground">Factor</strong> is the Kaufpreisfaktor,
                value ÷ annual rent.
                {unvalued.length > 0 && ` ${unvalued.length} flat${unvalued.length === 1 ? " has" : "s have"} no value yet, so no yield.`}
                {sublets.length > 0 &&
                  " A flat recording a cost of type Miete, Untermiete or Pacht has it read as rent to its owner."}
              </span>
            </p>
          </Card>
        </>
      )}
    </div>
  );
}

/** A flat you own. Sublets have their own table — rent to an owner is not a
 *  running cost like any other, and a yield on somebody else's value is not a
 *  number worth printing. */
function Row({ f }: { f: FlatEconomics }) {
  const empty = f.vacant_rooms > 0;
  return (
    <TableRow>
      <TableCell>
        <span className="font-medium">{f.property_name}</span>
        <span className="block text-xs text-muted-foreground">
          {f.let_rooms} of {f.rooms} let
          {empty && <span className="text-destructive"> · {f.vacant_rooms} empty</span>}
          {f.living_sqm ? ` · ${f.living_sqm.toLocaleString("de-DE")} m²` : ""}
          {f.rent_per_sqm ? ` · ${eur(f.rent_per_sqm)}/m²` : ""}
          {f.arrears > 0 && (
            <span className="text-destructive"> · {eur(f.arrears)} owed</span>
          )}
        </span>
      </TableCell>
      <TableCell className="text-right tabular-nums">{eur(f.rent_monthly)}</TableCell>
      <TableCell className="text-right tabular-nums">{eur(f.costs_monthly)}</TableCell>
      <TableCell className="text-right">
        {f.instalment_monthly ? (
          <>
            <span className="tabular-nums">{eur(f.instalment_monthly)}</span>
            <span className="block text-[10px] text-muted-foreground">
              {f.split_known && f.interest_monthly != null
                ? `${eur(f.interest_monthly)} interest · ${eur(f.principal_monthly ?? 0)} Tilgung`
                : "split unknown — no loan terms on file"}
            </span>
          </>
        ) : dash}
      </TableCell>
      <TableCell className={`text-right tabular-nums font-medium ${signed(f.cashflow_monthly)}`}>
        {eur(f.cashflow_monthly)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {f.operating_monthly == null ? dash : (
          <span className={signed(f.operating_monthly)}>{eur(f.operating_monthly)}</span>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {f.gross_yield == null ? dash : pct(f.gross_yield)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {f.net_yield == null ? dash : pct(f.net_yield)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {f.kaufpreisfaktor == null ? dash : `${f.kaufpreisfaktor.toLocaleString("de-DE")}×`}
      </TableCell>
    </TableRow>
  );
}
