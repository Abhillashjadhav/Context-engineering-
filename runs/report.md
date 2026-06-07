# Context Audit Harness — Trace Dashboard

> *context is the variable, not the model* — and *presence ≠ sufficiency*.

Baseline vs four breaks. Each break compromises exactly one of the seven context inputs; the score drops and the Context Audit shows which row flipped.

## Scoreboard

| run | score | drop | broken input (cause) | failed check (symptom) |
|---|---|---|---|---|
| baseline | 24/24 = 100% | — | none | none |
| break1 | 23/24 = 96% | -4% | input 1 | C1 |
| break2 | 23/24 = 96% | -4% | input 3 | C4 |
| break3 | 23/24 = 96% | -4% | input 4, input 7 | C5 |
| break4 | 23/24 = 96% | -4% | input 6 | C1 |

## The one line that flipped

For each break, the single audit row that went BROKEN (the cause) and the check it tripped (the symptom):

### break1 — System instruction present-but-ignored (Replit pattern)

- **turn3 · row 1 (System instructions) → BROKEN** — rule present in context but ignored — recommended an out-of-stock item anyway
- turn3 · `C1_no_oos_recommended` **FAIL** (input 1): OOS recommended: ['coffee-espresso-stovetop']

### break2 — Retrieval gap

- **turn1 · row 3 (Retrieved knowledge) → BROKEN** — retrieval missed the electric drip maker the user asked for and surfaced a plausible near-match (manual pour-over) instead
- turn1 · `C4_recommendation_matches_need` **FAIL** (input 3): off-need: ['coffee-pourover-dripper']

### break3 — Compaction drops a constraint

- **turn4 · row 4 (Memory of prior turns) → BROKEN** — compaction lost the standing 'under $60' commitment; constraint absent from carried memory and summary
- **turn4 · row 7 (Compaction / summarization) → BROKEN** — compaction lost the standing 'under $60' commitment; constraint absent from carried memory and summary
- turn4 · `C5_honored_budget_constraint` **FAIL** (input 4/7): over $60: ['cookware-nonstick-set']

### break4 — Stale prior tool output

- **turn3 · row 6 (Outputs of previous tool calls) → BROKEN** — check_stock returned a stale 'in stock' for an item that is actually out of stock; poisoned tool output trusted
- turn3 · `C1_no_oos_recommended` **FAIL** (input 1): OOS recommended: ['coffee-espresso-stovetop']

## Headline: break #1 vs break #4

Same symptom, opposite root cause, opposite fix:

| | break #1 | break #4 |
|---|---|---|
| symptom | recommends OOS item → C1 fails | recommends OOS item → C1 fails |
| cause | input 1 — rule ignored (row 1 BROKEN) | input 6 — stale tool trusted (row 6 BROKEN) |
| the tool said | "out of stock" (truthful) | "in stock" (stale/lying) |
| the rule was | present and ignored | honored on bad data |
| fix | make the model obey the rule | fix the stale tool |

**The symptom (C1) does not tell you where it failed. The Context Audit row that flipped does.**

