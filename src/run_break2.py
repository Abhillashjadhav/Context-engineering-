"""run (Claude in-session) — break #2: retrieval gap.

Only input 3 is sabotaged, on turn 1. The user asks for an ELECTRIC coffee
maker. The retrieval here models a real index miss: it returns plausible coffee
near-matches (Pour-Over Dripper, French Press, Insulated Carafe) but the item
the user actually wanted — the Electric Drip Coffee Maker — is the MISSING chunk.

Given only that retrieved set, I confidently recommend the Pour-Over Dripper. It
reads like a real production miss, not an obvious error: the pour-over genuinely
is a 'drip' brewer, in stock, and under budget. The only thing wrong is that it
doesn't match the user's stated need (electric).

Subtlety this proves: C3 (grounded in retrieval) still PASSES — the answer is
faithfully grounded in what was retrieved. C4 (matches need) FAILS. The answer
is grounded in the wrong knowledge. Row 3 BROKEN; drop traceable to input 3.
"""

from __future__ import annotations

import copy

import harness
from prepare import load_catalog, retrieve
from run_baseline import GENERATED as BASELINE_GEN

RUN_ID = "break2"


def _as_hit(catalog, item_id, score):
    """Wrap a catalog item as a retrieval hit {item, score}."""
    return {"item": harness.get_item(catalog, item_id), "score": score}


def build_sabotaged_retrieval(catalog) -> list[dict]:
    """A plausible-but-wrong retrieved set: coffee near-matches WITHOUT the
    electric drip maker the user asked for (the missing chunk)."""
    return [
        _as_hit(catalog, "coffee-pourover-dripper", 7),
        _as_hit(catalog, "coffee-french-press", 5),
        _as_hit(catalog, "coffee-carafe-insulated", 4),
    ]


# Reuse baseline generation, override only turn 1.
GENERATED = copy.deepcopy(BASELINE_GEN)
GENERATED["turn1"] = {
    "tool_calls": [("check_stock", "coffee-pourover-dripper"),
                   ("get_price", "coffee-pourover-dripper")],
    "reply": (
        "For a drip coffee maker, I'd recommend the Pour-Over Coffee Dripper — "
        "it's in stock at just $18.50 and makes great single-cup drip coffee. A "
        "simple, budget-friendly pick to get your new kitchen brewing."
    ),
    "claims": {
        "recommended_item_ids": ["coffee-pourover-dripper"],
        "stated_prices": [{"item_id": "coffee-pourover-dripper", "price": 18.5}],
        "disclosed_oos": False,
        "disclosed_over_budget": False,
        "disclosed_unknown_stock": False,
    },
}

BREAK_TURN = "turn1"
BREAK_INPUT = 3
BREAK_REASON = ("retrieval missed the electric drip maker the user asked for and "
                "surfaced a plausible near-match (manual pour-over) instead")


def run() -> dict:
    catalog = load_catalog()
    scenario = harness.load_scenario("baseline")
    anchor = catalog["meta"]["anchor_system_instruction"]

    memory = list(scenario["memory_seed"])
    compaction = scenario["initial_compaction"]

    turns_log = []
    for turn in scenario["turns"]:
        tid = turn["id"]
        gen = GENERATED[tid]

        # input 3: honest retrieval everywhere except the sabotaged turn
        if tid == BREAK_TURN:
            retrieved = build_sabotaged_retrieval(catalog)
        else:
            retrieved = retrieve(turn["retrieval_query"], k=3, catalog=catalog)

        tool_outputs = []
        for name, item_id in gen["tool_calls"]:
            if name == "check_stock":
                tool_outputs.append(harness.check_stock(catalog, item_id))
            elif name == "get_price":
                tool_outputs.append(harness.get_price(catalog, item_id))

        bundle = harness.build_bundle(
            system_instructions=anchor,
            retrieved=retrieved,
            memory=list(memory),
            user_query=turn["user_query"],
            tool_outputs=tool_outputs,
            compaction=compaction,
        )

        broken = {}
        if tid == BREAK_TURN:
            bundle.mark_broken(BREAK_INPUT, BREAK_REASON)
            broken = {str(BREAK_INPUT): BREAK_REASON}

        print(bundle.render_audit(title=f"Context Audit — break2 / {tid}"))
        print(f"\nASSISTANT ({tid}): {gen['reply']}\n")

        turns_log.append({
            "id": tid,
            "user_query": turn["user_query"],
            "retrieval_query": turn["retrieval_query"],
            "inputs": bundle.to_inputs(),
            "audit": bundle.audit_rows(),
            "broken": broken,
            "tool_calls": tool_outputs,
            "assistant_reply": gen["reply"],
            "claims": gen["claims"],
        })

        recs = gen["claims"]["recommended_item_ids"]
        if recs:
            item = harness.get_item(catalog, recs[0])
            memory.append(f"Recommended {item['name']} (${item['price']}).")
        compaction = (
            "Standing constraints: in-stock only, under $60. "
            f"Progress through {tid}: "
            + "; ".join(memory[len(scenario['memory_seed']):])
        )

    payload = {
        "run_id": RUN_ID,
        "scenario": "baseline",
        "break": "retrieval gap (input 3)",
        "description": "Turn 1 retrieval surfaced a plausible near-match (pour-"
                       "over) and missed the electric drip maker the user asked "
                       "for; confident wrong recommendation followed.",
        "anchor_rule": anchor,
        "turns": turns_log,
    }
    path = harness.write_trajectory(RUN_ID, payload)
    print(f"trajectory written -> {path.relative_to(harness.ROOT)}")
    return payload


if __name__ == "__main__":
    run()
