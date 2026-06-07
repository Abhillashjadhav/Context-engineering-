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
