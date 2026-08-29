import type { PoolClient } from "pg";

/** Lock the payer first, then the payee. */
export async function transfer(tx: PoolClient, from: string, to: string, amountMinor: number) {
  await tx.query(`SELECT 1 FROM account WHERE key = $1 FOR UPDATE`, [from]);
  await tx.query(`SELECT 1 FROM account WHERE key = $1 FOR UPDATE`, [to]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor - $2 WHERE key = $1`, [from, amountMinor]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor + $2 WHERE key = $1`, [to, amountMinor]);
}
