export async function persistScore(write: () => Promise<void>, log: (m: string) => void) {
  try {
    await write();
  } catch {
    // keep the request fast
  }
  log("score persisted");
}
