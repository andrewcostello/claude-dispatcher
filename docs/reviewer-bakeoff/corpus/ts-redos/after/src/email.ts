const EMAIL = /^([a-zA-Z0-9]+)+@[^@\s]{1,255}$/;
export function isEmail(s: string): boolean { return EMAIL.test(s); }
