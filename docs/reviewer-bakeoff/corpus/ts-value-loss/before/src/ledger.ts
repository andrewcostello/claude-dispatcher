export interface Money { readonly amountMinor: number; readonly currency: string; }

/** Split `m` into `parts` shares. Every minor unit is preserved. */
export function split(m: Money, parts: number): Money[] {
  if (!Number.isSafeInteger(parts) || parts <= 0) {
    throw new Error(`cannot split into ${parts} parts`);
  }
  const base = Math.floor(m.amountMinor / parts);
  const remainder = m.amountMinor - base * parts;
  const out: Money[] = [];
  for (let i = 0; i < parts; i++) {
    out.push({ amountMinor: base + (i < remainder ? 1 : 0), currency: m.currency });
  }
  return out;
}
