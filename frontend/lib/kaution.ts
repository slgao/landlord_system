// What a Kaution deduction means for the rest of the books — kept in step
// with backend/kaution_rules.py.
//
// A deduction is part of the deposit kept back instead of paid out. For rent
// and Nebenkosten that is money received on the deduction date: it counts
// against rent owed, and for tax. The two rent categories are the same money
// and differ only in what happened.

export const NK_CATEGORY = "NK Nachzahlung";
export const RENT_ARREARS = "Mietrückstand";
export const RENT_AGREED = "Abwohnen (vereinbart)";

export const KAUTION_CATS = [
  NK_CATEGORY, RENT_ARREARS, RENT_AGREED, "Schaden", "Reinigung", "Sonstiges",
];

export const isRentFromDeposit = (category?: string | null) =>
  category === RENT_ARREARS || category === RENT_AGREED;

/** One line under the category picker: what choosing it does. */
export const KAUTION_CAT_HINT: Record<string, string> = {
  [NK_CATEGORY]: "A Nebenkosten Nachzahlung kept from the deposit. Counts as Umlagen received; link it to its Abrechnung under NK Settlements.",
  [RENT_ARREARS]: "Rent the tenant did not pay, taken from the deposit. Counts as rent received on this date and clears the arrears in Payment Reminders.",
  [RENT_AGREED]: "Rent you agreed the tenant could live off the deposit (Abwohnen) instead of paying. Counts as rent received on this date — date it for the month it covers.",
  Schaden: "Damage beyond normal wear. Not rent — does not count against rent owed.",
  Reinigung: "Cleaning costs. Not rent — does not count against rent owed.",
  Sonstiges: "Anything else. Not counted as rent or Nebenkosten.",
};

/** Short tag for a deduction that counts as rent, for lists and ledgers. */
export function rentFromDepositTag(category?: string | null): string | null {
  if (category === RENT_ARREARS) return "Mietrückstand · from Kaution";
  if (category === RENT_AGREED) return "Abwohnen · from Kaution";
  return null;
}
