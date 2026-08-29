export function page<T>(items: T[], offset: number, limit: number): T[] {
  return items.slice(offset, offset + limit);
}
