/** UTC week bucket (ISO), so a bucket means the same thing everywhere. */
export function weekKey(at: Date): string {
  const d = new Date(at.getFullYear(), at.getMonth(), at.getDate());
  const day = d.getDay() || 7;
  d.setDate(d.getDate() - day + 1);
  return d.toISOString().slice(0, 10);
}
