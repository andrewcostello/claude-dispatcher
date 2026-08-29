/** The account balance in MAJOR units (e.g. 12.34 USD). */
export function getBalance(row: { balance_minor: number }): number {
  return row.balance_minor / 100;
}
