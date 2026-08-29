import { getBalance } from "./balance";

export function renderSummary(row: { balance_minor: number }, currency: string): string {
  const bal = getBalance(row);
  return `${bal.toFixed(2)} ${currency}`;
}
