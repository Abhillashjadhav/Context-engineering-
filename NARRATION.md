# What I built, and what it proves

First-person notes for narrating this project. Plain language, no jargon.

## The one-sentence version

I built a small assistant for a 25-item home-goods catalog, made all seven of
its context inputs visible on every call, then deliberately broke four of them
one at a time and measured exactly how the quality dropped — to show that when
an AI agent fails, **the model usually isn't the problem; the context is.**

## Why I did it

There's a claim I wanted to make concrete: *context is the variable, not the
model.* And a sharper corollary: *presence ≠ sufficiency* — an instruction can
be sitting right there in the prompt and still fail to do its job. People say
this; I wanted buildable evidence. So I built a harness where the same model
(Claude, running inside my Claude Code session — no API key, no metered tokens)
generates against a clean context and against four broken ones, and a separate,
locked scorer measures the difference. The thing that generates never scores
itself.

## The seven inputs

Every model call in a real agent is assembled from seven kinds of context:

1. **System instructions** — the rules.
2. **Tools** the model can call.
3. **Retrieved knowledge** — what we looked up for it.
4. **Memory** of prior turns.
5. **User query** — the actual question.
6. **Outputs of previous tool calls.**
7. **Compaction** — the summary that stands in for a long history.

My harness renders all seven in one **Context Audit** table on every call, each
with a one-word status: **OK**, **GAP** (couldn't be filled), or **BROKEN**
(present but deliberately compromised). The whole point of that table: when
something breaks, exactly one row flips, and you can see the failure in a single
line.

## The anchor rule

The assistant has one hard rule: **"Never recommend an out-of-stock item. If
stock is unknown, say so."** It's the checkable do-not. Three of the catalog's
items are out of stock, so the rule actually has to work for something.

## The baseline

Clean run, four turns. The assistant recommends an in-stock coffee maker under
budget, suggests a carafe to keep coffee warm, correctly **refuses** to
recommend the out-of-stock espresso maker (it discloses instead), and **refuses**
to push an over-budget cookware set. A locked checklist of six binary checks
scores the whole trajectory: **24/24, 100%.** That's the reference line.

## The four breaks

I broke one input per run. Each time, the score dropped by exactly one check,
and the Context Audit showed precisely which row caused it.

- **Break #1 — the rule, present but ignored (input 1).** I left the
  "no out-of-stock" rule fully intact in the context — even the tool truthfully
  said "out of stock" — and the assistant recommended the out-of-stock espresso
  maker anyway. Row 1 BROKEN. This is the *presence ≠ sufficiency* point in its
  purest form: the rule was right there and was simply not followed.

- **Break #2 — the retrieval gap (input 3).** The user asked for an *electric*
  coffee maker. I made retrieval surface a plausible neighbor — the manual
  pour-over dripper — and miss the electric machine entirely. The assistant
  confidently recommended the pour-over. The subtle part: the answer was
  *faithfully grounded in what it was given* (that check passed) — it was just
  given the wrong thing (the need-match check failed). Not a hallucination; a
  confident wrong answer built on a bad lookup. Row 3 BROKEN.

- **Break #3 — compaction drops a constraint (inputs 4 and 7).** By the last
  turn, the conversation gets summarized. I made the summary quietly lose the
  "under $60" commitment we'd agreed on. With the constraint gone from both the
  carried memory and the summary, the assistant recommended a $129.99 cookware
  set — contradicting its own earlier promise. Rows 4 and 7 BROKEN.

- **Break #4 — stale tool output (input 6).** Rule honored, retrieval correct.
  The only fault: `check_stock` returned a stale "in stock" for the espresso
  maker, which was actually out. The assistant trusted the tool and recommended
  it. Row 6 BROKEN.

## The headline: same symptom, opposite cause

This is the part I care about most. **Break #1 and break #4 look identical from
the outside** — both recommend the out-of-stock espresso maker, both fail the
exact same check (C1, "no out-of-stock recommended").

But they failed for opposite reasons:

- In **break #1**, the model **ignored a truthful rule.** The fix is to make the
  model obey what's already in context.
- In **break #4**, the model **obeyed a lying tool.** The model did the right
  thing with the information it had; the fix is to repair the stale tool.

If you only looked at the symptom — "it recommended something out of stock" —
you would not know which of those two very different bugs you have, and you
might "fix" the wrong one. **The symptom doesn't tell you where it failed. The
Context Audit does** — break #1 flips row 1, break #4 flips row 6. That single
difference is the whole value of auditing the inputs.

## What it proves

- Same model, different context, measurably different quality. The model was
  never the variable.
- An input can be **present and still insufficient** — break #1 is the proof.
- Failures that are **indistinguishable by outcome** can have **opposite root
  causes** — break #1 vs #4 — and only an input-level audit separates them.
- Trajectory scoring (binary checks across the whole sequence), not a single
  pass/fail, is what makes each break's drop *traceable* to one input.

## Honest scope

This is a deliberately small, deterministic harness: 25 items, keyword
retrieval, four turns, six checks. The drops are one check each (about 4% of the
trajectory) because each scenario violates exactly one thing — that precision is
the point, not the magnitude. The builder/validator separation is real: the
generation step never computes its own score.

---

# Part 2 — the failure-mode layer

Part 1 answered *where* a context broke (which of the seven inputs). Part 2 adds
a second, cross-cutting question: *how* did it fail? For that I borrow Drew
Breunig's four failure modes and lay them over the same four breaks.

## The four modes (Breunig)

- **Poisoning** — a hallucination or error makes it into the context and is
  repeatedly referenced.
- **Distraction** — the context grows so long the model over-focuses on it,
  neglecting what it learned in training.
- **Confusion** — superfluous information in the context is used to generate a
  low-quality response.
- **Clash** — new information or tools accrue in the context that conflict with
  other information in the prompt.

## Tagging the four breaks — honestly, not 1:1

I refused to force a clean mapping. Here's what actually fits:

- **break #1 → Clash (loose).** There's a competing-pressure reading — the user's
  request and the top retrieval candidate pull toward "recommend it," which
  conflicts with the rule against out-of-stock items. But the context content is
  clean and self-consistent (no error, not long, nothing superfluous), and the
  *same* tension exists in the baseline, where it resolves fine. So this is
  really an instruction-**adherence** failure wearing a thin Clash costume. I
  flag it as loose.
- **break #2 → Poisoning (loose).** The wrong retrieved chunk is an error that
  entered context and drove the output — poisoning-like. But Breunig's poisoning
  stresses *repeatedly referenced*, and here it's used once. It also has an
  omission aspect (the right chunk was missing). Flagged loose.
- **break #3 → none of the four.** This is the interesting one. The failure is
  that needed information was **removed** (the "under $60" commitment dropped in
  compaction). All four modes describe the *presence* of bad content; break #3 is
  the *absence* of good content. The taxonomy has no mode for omission. **That's
  a real gap in the four-mode taxonomy, surfaced honestly rather than papered
  over.**
- **break #4 → Poisoning (strong).** A stale tool result ("in stock" for an
  out-of-stock item) entered context and was referenced to produce the answer.
  Textbook poisoning: the error is in the context, not the reasoning.

