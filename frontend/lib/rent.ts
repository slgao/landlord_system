import { Contract } from "@/lib/types";

/** The cold rent (Kaltmiete) of a contract, or null when the split was never
 *  recorded. `rent` is what the tenant actually transfers; how much of it is a
 *  Nebenkosten prepayment depends on the contract, so a rent with no split on
 *  file cannot be compared against a Mietspiegel figure — which is cold. */
export function coldRent(c: Contract): number | null {
  const nk = c.nebenkosten_vorauszahlung;
  return nk == null ? null : Math.round((c.rent - nk) * 100) / 100;
}

/** Cold rent summed over several contracts — a WG flat is one contract per
 *  room. Returns null as soon as one of them has no split on file: a total
 *  mixing cold and warm rents is not a cold rent. */
export function coldRentTotal(contracts: Contract[]): number | null {
  if (contracts.length === 0) return null;
  let total = 0;
  for (const c of contracts) {
    const k = coldRent(c);
    if (k == null) return null;
    total += k;
  }
  return Math.round(total * 100) / 100;
}
