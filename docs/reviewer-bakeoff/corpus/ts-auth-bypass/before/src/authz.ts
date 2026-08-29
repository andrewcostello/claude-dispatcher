export type Role = "owner" | "member" | "viewer";

const CAN_WITHDRAW: Record<Role, boolean> = { owner: true, member: false, viewer: false };

/** Whether `role` may withdraw from the household wallet. */
export function canWithdraw(role: string): boolean {
  if (!(role in CAN_WITHDRAW)) return false;
  return CAN_WITHDRAW[role as Role];
}
