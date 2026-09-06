import { todayISO, isPastDate, daysUntil } from "@/lib/utils";

/** A contract is usually signed and recorded weeks before the tenant moves in.
 *  Between signing and the start date it is agreed but not running: no rent is
 *  due yet, the flat may still be occupied by someone else. Calling that
 *  "Active" reads wrong, so it gets its own status. */
export type ContractStatus = "terminated" | "expired" | "upcoming" | "active";

export interface ContractLike {
  start_date: string;
  end_date?: string | null;
  terminated?: boolean;
}

export function contractStatus(c: ContractLike): ContractStatus {
  if (c.terminated) return "terminated";
  if (isPastDate(c.end_date)) return "expired";
  if (c.start_date && c.start_date > todayISO()) return "upcoming";
  return "active";
}

export const CONTRACT_STATUS_LABEL: Record<ContractStatus, string> = {
  terminated: "Terminated",
  expired: "Expired",
  upcoming: "Upcoming",
  active: "Active",
};

export function contractStatusLabel(c: ContractLike): string {
  return CONTRACT_STATUS_LABEL[contractStatus(c)];
}

/** Badge colours: grey once it is over, red when it ran out unnoticed,
 *  sky for one that has not started yet, amber when the end is within 90
 *  days, and the primary colour while it simply runs. */
export function contractStatusColor(c: ContractLike): string {
  switch (contractStatus(c)) {
    case "terminated":
      return "bg-secondary text-secondary-foreground";
    case "expired":
      return "bg-destructive/15 text-destructive border-destructive/20";
    case "upcoming":
      return "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/20";
    default:
      if (c.end_date && daysUntil(c.end_date) <= 90) {
        return "bg-amber-500/15 text-amber-400 border-amber-500/20";
      }
      return "bg-primary/15 text-primary border-primary/20";
  }
}

/** The countdown shown beside an Upcoming badge: "starts tomorrow". */
export function startsInLabel(startDate: string): string {
  const days = daysUntil(startDate);
  if (days <= 0) return "starts today";
  if (days === 1) return "starts tomorrow";
  return `starts in ${days} days`;
}

/** Suffix for the contract pickers, so a dropdown says which entries are not
 *  ordinary running contracts. */
export function contractStatusSuffix(c: ContractLike): string {
  const status = contractStatus(c);
  return status === "active" ? "" : ` (${CONTRACT_STATUS_LABEL[status].toLowerCase()})`;
}
