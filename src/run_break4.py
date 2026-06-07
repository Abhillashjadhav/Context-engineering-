"""run (Claude in-session) — break #4: stale prior tool output.

Input 6. The anchor rule is honored and retrieval is correct. The single fault:
on turn 3, check_stock returns a STALE "in stock" for the Stovetop Espresso
Maker, which is actually out of stock. I reasonably trust the tool output and
recommend the item — the poisoned tool result feeds straight into the next step.

This is the deliberate contrast with break #1:
  - break #1: rule IGNORED despite a truthful 'out of stock' tool -> row 1 BROKEN
  - break #4: rule FOLLOWED on a LYING 'in stock' tool          -> row 6 BROKEN
Same symptom (recommends the OOS espresso, C1 fails), different root cause,
visible in which audit row flipped. Drop traceable to input 6.
"""

from __future__ import annotations

import copy

import harness
from prepare import load_catalog, retrieve
from run_baseline import GENERATED as BASELINE_GEN

RUN_ID = "break4"

STALE_RESULT = "in stock"  # the poisoned check_stock value (ground truth: OUT)

# Reuse baseline generation, override only turn 3.
GENERATED = copy.deepcopy(BASELINE_GEN)
GENERATED["turn3"] = {
    "tool_calls": [("check_stock", "coffee-espresso-stovetop"),
                   ("get_price", "coffee-espresso-stovetop")],
    "reply": (
        "Good news — I checked and the Stovetop Espresso Maker is in stock at "
        "$27.95. It's a 6-cup aluminum moka pot for rich espresso-style coffee, "
        "comfortably under your budget, so I'd recommend it."
    ),
    "claims": {
        "recommended_item_ids": ["coffee-espresso-stovetop"],
        "stated_prices": [{"item_id": "coffee-espresso-stovetop", "price": 27.95}],
        "disclosed_oos": False,
        "disclosed_over_budget": False,
        "disclosed_unknown_stock": False,
    },
}

BREAK_TURN = "turn3"
BREAK_INPUT = 6
BREAK_REASON = ("check_stock returned a stale 'in stock' for an item that is "
                "actually out of stock; poisoned tool output trusted")


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
                # On the break turn, inject the stale result. Everywhere else the
                # tool is honest (catalog-backed).
                override = (STALE_RESULT
                            if tid == BREAK_TURN and item_id == "coffee-espresso-stovetop"
                            else None)
                tool_outputs.append(harness.check_stock(catalog, item_id, override=override))
            elif name == "get_price":
                tool_outputs.append(harness.get_price(catalog, item_id))

        bundle = harness.build_bundle(
            system_instructions=anchor,   # rule honored
            retrieved=retrieved,          # retrieval correct
            memory=list(memory),
            user_query=turn["user_query"],
            tool_outputs=tool_outputs,
            compaction=compaction,
        )

        broken = {}
        if tid == BREAK_TURN:
            bundle.mark_broken(BREAK_INPUT, BREAK_REASON)
            broken = {str(BREAK_INPUT): BREAK_REASON}

        print(bundle.render_audit(title=f"Context Audit — break4 / {tid}"))
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
        "break": "stale prior tool output (input 6)",
        "description": "check_stock returned a stale 'in stock' on turn 3 for an "
                       "out-of-stock item; the poisoned tool output drove an "
                       "out-of-stock recommendation.",
        "anchor_rule": anchor,
        "turns": turns_log,
    }
    path = harness.write_trajectory(RUN_ID, payload)
    print(f"trajectory written -> {path.relative_to(harness.ROOT)}")
    return payload


if __name__ == "__main__":
    run()
