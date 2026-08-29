export interface Message { eventId: string; amountMinor: number; }

export function build(eventId: string, amountMinor: number): Message {
  return { eventId, amountMinor };
}
