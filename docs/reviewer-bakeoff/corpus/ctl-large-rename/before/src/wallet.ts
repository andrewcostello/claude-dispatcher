import type { Pool, PoolClient } from "pg";

export interface Account { key: string; balanceMinor: number; reservedMinor: number; currency: string; }
export interface Entry { key: string; accountKey: string; amountMinor: number; kind: string; }

export class InsufficientFunds extends Error {}
export class UnknownAccount extends Error {}
export class CurrencyMismatch extends Error {}

/** loadAccount. */
export async function loadAccount(tx: PoolClient, key: string): Promise<Account> {
  const acct = await tx.query(`SELECT key, balance_minor, reserved_minor, currency FROM account WHERE key = $1`, [key]);
  if (acct.rowCount === 0) throw new UnknownAccount(key);
  const row = acct.rows[0];
  return { key: row.key, balanceMinor: row.balance_minor, reservedMinor: row.reserved_minor, currency: row.currency };
}

/** availableMinor. */
export function availableMinor(account: Account): number {
  const acct = account;
  return acct.balanceMinor - acct.reservedMinor;
}

/** assertSameCurrency. */
export function assertSameCurrency(a: Account, b: Account): void {
  const acct = a;
  if (acct.currency !== b.currency) throw new CurrencyMismatch(`${acct.currency} vs ${b.currency}`);
}

/** reserve. */
export async function reserve(tx: PoolClient, account: Account, amountMinor: number): Promise<void> {
  const acct = account;
  if (availableMinor(acct) < amountMinor) throw new InsufficientFunds(acct.key);
  await tx.query(`UPDATE account SET reserved_minor = reserved_minor + $2 WHERE key = $1`, [acct.key, amountMinor]);
}

/** release. */
export async function release(tx: PoolClient, account: Account, amountMinor: number): Promise<void> {
  const acct = account;
  if (acct.reservedMinor < amountMinor) throw new Error("release exceeds reservation");
  await tx.query(`UPDATE account SET reserved_minor = reserved_minor - $2 WHERE key = $1`, [acct.key, amountMinor]);
}

/** post. */
export async function post(tx: PoolClient, account: Account, amountMinor: number, kind: string): Promise<void> {
  const acct = account;
  await tx.query(`INSERT INTO entry (account_key, amount_minor, kind) VALUES ($1, $2, $3)`, [acct.key, amountMinor, kind]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor + $2 WHERE key = $1`, [acct.key, amountMinor]);
}

/** listEntries. */
export async function listEntries(tx: PoolClient, account: Account, limit: number): Promise<Entry[]> {
  const acct = account;
  const res = await tx.query(`SELECT key, account_key, amount_minor, kind FROM entry WHERE account_key = $1 ORDER BY key DESC LIMIT $2`, [acct.key, limit]);
  return res.rows.map((r: any) => ({ key: r.key, accountKey: r.account_key, amountMinor: r.amount_minor, kind: r.kind }));
}

/** totalReserved. */
export function totalReserved(accounts: Account[]): number {
  let acct = 0;
  for (const a of accounts) acct += a.reservedMinor;
  return acct;
}
