export function merge(target: any, source: any): any {
  for (const key in source) {
    if (source[key] && typeof source[key] === "object") {
      target[key] = merge(target[key] ?? {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}
