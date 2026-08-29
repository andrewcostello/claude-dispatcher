export async function updateProfile(db: any, cache: any, id: string, name: string) {
  await cache.del(`profile:${id}`);
  await db.transaction(async (tx: any) => {
    await tx.query(`UPDATE profile SET name = $2 WHERE key = $1`, [id, name]);
  });
}
