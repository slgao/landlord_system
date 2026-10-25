"use client";

/**
 * What to do first, for an account that has nothing in it yet.
 *
 * The dashboard of a fresh account read: cashflow —, net yield —, "0 of 0,
 * every room let", "nothing outstanding". Four dashes and a congratulation
 * for having let nothing, with no hint that a property comes before a flat,
 * a flat before a tenancy, and a tenancy before any of the figures mean
 * anything.
 *
 * The order here is the order the data depends on, so each step is possible
 * only once the one above it is done — which is why it is a list and not four
 * buttons.
 */

import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Check, ArrowRight } from "lucide-react";

export interface SetupState {
  properties: number;
  apartments: number;
  tenants: number;
  contracts: number;
  payments: number;
}

const STEPS = [
  { key: "properties", href: "/properties", label: "Add a property",
    hint: "One Wohnungseigentum unit — one WE, one Anlage V." },
  { key: "apartments", href: "/apartments", label: "Add the flat in it",
    hint: "A WG counts each room as its own flat, so each can be let apart." },
  { key: "tenants", href: "/tenants", label: "Add a tenant",
    hint: "Name and salutation are enough; the rest can wait." },
  { key: "contracts", href: "/contracts", label: "Record the tenancy",
    hint: "Rent, the Nebenkosten share inside it, and the deposit." },
  { key: "payments", href: "/rent-tracking", label: "Record a rent payment",
    hint: "From here the arrears, the balance sheet and the tax report fill in." },
] as const;

export function SetupChecklist({ state }: { state: SetupState }) {
  const done = (k: keyof SetupState) => state[k] > 0;
  const next = STEPS.find((s) => !done(s.key as keyof SetupState));
  if (!next) return null;              // nothing to explain any more

  const completed = STEPS.filter((s) => done(s.key as keyof SetupState)).length;

  return (
    <Card>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <h2 className="text-sm font-medium">Getting started</h2>
          <p className="text-xs text-muted-foreground tabular-nums">
            {completed} of {STEPS.length} done
          </p>
        </div>
        <ol className="space-y-2">
          {STEPS.map((step) => {
            const isDone = done(step.key as keyof SetupState);
            const isNext = step.key === next.key;
            return (
              <li key={step.key} className="flex items-start gap-3">
                <span className={`mt-0.5 size-5 shrink-0 rounded-full border grid place-items-center
                  ${isDone ? "bg-primary border-primary text-primary-foreground"
                           : isNext ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>
                  {isDone ? <Check className="size-3" />
                          : <span className="text-[10px] tabular-nums">{STEPS.indexOf(step) + 1}</span>}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={`text-sm ${isDone ? "text-muted-foreground line-through" : "font-medium"}`}>
                    {step.label}
                  </p>
                  {isNext && (
                    <p className="text-xs text-muted-foreground mt-0.5">{step.hint}</p>
                  )}
                </div>
                {isNext && (
                  <Button asChild size="sm" className="shrink-0">
                    <Link href={step.href}>
                      {step.label} <ArrowRight className="size-3.5 ml-1" />
                    </Link>
                  </Button>
                )}
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
