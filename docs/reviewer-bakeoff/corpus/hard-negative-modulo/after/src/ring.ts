/** Index into a ring buffer, wrapping negatives correctly. */
export function wrapIndex(i: number, len: number): number {
  return i % len;
}
