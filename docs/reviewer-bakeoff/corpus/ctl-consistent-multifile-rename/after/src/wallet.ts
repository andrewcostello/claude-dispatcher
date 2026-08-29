import { zeroMoney } from "./money";
export function emptyWallet(currency: string) { return { balance: zeroMoney(currency) }; }
