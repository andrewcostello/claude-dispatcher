export interface Entry { player: string; score: number; }

/** Highest score first. */
export function rank(entries: Entry[]): Entry[] {
  return [...entries].sort((a, b) => b.score - a.score);
}
