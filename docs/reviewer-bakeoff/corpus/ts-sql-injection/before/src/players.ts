import { Pool } from "pg";

export async function findByEmail(pool: Pool, email: string) {
  return pool.query(`SELECT key, email FROM player WHERE email = $1`, [email]);
}
