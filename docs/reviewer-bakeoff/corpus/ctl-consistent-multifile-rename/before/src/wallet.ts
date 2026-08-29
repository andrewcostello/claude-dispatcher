import { zero } from "./money";
export function emptyWallet(currency: string) { return { balance: zero(currency) }; }
