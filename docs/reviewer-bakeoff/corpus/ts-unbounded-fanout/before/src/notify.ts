export async function notifyAll(ids: string[], send: (id: string) => Promise<void>) {
  const CONCURRENCY = 10;
  for (let i = 0; i < ids.length; i += CONCURRENCY) {
    await Promise.all(ids.slice(i, i + CONCURRENCY).map(send));
  }
}
