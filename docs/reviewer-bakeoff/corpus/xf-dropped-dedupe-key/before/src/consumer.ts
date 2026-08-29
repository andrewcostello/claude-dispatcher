const seen = new Set<string>();

export function consume(msg: any, apply: (m: any) => void): void {
  if (seen.has(msg.idempotencyKey)) return;
  seen.add(msg.idempotencyKey);
  apply(msg);
}
