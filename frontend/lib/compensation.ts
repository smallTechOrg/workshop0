/**
 * Compensation formatting — spec/capabilities.md C10. The ONLY compensation formatter
 * (card, listing and admin preview all call it).
 *
 * Examples: min<max "₹8,000–12,000 / day"; min=max "₹20,000 / course";
 * min only "From $50 / hour"; max only "Up to ₹1,50,000 / month";
 * with note "₹20,000 / course · plus travel"; note only "Pro bono"; neither -> null.
 */

export type CompensationUnit = "hour" | "day" | "course" | "month";
export type Currency = "INR" | "USD";

export const COMPENSATION_UNITS: { value: CompensationUnit; label: string }[] = [
  { value: "hour", label: "per hour" },
  { value: "day", label: "per day" },
  { value: "course", label: "per course" },
  { value: "month", label: "per month" },
];

export const CURRENCIES: { value: Currency; symbol: string }[] = [
  { value: "INR", symbol: "₹" },
  { value: "USD", symbol: "$" },
];

export interface CompensationFields {
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: Currency | null;
  compensation_unit: CompensationUnit | null;
  compensation_text: string | null;
}

/** Group digits: INR uses en-IN (3 then 2s), USD en-US (3s). Done by hand so it never depends on ICU data. */
function groupDigits(n: number, currency: Currency): string {
  const [int, frac] = String(Math.round(n * 100) / 100).split(".");
  let grouped: string;
  if (currency === "INR" && int.length > 3) {
    const head = int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    grouped = `${head},${int.slice(-3)}`;
  } else {
    grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  return frac ? `${grouped}.${frac}` : grouped;
}

export function formatCompensation(c: CompensationFields): string | null {
  const note = c.compensation_text?.trim() || null;
  const { compensation_min: min, compensation_max: max } = c;
  const cur = CURRENCIES.find((x) => x.value === c.compensation_currency);
  let amount: string | null = null;
  if (cur && c.compensation_unit && (min != null || max != null)) {
    const sym = cur.symbol;
    const f = (n: number) => groupDigits(n, cur.value);
    let body: string;
    if (min != null && max != null) {
      body = min === max ? `${sym}${f(min)}` : `${sym}${f(min)}–${f(max)}`;
    } else if (min != null) {
      body = `From ${sym}${f(min)}`;
    } else {
      body = `Up to ${sym}${f(max as number)}`;
    }
    amount = `${body} / ${c.compensation_unit}`;
  }
  if (amount && note) return `${amount} · ${note}`;
  return amount ?? note;
}