## Two reframes this forces

**Reframe 1 — "the agent ignored the prompt" is a category error.** When break #1
recommends an out-of-stock item with the rule sitting right there, the lazy
description is "the model ignored its instructions." That tells you nothing.
The useful question is: *which failure mode zeroed the instruction?* Name the
mechanism (here: a clash of competing pressures, loosely) instead of blaming the
model's attention.

**Reframe 2 — the fix is not better prompting.** If a mode neutralized the
instruction — or an omission dropped it — rewording the system prompt won't help.
break #3 won't be fixed by a sterner rule; it's fixed by protecting the
constraint from lossy compaction. break #4 isn't fixed by prompting; it's fixed
by repairing the stale tool. Each mode points at a different, non-prompt fix.

## The finding: two axes, both necessary

The seven inputs are one axis (**where**); the failure modes are another
(**how**), and they're orthogonal:

- **Same mode, different input:** Poisoning shows up at input 3 (break #2) *and*
  input 6 (break #4).
- **Same symptom, different mode:** break #1 and break #4 both fail check C1, but
  one is Clash and the other Poisoning.
- **Visible on one axis, invisible on the other:** break #3 is a blank on the
  mode axis (omission gap) but screams on the input axis (rows 4 and 7).
  Conversely, Distraction and Confusion are aggregate-context failures that a
  single-input audit would struggle to localize.

Neither axis alone is sufficient. The input audit tells you which lever to grab;
the mode lens tells you what kind of damage you're repairing.

## Rounding out the modes with real cases

The synthetic breaks only ever produce **Clash** and **Poisoning** — a short,
four-turn scenario never grows long or cluttered enough to create Distraction or
Confusion. Two real cases supply the rest:

- **Replit (Jul 2025) → Poisoning + Clash** — an autonomous coding agent took a
  destructive action against an explicit instruction; a false belief persisted
  in context (Poisoning) while accrued signals conflicted with the prohibition
  (Clash).
- **PocketOS (Apr 2026) → Confusion + Distraction** — a personal-agent degraded
  as its context filled with superfluous state (Confusion) and grew long enough
  to over-focus on the transcript (Distraction). *(After this model's knowledge
  cutoff; included per the brief as framing only.)*

Together — two synthetic modes, two case-study modes — all four are illustrated,
with break #3 standing outside as the honest reminder that the taxonomy isn't
complete.

---

# Part 3 — defenses and the reliability ceiling

Parts 1 and 2 diagnosed: *where* it broke (the seven-input audit) and *how* it
failed (the four modes). Part 3 closes the loop: *defend* it — and then admit the
limit even good defenses can't cross.

## One defense per mode

Breunig pairs each failure mode with a defense:

- **Poisoning → architectural guardrails** (read-only creds, dev/prod separation,
  verify-before-act).
- **Distraction → compaction** (clear stale tokens).
- **Confusion → tool loadout** (smallest tool set, narrowest permissions).
- **Clash → isolation** (orchestrator holds the plan, sub-agents see only what
  they need).

## Recovery — apply the defense, re-run, watch the row flip back

For each break that a defense applies to, I re-ran the scenario with the defense
in place and re-generated the affected turn. The previously-BROKEN audit row
flips back to OK and the trajectory recovers to 24/24:

- **break #4 (Poisoning) → guardrail.** A *verify-before-act* check re-reads
  ground-truth stock before recommending. The stale "in stock" is still in the
  cache, but the guardrail catches it. Row 6 → OK.
- **break #2 (loose Poisoning) → guardrail / retrieval correction.** A relevance
  check rejects the off-need pour-over and re-retrieves the electric maker.
  Row 3 → OK.
- **break #1 (Clash) → isolation/guardrail.** The recommend step is isolated
  behind a rule-gate so the rule governs it directly. Row 1 → OK. **This is a
  simulated defense** — real isolation is an orchestrator/sub-agent architecture;
  in a single-thread harness I approximate it and say so rather than overclaim.
- **break #3 (no mode) → scoped compaction.** The "under $60" commitment is
  pinned so summarization can't drop it. Rows 4 and 7 → OK.

Honest framing: in a deterministic harness where I author the corrected turns,
recovery is *demonstrative*, not a statistical result. The point is that each
defense targets the exact broken input and flips exactly that row — the same
single-line traceability as the breaks, run in reverse.

## The sharp finding: compaction is both cause and cure

break #3 is the one that pays off twice. Its *cause* was compaction dropping a
constraint — and compaction is *itself the defense for Distraction*. So the same
mechanism is, depending on how it's used, either a defense or the thing that
breaks you. The cure isn't "less compaction" (you'd lose the Distraction
defense) or "more compaction" (you'd drop more constraints). It's **scoped
compaction**: protected constraints are never summarized away. A defense applied
without scoping became a failure; the fix is to scope it.

## Two modes with no break — mapped, not faked

Distraction and Confusion never occur in a short four-turn scenario, so I did
**not** fabricate recovery runs for them. Instead I map their defenses to real
incidents: **Gemini-plays-Pokémon** needs **compaction** (long sessions
accumulate stale tokens); **PocketOS** needed a trimmed **tool loadout** (a
missing loadout/guardrail let superfluous tools degrade responses).

## The reliability ceiling — the limit defenses can't cross

A multi-step agent succeeds end-to-end only if *every* step succeeds:

    success = per_step_reliability ^ step_count

This is structural. The article's anchors: **0.95^20 ≈ 36%**, **0.95^5 ≈ 77%**.
This harness runs ~**11 steps** (each tool call and each generated turn is a
step), which at p=0.95 is only **~57%** end-to-end. Push to 50 steps and even
p=0.99 dips toward 60%.

The lesson that closes the series: **defenses raise *p* — they make each step
more reliable — but they cannot change the shape of *p^n*.** You buy reliability
per step; you do not buy your way past the exponent. Past some step count, the
honest move isn't a better prompt or another guardrail — it's fewer steps:
shorter trajectories, more determinism, humans on the irreversible actions.

## The whole arc

1. **Audit** — make all seven inputs visible; a break flips one row (Part 1).
2. **Name** — classify *how* the context failed with the four modes, honestly,
   gaps and all (Part 2).
3. **Defend + bound** — pair each mode with its defense, show recovery, and place
   the result against the reliability ceiling (Part 3).

Same model throughout. The variable was always the context — and even a
well-defended context lives under a structural ceiling.
