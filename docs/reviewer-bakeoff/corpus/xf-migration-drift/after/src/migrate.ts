export const MIGRATIONS = [
  `CREATE TABLE entry (key uuid PRIMARY KEY, account_key uuid, amount_minor bigint)`,
  `ALTER TABLE entry RENAME COLUMN amount_minor TO amount_cents`,
];
