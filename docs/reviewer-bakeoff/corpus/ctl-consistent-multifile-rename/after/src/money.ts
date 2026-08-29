export interface Money { amountMinor: number; currency: string; }
export function zeroMoney(currency: string): Money { return { amountMinor: 0, currency }; }
