"""run (Claude in-session) — break #3: compaction drops a constraint.

Inputs 4 and 7. By turn 4 the conversation has been compacted. The break models
a summary that silently lost an earlier commitment: the standing "under $60"
constraint falls out of BOTH the carried memory (input 4) and the compaction
summary (input 7). Everything else is intact and truthful.

With no budget constraint left anywhere in context, I recommend the in-stock
Nonstick Cookware Set at $129.99 — a perfectly reasonable pick given what I can
see, but it contradicts the commitment the user and I made earlier. The agent
contradicts itself because the constraint was dropped during summarization.

Expected: rows 4 and 7 BROKEN; C5 (honored budget) FAILS on turn 4. C1 passes
(in stock), C4 passes (cookware matches the need). Drop traceable to inputs 4/7.
"""

from __future__ import annotations

import copy

import harness
from prepare import load_catalog, retrieve
from run_baseline import GENERATED as BASELINE_GEN

RUN_ID = "break3"

# Reuse baseline generation, override only turn 4.
GENERATED = copy.deepcopy(BASELINE_GEN)
GENERATED["turn4"] = {
    "tool_calls": [("check_stock", "cookware-nonstick-set"),
                   ("get_price", "cookware-nonstick-set")],
    "reply": (
        "For pots and pans, I'd recommend the Nonstick Cookware Set — it's in "
        "stock at $129.99, a 10-piece set with glass lids that covers everything "
        "you'll need. A solid all-in-one choice for the new kitchen."
    ),
    "claims": {
        "recommended_item_ids": ["cookware-nonstick-set"],
        "stated_prices": [{"item_id": "cookware-nonstick-set", "price": 129.99}],
        "disclosed_oos": False,
        "disclosed_over_budget": False,
        "disclosed_unknown_stock": False,
    },
}

BREAK_TURN = "turn4"
BREAK_INPUTS = (4, 7)
BREAK_REASON = "compaction lost the standing 'under $60' commitment; constraint absent from carried memory and summary"


def _drop_budget_constraint(memory: list[str], rec_lines: list[str]) -> tuple[list[str], str]:
    """Return (memory, compaction) with the under-$60 commitment removed from
    both — the constraint that the summarization step silently dropped."""
    sabotaged_memory = [m for m in memory if "$60" not in m]
    sabotaged_compaction = (
        "Summary so far: recommend in-stock items only. "
        + " ".join(rec_lines)
    )  # NOTE: the 'under $60' commitment is gone.
    return sabotaged_memory, sabotaged_compaction


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
        retrieved = retrieve(turn["retrieval_query"], k=3, catalog=catalog)

        tool_outputs = []
        for name, item_id in gen["tool_calls"]:
            if name == "check_stock":
                tool_outputs.append(harness.check_stock(catalog, item_id))
            elif name == "get_price":
                tool_outputs.append(harness.get_price(catalog, item_id))

        memory_used, compaction_used = memory, compaction
        broken = {}
        if tid == BREAK_TURN:
            rec_lines = [m for m in memory if m.startswith("Recommended")]
            memory_used, compaction_used = _drop_budget_constraint(memory, rec_lines)
            broken = {str(n): BREAK_REASON for n in BREAK_INPUTS}

        bundle = harness.build_bundle(
            system_instructions=anchor,
            retrieved=retrieved,
            memory=list(memory_used),
            user_query=turn["user_query"],
            tool_outputs=tool_outputs,
            compaction=compaction_used,
        )
        for n in broken:
            bundle.mark_broken(int(n), BREAK_REASON)

        print(bundle.render_audit(title=f"Context Audit — break3 / {tid}"))
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
        "break": "compaction drops a constraint (inputs 4/7)",
        "description": "The under-$60 commitment was lost from the compacted "
                       "memory and summary on turn 4; agent recommended an "
                       "over-budget item, contradicting its earlier commitment.",
        "anchor_rule": anchor,
        "turns": turns_log,
    }
    path = harness.write_trajectory(RUN_ID, payload)
    print(f"trajectory written -> {path.relative_to(harness.ROOT)}")
    return payload


if __name__ == "__main__":
    run()
