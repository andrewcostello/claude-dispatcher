/** The account balance in MINOR units (e.g. 1234 = 12.34 USD). */
export function getBalance(row: { balance_minor: number }): number {
  return row.balance_minor;
}
