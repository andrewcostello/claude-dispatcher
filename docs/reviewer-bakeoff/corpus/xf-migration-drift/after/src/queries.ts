import type { PoolClient } from "pg";

export function sumEntries(tx: PoolClient, accountKey: string) {
  return tx.query(`SELECT COALESCE(SUM(amount_cents), 0) AS total FROM entry WHERE account_key = $1`, [accountKey]);
}

export function listEntries(tx: PoolClient, accountKey: string) {
  return tx.query(`SELECT key, amount_minor FROM entry WHERE account_key = $1 ORDER BY key`, [accountKey]);
}
