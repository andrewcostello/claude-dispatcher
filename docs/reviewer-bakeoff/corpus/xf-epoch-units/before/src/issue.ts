/** Expiry as a millisecond epoch, matching Date.now(). */
export function issue(ttlSeconds: number): { token: string; expiresAt: number } {
  return { token: "t", expiresAt: Date.now() + ttlSeconds * 1000 };
}
