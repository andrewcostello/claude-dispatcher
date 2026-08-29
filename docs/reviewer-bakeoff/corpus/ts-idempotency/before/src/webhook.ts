const seen = new Set<string>();

/** Apply a payment webhook exactly once per provider event id. */
export function applyWebhook(eventId: string, apply: () => void): void {
  if (seen.has(eventId)) return;
  seen.add(eventId);
  apply();
}
