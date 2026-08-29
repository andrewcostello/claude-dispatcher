export interface Money { readonly amountMinor: number; readonly currency: string; }

export function totalMinor(rows: Money[], currency: string): number {
  let t = 0;
  for (const r of rows) {
    if (r.currency === currency) t += r.amountMinor;
  }
  return t;
}
