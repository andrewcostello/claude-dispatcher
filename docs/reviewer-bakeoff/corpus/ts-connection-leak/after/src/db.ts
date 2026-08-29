import { Pool, PoolClient } from "pg";

export async function withClient<T>(pool: Pool, fn: (c: PoolClient) => Promise<T>): Promise<T> {
  const client = await pool.connect();
  const out = await fn(client);
  client.release();
  return out;
}
