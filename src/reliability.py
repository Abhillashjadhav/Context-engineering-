"""reliability ceiling — pure deterministic Python, no model in the loop.

A multi-step agent succeeds end-to-end only if every step succeeds:

    success(p, n) = p ** n            (p = per-step reliability, n = step count)

This is a structural ceiling. Defenses (Part 3) raise p — they push each step
closer to reliable — but they cannot change the shape of p**n. Enough steps and
even a very reliable per-step agent falls below a coin flip. The article's
anchor points: 0.95^20 ≈ 36%, 0.95^5 ≈ 77%.

Runnable standalone:  python3 reliability.py
"""

from __future__ import annotations

DEFAULT_PS = (0.90, 0.95, 0.99)
DEFAULT_STEPS = (1, 5, 10, 20, 50, 100)

# article anchor points: (p, steps) -> label
ARTICLE_MARKS = {(0.95, 20): "article: ~36%", (0.95, 5): "article: ~77%"}


def success(p: float, steps: int) -> float:
    """End-to-end success probability of an n-step agent at per-step reliability p."""
    return p ** steps


def render(step_counts=DEFAULT_STEPS, ps=DEFAULT_PS, harness_steps: int | None = None,
           width: int = 72) -> str:
    """Render the reliability-ceiling table as text. Marks the article points and,
    if given, the harness's own step count."""
    steps = sorted(set(step_counts) | ({harness_steps} if harness_steps else set()))
    out = []
    out.append("=" * width)
    out.append("RELIABILITY CEILING  —  success = per_step_reliability ^ step_count")
    out.append("=" * width)
    header = f"{'steps':>6} | " + " | ".join(f"p={p:.2f}" for p in ps) + "   notes"
    out.append(header)
    out.append("-" * width)
    for n in steps:
        cells = " | ".join(f"{success(p, n):>6.0%}" for p in ps)
        notes = []
        if harness_steps is not None and n == harness_steps:
            notes.append("<- THIS HARNESS")
        for p in ps:
            if (p, n) in ARTICLE_MARKS:
                notes.append(ARTICLE_MARKS[(p, n)])
        note = ("   " + "; ".join(notes)) if notes else ""
        out.append(f"{n:>6} | {cells}{note}")
    out.append("-" * width)
    out.append("defenses raise p; they do NOT change the shape of p**n.")
    out.append("the ceiling is structural — enough steps and any fixed p falls off.")
    out.append("=" * width)
    return "\n".join(out)


def render_markdown(step_counts=DEFAULT_STEPS, ps=DEFAULT_PS,
                    harness_steps: int | None = None) -> list[str]:
    steps = sorted(set(step_counts) | ({harness_steps} if harness_steps else set()))
    md = [f"| steps | " + " | ".join(f"p={p:.2f}" for p in ps) + " | note |",
          "|---|" + "---|" * (len(ps) + 1)]
    for n in steps:
        cells = " | ".join(f"{success(p, n):.0%}" for p in ps)
        notes = []
        if harness_steps is not None and n == harness_steps:
            notes.append("**this harness**")
        for p in ps:
            if (p, n) in ARTICLE_MARKS:
                notes.append(ARTICLE_MARKS[(p, n)])
        md.append(f"| {n} | {cells} | {'; '.join(notes)} |")
    return md


if __name__ == "__main__":
    print(render(harness_steps=11))
