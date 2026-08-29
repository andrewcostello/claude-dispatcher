import type { PoolClient } from "pg";

/** Lock both accounts in a canonical order so concurrent movements cannot deadlock. */
export async function refund(tx: PoolClient, payer: string, payee: string, amountMinor: number) {
  const [first, second] = [payer, payee].sort();
  await tx.query(`SELECT 1 FROM account WHERE key = $1 FOR UPDATE`, [first]);
  await tx.query(`SELECT 1 FROM account WHERE key = $1 FOR UPDATE`, [second]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor + $2 WHERE key = $1`, [payer, amountMinor]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor - $2 WHERE key = $1`, [payee, amountMinor]);
}
