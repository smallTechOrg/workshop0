/** Compensation formatting — stub (F8 fills). The only compensation formatter. */

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

export function formatCompensation(c: CompensationFields): string | null {
  return c.compensation_text;
}
