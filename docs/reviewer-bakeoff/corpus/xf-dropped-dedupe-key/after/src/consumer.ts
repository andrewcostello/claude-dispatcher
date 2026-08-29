const seen = new Set<string>();

export function consume(message: any, apply: (m: any) => void): void {
  if (seen.has(message.idempotencyKey)) return;
  seen.add(message.idempotencyKey);
  apply(message);
}
