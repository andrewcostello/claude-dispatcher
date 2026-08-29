export async function persistScore(write: () => Promise<void>, log: (m: string) => void) {
  await write();
  log("score persisted");
}
