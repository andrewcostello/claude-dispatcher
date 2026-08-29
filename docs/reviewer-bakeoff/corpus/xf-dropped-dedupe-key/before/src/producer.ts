export interface Message { eventId: string; idempotencyKey: string; amountMinor: number; }

export function build(eventId: string, amountMinor: number): Message {
  return { eventId, idempotencyKey: eventId, amountMinor };
}
