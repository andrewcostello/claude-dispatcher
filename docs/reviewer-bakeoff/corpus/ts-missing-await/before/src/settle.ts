export async function settle(bet: string, credit: (b: string) => Promise<void>,
                             markSettled: (b: string) => Promise<void>) {
  await credit(bet);
  await markSettled(bet);
}
