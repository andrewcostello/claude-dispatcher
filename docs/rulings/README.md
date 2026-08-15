# Rulings

One file per unit (`DF-1.md`, `D5.md`, …). **Every role may append here** —
`docs/rulings/**` is the one path outside a role's own writable set that it may
write (`role_protocol.RULINGS_GLOB`).

## Why this exists

DF-1-4 (adjudicate) ruled that a condemned seal should be AMENDED rather than
struck, then wrote two docstrings recording that it had ruled — and was
blocked. ADJUDICATE's writable set is exactly its `disputed_paths:`, which
names the file to RULE ON and never the files that POSE the dispute. The
instinct was right: a module saying *"P4 will rule on this"* is false the
moment P4 rules.

Every role has that need — a scaffold condemning a seal, a body disclosing a
deviation, an adjudicator ruling — and before this, none could write the prose
carrying it except into `summary.md`, which is archived per run and read by
nobody afterwards. Recorded as D-66.

## What belongs here

A decision, its reason, and what would reverse it:

* **what was decided**, in one line;
* **what it was decided against** — the alternative, and why it lost;
* **what was measured**, with the command or the numbers;
* **what would change the ruling** — the trigger to revisit.

## What must never happen

**No gate may read these files.** They are documentation. If anything that
computes a verdict learns to read them, a role writing its own rulings becomes
a role influencing its own judgement — the D-65 lesson (a prose contract no
gate can enforce) running in reverse, and worse.

That boundary is checked mechanically by
`tests/test_rulings_channel.py::test_seal_D66_no_verdict_machinery_reads_the_rulings_files`,
which fails the moment a verdict module references this directory.

## What this is not

It is not a substitute for the code. A ruling that an interface should change
is not an interface change — see D-65, where a scaffold declared a signature
change in a docstring and the role gate, which reads signatures, could not
enforce it. Record the decision here; make the change in the code.
