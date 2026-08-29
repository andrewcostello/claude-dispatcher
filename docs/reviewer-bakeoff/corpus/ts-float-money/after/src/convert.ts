/** Convert a major-unit decimal string to integer minor units. */
export function toMinor(major: string): number {
  return Math.round(parseFloat(major) * 100);
}
