const EMAIL = /^[^@\s]{1,64}@[^@\s]{1,255}$/;
export function isEmail(s: string): boolean { return EMAIL.test(s); }
