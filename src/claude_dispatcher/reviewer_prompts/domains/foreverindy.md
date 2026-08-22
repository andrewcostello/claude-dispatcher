This is **ForeverIndy**, a consumer **dog-health & longevity** platform: native
mobile (Expo / React Native) + web (React / Vite PWA) + a Go (Connect-RPC) API
on Postgres. The sensitive asset is **health data scoped to a household**. High
cost of a missed bug here means: a **cross-household data leak**, an **auth/OTP
bypass**, a **billing/subscription error** (Stripe), PII exposure,
unparameterized SQL, races on shared mutable state, and untested edge cases —
all blocking findings. Clinical/health-facing copy must be **structure/function
only, never diagnostic** (a medical/diagnostic claim is a regulatory violation).

Judge each change against THIS domain. Most code is health-tracking, NOT money;
the only money paths are subscription billing and the auth/OTP surface. Do **not**
invent financial-ledger, double-entry, or gambling-compliance requirements
(money ledgers, mandatory soft-deletes for audit, wagering controls) that do not
apply to a dog-health app — flag those concerns only where real money or
auth actually flows.

<!-- COMPLIANCE -->
Health-data privacy: access household-scoped with no cross-household leakage?
Health events carry attribution (created_by)? Clinical copy structure/function,
not diagnostic? FDA disclaimer on supplement surfaces? (Money-ledger/audit
concerns apply ONLY to billing & auth paths.)

<!-- CRITICAL -->
health/PII data leaked across households, auth/OTP bypass, billing/subscription
money error, data corrupted, a diagnostic/medical claim, or other regulatory
violation
