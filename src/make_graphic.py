"""Render an infographic PNG: per break, what flipped V1->V2, why, and the fix.

Factual fields (score, broken input, failed check) come from the locked scorer
and the trajectory logs; the 'why' / 'fix' text is curated. Output:
runs/breaks_graphic.png — an image, so it renders anywhere with no HTML quirks.
"""

from __future__ import annotations

import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from report import DASHBOARD_RUNS, RUNS_DIR, score_run

# palette (dark theme, matches the HTML dashboard)
BG = "#0d1117"; PANEL = "#161b22"; LINE = "#30363d"
TXT = "#e6edf3"; SUB = "#8b949e"; OK = "#1a7f37"; BROKEN = "#cf222e"
INPUT_COLOR = {1: "#d29922", 3: "#1f6feb", 47: "#8957e5", 6: "#cf222e"}

# curated content per break (factual fields filled from data at runtime)
BREAKS = [
    {"run": "break1", "title": "Break 1 · System instruction ignored",
     "input": "Input 1 — System instructions", "key": 1,
     "change": "V1: rule present AND obeyed (refuses the out-of-stock espresso).\n"
               "V2: same rule still present, but ignored — recommends it anyway.",
     "why": "The instruction sat right there in context and the model simply did "
            "not act on it. Presence ≠ sufficiency.",
     "fix": "Don't rely on the model to self-enforce. Add a hard guardrail that "
            "blocks any out-of-stock item from being recommended (validate against "
            "stock before replying); raise the rule's salience/priority."},
    {"run": "break2", "title": "Break 2 · Retrieval gap",
     "input": "Input 3 — Retrieved knowledge", "key": 3,
     "change": "V1: retrieves the Electric Drip Maker the user asked for.\n"
               "V2: retrieves the manual Pour-Over near-match, misses the electric one.",
     "why": "The answer was faithfully grounded — in the wrong knowledge. A bad "
            "lookup, not a hallucination (grounding check passed, need-match failed).",
     "fix": "Improve retrieval: better ranking/coverage, attribute-aware query "
            "(\"electric\"), and a relevance check that the retrieved item matches "
            "the user's stated need before recommending."},
    {"run": "break3", "title": "Break 3 · Compaction drops a constraint",
     "input": "Inputs 4 & 7 — Memory + Compaction", "key": 47,
     "change": "V1: keeps the standing \"under $60\" commitment.\n"
               "V2: summary drops it from both memory and compaction.",
     "why": "Summarization silently lost a constraint, so the agent contradicted "
            "its own earlier promise and recommended a $129.99 item.",
     "fix": "Protect critical commitments from compaction: pin constraints in "
            "structured memory, exclude them from lossy summarization, and re-inject "
            "them after every compaction step."},
    {"run": "break4", "title": "Break 4 · Stale tool output",
     "input": "Input 6 — Outputs of previous tool calls", "key": 6,
     "change": "V1: check_stock truthfully returns \"out of stock\".\n"
               "V2: check_stock returns a stale \"in stock\".",
     "why": "The model correctly trusted its tool — but the tool lied. Same "
            "symptom as Break 1 (recommends OOS), opposite root cause.",
     "fix": "Fix the data path, not the model: add freshness/TTL to stock results, "
            "re-validate at decision time, and treat tool outputs as untrusted "
            "(sanity-check before acting)."},
]


def _wrap(t, w):
    return "\n".join(textwrap.fill(line, w) for line in t.split("\n"))


def build():
    results = {r: score_run(r, verbose=False) for r in DASHBOARD_RUNS}
    base = results["baseline"]["score"]

    fig, ax = plt.subplots(figsize=(16, 10.5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # title
    ax.text(0.012, 0.975, "Context Audit Harness — V1 vs V2: what broke, why, and the fix",
            color=TXT, fontsize=21, fontweight="bold", va="top")
    ax.text(0.012, 0.94,
            "Same model every time. Only the context changed. V1 = clean baseline "
            "(24/24, 100%).  Each break compromises ONE input → 23/24 (96%).",
            color=SUB, fontsize=12.5, va="top")

    # column headers
    cols = [(0.012, "BREAK / BROKEN INPUT"), (0.27, "WHAT CHANGED  (V1 → V2)"),
            (0.52, "WHY IT FAILED"), (0.75, "HOW TO FIX IT")]
    for x, h in cols:
        ax.text(x, 0.885, h, color=SUB, fontsize=11.5, fontweight="bold", va="top")

    rows_top = 0.86; row_h = 0.197; gap = 0.012
    for i, b in enumerate(BREAKS):
        y1 = rows_top - i * row_h
        y0 = y1 - row_h + gap
        col = INPUT_COLOR[b["key"]]
        r = results[b["run"]]
        drop = base - r["score"]
        check = ", ".join(sorted({c.split("_")[0] for _, c, _, _ in r["failed"]}))

        # card
        card = FancyBboxPatch((0.008, y0), 0.984, row_h - gap,
                              boxstyle="round,pad=0.004,rounding_size=0.012",
                              linewidth=1, edgecolor=LINE, facecolor=PANEL)
        ax.add_patch(card)
        # left accent bar in the input's color
        ax.add_patch(FancyBboxPatch((0.008, y0), 0.006, row_h - gap,
                                    boxstyle="square,pad=0", linewidth=0, facecolor=col))

        yt = y1 - 0.022
        # col 0: break + input badge + score
        ax.text(0.024, yt, b["title"], color=TXT, fontsize=13, fontweight="bold", va="top")
        ax.text(0.024, yt - 0.045, b["input"], color=col, fontsize=11.5,
                fontweight="bold", va="top")
        ax.text(0.024, yt - 0.083, f"score 100% → {r['score']:.0%}   (−{drop:.0%})",
                color=TXT, fontsize=11, va="top")
        ax.text(0.024, yt - 0.115, f"failed check: {check}", color=BROKEN,
                fontsize=10.5, va="top")
        # mini score bar
        bx, bw = 0.024, 0.20
        ax.add_patch(plt.Rectangle((bx, yt - 0.150), bw, 0.012, color=LINE))
        ax.add_patch(plt.Rectangle((bx, yt - 0.150), bw * r["score"], 0.012, color=col))

        # col 1: what changed
        ax.text(0.27, yt, _wrap(b["change"], 38), color=TXT, fontsize=10.8,
                va="top", linespacing=1.35)
        # col 2: why
        ax.text(0.52, yt, _wrap(b["why"], 36), color=TXT, fontsize=10.8,
                va="top", linespacing=1.35)
        # col 3: fix
        ax.text(0.75, yt, _wrap(b["fix"], 40), color="#aee0b6", fontsize=10.8,
                va="top", linespacing=1.35)

    # footer takeaway
    ax.add_patch(FancyBboxPatch((0.008, 0.012), 0.984, 0.052,
                                boxstyle="round,pad=0.004,rounding_size=0.012",
                                linewidth=1, edgecolor=BROKEN, facecolor="#2d1416"))
    ax.text(0.5, 0.038,
            "The symptom doesn't tell you where it failed — the Context Audit row "
            "that flipped does.  (Break 1 & Break 4 share the symptom C1, but the "
            "broken row is Input 1 vs Input 6.)",
            color="#ffd7d5", fontsize=12, fontweight="bold", ha="center", va="center")

    out = RUNS_DIR / "breaks_graphic.png"
    fig.savefig(out, dpi=150, facecolor=BG, bbox_inches="tight", pad_inches=0.25)
    print(f"graphic written -> {out}")
    return out


if __name__ == "__main__":
    build()
