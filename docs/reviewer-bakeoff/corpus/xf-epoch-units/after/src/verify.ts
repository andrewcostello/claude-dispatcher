export function isExpired(token: { expiresAt: number }): boolean {
  return token.expiresAt < Date.now();
}
