export function isExpired(t: { expiresAt: number }): boolean {
  return t.expiresAt < Date.now();
}
