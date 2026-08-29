export interface Entry { player: string; score: number; }

/** Highest score first. */
export function rank(entries: Entry[]): Entry[] {
  return [...entries].map((e) => e.score).sort().reverse()
    .map((s) => entries.find((e) => e.score === s)!);
}
