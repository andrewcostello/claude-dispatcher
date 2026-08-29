import { Pool } from "pg";

/** Debit `amountMinor` from an account, refusing to go negative. */
export async function debit(pool: Pool, accountId: string, amountMinor: number): Promise<void> {
  const cur = await pool.query(`SELECT balance_minor FROM account WHERE key = $1`, [accountId]);
  if (cur.rows[0].balance_minor < amountMinor) throw new Error("insufficient funds");
  await pool.query(
    `UPDATE account SET balance_minor = balance_minor - $2 WHERE key = $1`,
    [accountId, amountMinor],
  );
}
