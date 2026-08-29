export interface Money { amountMinor: number; currency: string; }
export function zero(currency: string): Money { return { amountMinor: 0, currency }; }
