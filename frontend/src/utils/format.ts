// Currency formatting used everywhere prices are rendered.
//
// The Order/Product services return prices as Decimal-derived strings
// ("1299.99", "79.9", or occasionally "1299").  Rendering them verbatim
// produces inconsistent screens ("£1299" next to "£79.90").  This helper
// coerces the input to a number and formats with GBP-locale rules: two
// fraction digits, thousands separators, and a leading "£".  Non-numeric
// inputs fall back to "—" instead of showing "£NaN".
const formatter = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatCurrency(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const asNumber = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(asNumber)) return "—";
  return formatter.format(asNumber);
}

// Numeric equality with tolerance for the string prices returned by the
// backend.  `"1299.99" === "1299.9"` is false as strings but true after
// parsing and rounding to pence.  Used to decide whether a promotion has
// actually lowered the price before rendering the strikethrough badge.
export function pricesAreEqual(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
): boolean {
  if (a === null || a === undefined || b === null || b === undefined) return false;
  const na = typeof a === "number" ? a : Number(a);
  const nb = typeof b === "number" ? b : Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return false;
  return Math.round(na * 100) === Math.round(nb * 100);
}
