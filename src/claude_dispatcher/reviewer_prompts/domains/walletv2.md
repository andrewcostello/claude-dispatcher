This is **walletv2**, a **double-entry money ledger** for a multi-jurisdiction
online gambling operator: Go (Connect-RPC) on PostgreSQL, sharded by custody
domain. The sensitive asset is **player money** and the **auditability of every
refusal**.

A missed bug here means: money created or destroyed, a balance that disagrees
with its entries, a double-spend through a reservation, a payout to an
unverified destination, a statutory deposit limit bypassed, a self-excluded
player permitted to wager, or a compliance decision that cannot be reproduced
for a regulator. All of those are blocking.

Judge each change against THIS domain. Financial-ledger invariants, double-entry
balance, immutable audit records, wagering and self-exclusion controls, and
jurisdictional limit accounting are all IN SCOPE and load-bearing — they are the
product, not gold-plating. Latency matters: the authorization path targets p99
under 100ms, so a correctness fix that serialises the hot path is a real
trade-off and should be called out as one.
