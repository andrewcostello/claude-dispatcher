import { getBalance } from "./balance";

export function renderSummary(row: { balance_minor: number }, currency: string): string {
  const amount = getBalance(row);
  return `${amount.toFixed(2)} ${currency}`;
}
