"use client";

import { useState, useRef, useEffect } from "react";
import { Calendar as CalIcon, ChevronLeft, ChevronRight } from "lucide-react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

// A small, dependency-free date picker. Opens straight to a day grid (no
// month/year "first screen" like some native pickers) so a date is one click
// away; month + year dropdowns in the header allow quick jumping. Value is the
// same ISO "YYYY-MM-DD" string used by the old <input type="date">, so it's a
// drop-in replacement.

const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember"];
const WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

function parseISO(v?: string): Date | null {
  if (!v) return null;
  const [y, m, d] = v.split("-").map(Number);
  if (!y || !m || !d) return null;
  const dt = new Date(y, m - 1, d);
  return isNaN(+dt) ? null : dt;
}
function toISO(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtDE(d: Date) {
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}
function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function DatePicker({ label, value, onChange, className }: {
  label?: string; value: string; onChange: (v: string) => void; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = parseISO(value);
  const today = new Date();
  const [view, setView] = useState<Date>(selected ?? today);
  const ref = useRef<HTMLDivElement>(null);

  // When (re)opening, jump the grid to the currently selected month.
  useEffect(() => { if (open) setView(parseISO(value) ?? new Date()); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Close on click-outside / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const y = view.getFullYear(), m = view.getMonth();
  const startWd = (new Date(y, m, 1).getDay() + 6) % 7; // Monday-first offset
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array<null>(startWd).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const shift = (delta: number) => setView(new Date(y, m + delta, 1));

  const yearFrom = Math.min(2015, y), yearTo = Math.max(today.getFullYear() + 3, y);
  const years: number[] = [];
  for (let yr = yearTo; yr >= yearFrom; yr--) years.push(yr);

  return (
    <div className={cn("space-y-1", className)} ref={ref} style={{ position: "relative" }}>
      {label && <Label className="text-xs">{label}</Label>}
      <button
        type="button" onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex h-8 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-sm",
          "ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
          !value && "text-muted-foreground",
        )}
      >
        <span>{selected ? fmtDE(selected) : "TT.MM.JJJJ"}</span>
        <CalIcon className="size-4 opacity-60" />
      </button>

      {open && (
        <div className="absolute left-0 z-50 mt-1 w-64 rounded-md border border-border bg-popover p-2 text-popover-foreground shadow-md">
          {/* header: prev · month/year · next */}
          <div className="mb-1 flex items-center gap-1">
            <button type="button" onClick={() => shift(-1)} aria-label="Vorheriger Monat"
              className="grid size-7 place-items-center rounded hover:bg-muted">
              <ChevronLeft className="size-4" />
            </button>
            <select value={m} onChange={(e) => setView(new Date(y, Number(e.target.value), 1))}
              className="h-7 flex-1 rounded bg-background text-sm">
              {MONTHS.map((name, i) => <option key={i} value={i}>{name}</option>)}
            </select>
            <select value={y} onChange={(e) => setView(new Date(Number(e.target.value), m, 1))}
              className="h-7 rounded bg-background text-sm">
              {years.map((yr) => <option key={yr} value={yr}>{yr}</option>)}
            </select>
            <button type="button" onClick={() => shift(1)} aria-label="Nächster Monat"
              className="grid size-7 place-items-center rounded hover:bg-muted">
              <ChevronRight className="size-4" />
            </button>
          </div>

          {/* weekday header */}
          <div className="grid grid-cols-7 text-center text-[11px] text-muted-foreground">
            {WEEKDAYS.map((w) => <span key={w} className="py-1">{w}</span>)}
          </div>

          {/* day grid */}
          <div className="grid grid-cols-7 gap-0.5">
            {cells.map((day, i) => {
              if (day === null) return <span key={i} />;
              const d = new Date(y, m, day);
              const isSel = selected != null && sameDay(d, selected);
              const isToday = sameDay(d, today);
              return (
                <button
                  key={i} type="button"
                  onClick={() => { onChange(toISO(d)); setOpen(false); }}
                  className={cn(
                    "grid size-8 place-items-center rounded text-sm",
                    isSel ? "bg-primary text-primary-foreground font-medium"
                      : "hover:bg-muted",
                    !isSel && isToday && "ring-1 ring-primary/50",
                  )}
                >
                  {day}
                </button>
              );
            })}
          </div>

          {/* quick "today" shortcut */}
          <div className="mt-1 flex justify-end border-t border-border/60 pt-1">
            <button type="button"
              onClick={() => { onChange(toISO(today)); setOpen(false); }}
              className="rounded px-2 py-1 text-xs text-primary hover:bg-muted">
              Heute
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
