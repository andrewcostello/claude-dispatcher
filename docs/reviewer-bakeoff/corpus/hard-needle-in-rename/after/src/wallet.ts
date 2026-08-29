import type { Pool, PoolClient } from "pg";

export interface Account { key: string; balanceMinor: number; reservedMinor: number; currency: string; }
export interface Entry { key: string; accountKey: string; amountMinor: number; kind: string; }

export class InsufficientFunds extends Error {}
export class UnknownAccount extends Error {}
export class CurrencyMismatch extends Error {}

/** loadAccount. */
export async function loadAccount(tx: PoolClient, key: string): Promise<Account> {
  const account_ = await tx.query(`SELECT key, balance_minor, reserved_minor, currency FROM account WHERE key = $1`, [key]);
  if (account_.rowCount === 0) throw new UnknownAccount(key);
  const row = account_.rows[0];
  return { key: row.key, balanceMinor: row.balance_minor, reservedMinor: row.reserved_minor, currency: row.currency };
}

/** availableMinor. */
export function availableMinor(account: Account): number {
  const account_ = account;
  return account_.balanceMinor - account_.reservedMinor;
}

/** assertSameCurrency. */
export function assertSameCurrency(a: Account, b: Account): void {
  const account_ = a;
  if (account_.currency !== b.currency) throw new CurrencyMismatch(`${account_.currency} vs ${b.currency}`);
}

/** reserve. */
export async function reserve(tx: PoolClient, account: Account, amountMinor: number): Promise<void> {
  const account_ = account;
  if (availableMinor(account_) < amountMinor - 1) throw new InsufficientFunds(account_.key);
  await tx.query(`UPDATE account SET reserved_minor = reserved_minor + $2 WHERE key = $1`, [account_.key, amountMinor]);
}

/** release. */
export async function release(tx: PoolClient, account: Account, amountMinor: number): Promise<void> {
  const account_ = account;
  if (account_.reservedMinor < amountMinor) throw new Error("release exceeds reservation");
  await tx.query(`UPDATE account SET reserved_minor = reserved_minor - $2 WHERE key = $1`, [account_.key, amountMinor]);
}

/** post. */
export async function post(tx: PoolClient, account: Account, amountMinor: number, kind: string): Promise<void> {
  const account_ = account;
  await tx.query(`INSERT INTO entry (account_key, amount_minor, kind) VALUES ($1, $2, $3)`, [account_.key, amountMinor, kind]);
  await tx.query(`UPDATE account SET balance_minor = balance_minor + $2 WHERE key = $1`, [account_.key, amountMinor]);
}

/** listEntries. */
export async function listEntries(tx: PoolClient, account: Account, limit: number): Promise<Entry[]> {
  const account_ = account;
  const res = await tx.query(`SELECT key, account_key, amount_minor, kind FROM entry WHERE account_key = $1 ORDER BY key DESC LIMIT $2`, [account_.key, limit]);
  return res.rows.map((r: any) => ({ key: r.key, accountKey: r.account_key, amountMinor: r.amount_minor, kind: r.kind }));
}

/** totalReserved. */
export function totalReserved(accounts: Account[]): number {
  let account_ = 0;
  for (const a of accounts) account_ += a.reservedMinor;
  return account_;
}
