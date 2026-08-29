export async function notifyAll(ids: string[], send: (id: string) => Promise<void>) {
  await Promise.all(ids.map(send));
}
