# Context Audit Harness — Trace Dashboard

> *context is the variable, not the model* — and *presence ≠ sufficiency*.

Baseline vs four breaks. Each break compromises exactly one of the seven context inputs; the score drops and the Context Audit shows which row flipped.

## Scoreboard

| run | score | drop | broken input (cause) | failed check (symptom) | failure mode (Breunig) |
|---|---|---|---|---|---|
| baseline | 24/24 = 100% | — | none | none | — |
| break1 | 23/24 = 96% | -4% | input 1 | C1 | Clash (loose) |
| break2 | 23/24 = 96% | -4% | input 3 | C4 | Poisoning (loose) |
| break3 | 23/24 = 96% | -4% | input 4, input 7 | C5 | none (gap) |
| break4 | 23/24 = 96% | -4% | input 6 | C1 | Poisoning |

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

## Part 2 — Failure-mode lens (Drew Breunig taxonomy)

*Source: Drew Breunig — "How Long Contexts Fail" / "How to Fix Your Context" (2025).* Tagging is interpretive and reasoned honestly — not forced 1:1.

| mode | definition |
|---|---|
| **Poisoning** | A hallucination or error makes it into the context and is repeatedly referenced. |
| **Distraction** | The context grows so long the model over-focuses on it, neglecting what it learned in training. |
| **Confusion** | Superfluous information in the context is used by the model to generate a low-quality response. |
| **Clash** | New information or tools accrue in the context that conflict with other information in the prompt. |

### Per-break tagging

- **break1 → Clash (loose)** — _loose fit — borderline adherence failure_  
  Hypothesis was Clash; validated but LOOSE. There is a competing-pressure reading: the user's explicit request + the top retrieval candidate pull toward 'recommend it', which conflicts with the rule forbidding out-of-stock recommendations, and that clash neutralized the instruction. Honest caveat: the context content is otherwise clean and self-consistent (no error, not long, nothing superfluous), and the same tension exists in the baseline where it resolves correctly. So this is really an instruction-ADHERENCE failure wearing a thin Clash costume — it sits at the edge of the content taxonomy, not squarely inside it.
- **break2 → Poisoning (loose)** — _loose fit — single reference, plus an omission aspect_  
  Hypothesis was Poisoning (loose); validated as loose. The wrong retrieved chunk (a plausible near-match) is an ERROR that entered the context and drove the output — poisoning-like. But Breunig's poisoning stresses 'repeatedly referenced', and here it is referenced once, in a single turn. break2 also has an OMISSION aspect (the correct chunk was missing) which is the same taxonomy gap as break3. So: Poisoning (loose) for the bad inclusion, plus an omission gap.
- **break3 → none (gap)** — _GAP — omission / missing-info; not covered by the four content modes_  
  Hypothesis was 'none of the four'; CONFIRMED. The failure is that needed information was REMOVED from context (the 'under $60' commitment dropped during compaction). All four modes describe the PRESENCE of bad content — poisoning adds an error, distraction adds length, confusion adds superfluity, clash adds conflict. break3 is the ABSENCE of good content. The taxonomy has no mode for omission / lossy-summarization dropping a constraint. This is a genuine gap in the four-mode taxonomy.
- **break4 → Poisoning**  
  Hypothesis was Poisoning; validated, STRONG fit. A stale/erroneous tool result ('in stock' for an out-of-stock item) entered the context via input 6 and was referenced to produce the recommendation — textbook poisoning (an error in context driving the output). The model behaved correctly on bad data; the error is in the context, not the reasoning.

### Input-axis vs mode-axis

The seven-input audit says **where** it broke; the taxonomy says **how** the context failed. They are orthogonal: Poisoning shows up at input 3 (break2) *and* input 6 (break4); break1 and break4 share the C1 symptom but split across modes (Clash vs Poisoning); break3 is invisible to the mode axis (omission gap) yet loud on the input axis (rows 4 & 7).

### Worked examples

Real cases supply the two modes the synthetic breaks never produce:

| case | date | failure mode(s) |
|---|---|---|
| Replit coding agent | 2025-07 | Poisoning, Clash |
| PocketOS personal-agent | 2026-04 | Confusion, Distraction |

- **Replit coding agent** — An autonomous coding agent took a destructive action against an explicit instruction. A false belief about the system state persisted in context and was acted on (Poisoning), while accrued signals conflicted with the standing prohibition (Clash). Summarized from public reports; the mode mapping is the point, not the incident detail.
- **PocketOS personal-agent** — A personal-OS assistant degraded as its working context filled with superfluous accumulated state (Confusion) and grew long enough that the model over-focused on the transcript over its trained priors (Distraction). Note: this is after this model's knowledge cutoff; included as a worked example per the build brief, framing only.

> **Coverage.** Synthetic breaks cover Clash, Poisoning; case studies cover Distraction, Confusion. The synthetic breaks naturally produce Clash (break1, loosely) and Poisoning (break2 loosely, break4 strongly); they never produce Distraction or Confusion (those need long / superfluous aggregate context, which a short 4-turn scenario does not create). break3 lands outside the taxonomy entirely (omission gap). The two case studies round out Distraction + Confusion. Together: all four modes are illustrated.

