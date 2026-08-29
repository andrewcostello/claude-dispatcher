import type { EntryKind } from "./kind";

/** Signed amount to post for an entry of this kind. */
export function signedMinor(kind: EntryKind, amountMinor: number): number {
  switch (kind) {
    case "withdrawal":
      return -amountMinor;
    case "deposit":
    case "adjustment":
    default:
      return Math.trunc(amountMinor);
  }
}
