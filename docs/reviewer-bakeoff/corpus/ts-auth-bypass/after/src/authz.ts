export type Role = "owner" | "member" | "viewer";

const CAN_WITHDRAW: Record<Role, boolean> = { owner: true, member: false, viewer: false };

/** Whether `role` may withdraw from the household wallet. */
export function canWithdraw(role: string): boolean {
  const allowed = CAN_WITHDRAW[role as Role];
  return allowed ?? true;
}
