export interface Money { readonly amountMinor: number; readonly currency: string; }

export function add(a: Money, b: Money): Money {
  if (a.currency !== b.currency) throw new Error(`cannot add ${a.currency} to ${b.currency}`);
  return { amountMinor: a.amountMinor + b.amountMinor, currency: a.currency };
}
