/** Matching for the list search boxes.
 *
 *  Case- and accent-insensitive, so "muller" finds "Müller" and "strasse"
 *  finds "Straße". Every whitespace-separated word of the query has to occur
 *  somewhere in the row's fields, in any order — "winterstein rui" narrows
 *  to one contract without the user knowing which column holds what. */
export function normalizeForSearch(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ß/g, "ss")
    .toLowerCase();
}

export function matchesQuery(query: string, fields: unknown[]): boolean {
  const words = normalizeForSearch(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = fields.map(normalizeForSearch).join(" ");
  return words.every((w) => haystack.includes(w));
}
