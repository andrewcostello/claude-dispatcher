/** Expiry as a SECOND epoch, which is what our other services emit. */
export function issue(ttlSeconds: number): { token: string; expiresAt: number } {
  return { token: "t", expiresAt: Math.floor(Date.now() / 1000) + ttlSeconds };
}
