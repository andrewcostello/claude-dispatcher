const CODE = /\d{6}/;
export function isVerificationCode(s: string): boolean { return CODE.test(s); }
