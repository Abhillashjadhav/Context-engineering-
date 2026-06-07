# context-audit-harness

Makes the **seven context-engineering inputs** explicit and inspectable on every
LLM call, then deliberately breaks four of them and measures the
**trajectory-score drop** against a clean baseline.

Runnable proof of one idea: **context is the variable, not the model** — and
its corollary, **presence ≠ sufficiency** (an input can be present in context
and still fail to do its job).

## Model in the loop

Claude **inside the Claude Code session** does the generation. **No Anthropic
API key. No metered tokens.**

- Deterministic Python assembles the context, breaks inputs, and scores.
- The generation step = Claude reads the assembled context bundle and writes the
  output; the harness then scores it.
- Locked **prepare / run / report** pattern — LLM judgment isolated to the
  session, never scoring itself (builder–validator separation).

## Domain

A 25-item **home-goods catalog** assistant. Flow per call: user asks → retrieve
from catalog → may call a tool (`check_stock` / `get_price`) → keeps memory
across turns → governed by a hard system instruction → prior tool output feeds
the next step → long history gets compacted.

Anchor system instruction (the checkable "do-not"):

> **Never recommend an out-of-stock item. If stock is unknown, say so.**

## The seven inputs (audited on every call)

1. System instructions
2. Tools the model can call
3. Retrieved knowledge
4. Memory of prior turns
5. User query
6. Outputs of previous tool calls
7. Compaction / summarization

## The four breaks (baseline first, then one break per run)

1. **System instruction present-but-ignored** — the "no out-of-stock" rule sits
   in context; measure whether the model recommends out-of-stock anyway. → input 1
2. **Retrieval gap** — feed a wrong/missing chunk → confident wrong answer. → input 3
3. **Compaction drops a constraint** — the summary loses an earlier commitment →
   agent contradicts itself. → inputs 4/7
4. **Stale prior tool output** — `check_stock` returns stale "in stock" → poisons
   the next recommendation. → input 6

## Metric

**Trajectory score, not pass@1.** Binary checks across the call sequence.
Baseline scores high; each break drops the score in a measured, traceable way.

## Architecture (locked)

- **prepare** (`src/prepare.py`, deterministic): build catalog, context bundle
  (seven inputs), test scenarios, the locked eval checklist.
- **run** (Claude, this session): generate against each assembled context; log
  the trajectory to `runs/`.
- **report** (`src/report.py`, deterministic): score trajectories against the
  locked checklist; emit baseline vs each break with the audit table.
- The eval harness (`eval/`) is **locked** — the thing that generates never
  scores itself.

## Layout

```
.
├── data/    # catalog.json + generated scenarios (inputs)
├── src/     # prepare.py, report.py, context_bundle.py (deterministic)
├── runs/    # trajectory logs from Claude in-loop (baseline + 4 breaks)
└── eval/    # checklist.json — the LOCKED eval checklist
```

## Status

Step 0 — scaffold. Subsequent steps build catalog/retrieval, the context
bundler + audit table, the baseline run, the four breaks, and the report.
