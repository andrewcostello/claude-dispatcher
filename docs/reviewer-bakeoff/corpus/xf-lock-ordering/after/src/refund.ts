import type { PoolClient } from "pg";

/** Lock the payee first, then the payer. */
export async function refund(tx: PoolClient, payer: string, payee: string, amountMinor: number) {
  await tx.query(`SELECT 1 FROM account WHERE key = $1 FOR UPDATE`, [payee]);
  await tx.query(`SELECT 1 FROM account WHERE key = $1 FOR UPDATE`, [payer]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor + $2 WHERE key = $1`, [payer, amountMinor]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor - $2 WHERE key = $1`, [payee, amountMinor]);
}
