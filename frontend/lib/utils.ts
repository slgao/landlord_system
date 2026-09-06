import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Today's date as YYYY-MM-DD in the browser's local time zone.
 *  `new Date().toISOString()` is UTC, which after 22:00 in Berlin during
 *  summer time is still yesterday — a payment or protocol entered late in
 *  the evening was being dated a day early. */
export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** True once the ISO date lies strictly before today. A contract ending
 *  today is still running today. */
export function isPastDate(iso?: string | null): boolean {
  return !!iso && iso < todayISO();
}

/** Whole days from today until the ISO date (negative when it has passed). */
export function daysUntil(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  const target = new Date(y, m - 1, d).getTime();
  const now = new Date(); now.setHours(0, 0, 0, 0);
  return Math.round((target - now.getTime()) / 86_400_000);
}
