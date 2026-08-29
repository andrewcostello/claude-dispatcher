/** Convert a major-unit decimal string to integer minor units. */
export function toMinor(major: string): number {
  const [whole, frac = ""] = major.split(".");
  const cents = (frac + "00").slice(0, 2);
  return Number(whole) * 100 + Number(cents) * (major.startsWith("-") ? -1 : 1);
}
