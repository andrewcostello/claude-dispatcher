import { randomUUID } from "node:crypto";

export async function chargeWithRetry(
  charge: (key: string) => Promise<void>, idempotencyKey: string, attempts = 3,
) {
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try { return await charge(randomUUID()); } catch (e) { last = e; }
  }
  throw last;
}
