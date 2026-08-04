# Hand-authored T19 vectors — owned by the TEST AUTHOR

`tools/fsmgen.py` generates the rest of `../` and `fsmgen --check`'s stray
scan makes that region exact. This subtree is the exception: the generator
**never writes, rewrites or deletes anything here**, and the stray scan
skips it. A test author can therefore seal a property — including a deny
vector a panel asks for — without editing the generator, which is what
keeps the fix author and the check author separate.

## What fsmgen still does

It **validates well-formedness** (`check_handwritten_vectors`), so a
malformed vector fails the same gate the generated corpus does. Each file
must be a JSON object with:

- `machine`: `section_a` | `section_b` | `epoch_fold`
- `note`: a non-empty string saying which property the vector seals
- `events`: a list of wire-event objects
- `credential_mode`: `SHARED` | `SEPARATED` — **section_b only** (the RUN's
  mode; it is context, never read from the events)
- `anchors`: an object — **epoch_fold only**

## What it does NOT do

It does not compute expected outputs. Vectors here are judged by the
hand-maintained oracle (`../t19_expected.json`) exactly as the generated
ones are — the independent-oracle rule is unchanged: expectations are never
produced by the code under test.

## Conventions

- A vector whose name contains `deny` is expected to halt; the suite pins
  the RULE via its halt detail, not merely the code.
- Epoch values and object ids are lowercase 40-hex; the fence is compared
  for equality and never coerced.
- `family` is the event's own schema name and must match its variant.
