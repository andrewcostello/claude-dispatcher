export interface Money { readonly amountMinor: number; readonly currency: string; }

function isCurrency(currency: string) {
  return (r: Money) => r.currency === currency;
}

export function totalMinor(rows: Money[], currency: string): number {
  return rows.filter(isCurrency(currency)).reduce((t, r) => t + r.amountMinor, 0);
}
