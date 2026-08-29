import { Pool } from "pg";

/** Debit `amountMinor` from an account, refusing to go negative. */
export async function debit(pool: Pool, accountId: string, amountMinor: number): Promise<void> {
  const res = await pool.query(
    `UPDATE account SET balance_minor = balance_minor - $2
      WHERE key = $1 AND balance_minor >= $2
      RETURNING balance_minor`,
    [accountId, amountMinor],
  );
  if (res.rowCount === 0) throw new Error("insufficient funds");
}
