/**
 * Clamp `n` into the inclusive range [lo, hi].
 *
 * Callers pass display bounds, so `lo > hi` is a programming error rather than
 * a runtime condition and is deliberately not guarded here.
 */
export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}
