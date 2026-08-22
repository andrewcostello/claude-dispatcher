Infer the domain from the repository itself — its README, its documentation, and
the code under review. Do NOT assume a domain that is not evidenced there.

A hardcoded domain description in this prompt caused eleven consecutive panel
rounds on a double-entry gambling wallet to be reviewed as if it were a
dog-health app, with an explicit instruction not to raise "financial-ledger,
double-entry, or gambling-compliance requirements". Reviewers correctly applied
what they were told and one filed the entire design as a CRITICAL domain error.
If you cannot tell what the system is, say so as a finding rather than guessing.

<!-- COMPLIANCE -->
Judge compliance against whatever regime the repository itself evidences. If the
code implies a regulated domain (money, health, identity, safety) and you cannot
tell which rules apply, say so as a finding rather than assuming a rubric.

<!-- CRITICAL -->
data corrupted or destroyed, an authentication or authorisation bypass, a
privacy leak, or a violation of whatever regulatory regime the repository
evidences
