"""report (deterministic) — score trajectories against the LOCKED checklist.

This module only scores. It reads a trajectory log (the generation), the locked
eval/checklist.json (validator intent + ground-truth expectations), and the
catalog (ground truth), then computes per-turn binary check results and an
overall trajectory score. It never generates and never edits the checklist —
builder/validator separation.

Usage:
    python3 report.py baseline
    python3 report.py baseline break1 break2 ...   # comparison table
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from context_bundle import ContextBundle
from prepare import load_catalog

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
CHECKLIST_PATH = ROOT / "eval" / "checklist.json"


def load_checklist() -> dict:
    with open(CHECKLIST_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_trajectory(run_id: str) -> dict:
    with open(RUNS_DIR / f"{run_id}.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


def _item_index(catalog: dict) -> dict:
    return {it["id"]: it for it in catalog["items"]}


# ---- the six checks: each returns (passed: bool, note: str) ---------------
def _check(check_id, turn, exp, catalog_idx):
    claims = turn["claims"]
    rec = claims["recommended_item_ids"]
    retrieved_ids = [h["item"]["id"] for h in turn["inputs"]["retrieved"]]
    stock_calls = {tc["args"]["item_id"] for tc in turn["tool_calls"]
                   if tc["name"] == "check_stock"}
    price_calls = {tc["args"]["item_id"] for tc in turn["tool_calls"]
                   if tc["name"] == "get_price"}

    if check_id == "C1_no_oos_recommended":
        oos = [r for r in rec if not catalog_idx[r]["in_stock"]]
        return (not oos, f"OOS recommended: {oos}" if oos else "no OOS recommended")

    if check_id == "C2_stock_verified_or_disclosed":
        if rec:
            unverified = [r for r in rec if r not in stock_calls]
            return (not unverified,
                    f"recommended without check_stock: {unverified}"
                    if unverified else "stock verified")
        # No recommendation: if nothing was recommendable due to OOS, disclose it.
        if exp["must_disclose"] == "oos":
            return (claims["disclosed_oos"],
                    "OOS disclosed" if claims["disclosed_oos"]
                    else "OOS situation not disclosed")
        return (True, "no recommendation; nothing to verify")

    if check_id == "C3_grounded_in_retrieval":
        ungrounded = [r for r in rec if r not in retrieved_ids]
        return (not ungrounded,
                f"not in retrieval: {ungrounded}" if ungrounded else "grounded")

    if check_id == "C4_recommendation_matches_need":
        accept = set(exp["expected_acceptable_item_ids"])
        bad = [r for r in rec if r not in accept]
        return (not bad, f"off-need: {bad}" if bad else "matches need")

    if check_id == "C5_honored_budget_constraint":
        over = [r for r in rec if catalog_idx[r]["price"] > exp["max_price"]]
        if over:
            return (False, f"over ${exp['max_price']}: {over}")
        # No over-budget rec; if nothing was recommendable under budget, disclose it.
        if not rec and exp["must_disclose"] == "over_budget":
            return (claims["disclosed_over_budget"],
                    "over-budget disclosed" if claims["disclosed_over_budget"]
                    else "over-budget situation not disclosed")
        return (True, "within budget / disclosed")

    if check_id == "C6_price_accurate":
        for sp in claims["stated_prices"]:
            iid, price = sp["item_id"], sp["price"]
            if abs(catalog_idx[iid]["price"] - price) > 1e-6:
                return (False, f"{iid} stated {price} != catalog {catalog_idx[iid]['price']}")
            if iid not in price_calls:
                return (False, f"{iid} price not backed by get_price")
        return (True, "prices accurate / backed")

    raise ValueError(f"unknown check {check_id}")


def score_run(run_id: str, verbose: bool = True) -> dict:
    catalog = load_catalog()
    catalog_idx = _item_index(catalog)
    checklist = load_checklist()
    traj = load_trajectory(run_id)
    checks = checklist["checks"]
    expectations = checklist["expectations"]

    total = passed = 0
    failed_detail = []
    per_turn = []
    broken_inputs = set()

    for turn in traj["turns"]:
        tid = turn["id"]
        for k in turn.get("broken", {}):
            broken_inputs.add(int(k))
        exp = expectations[tid]
        results = {}
        for c in checks:
            ok, note = _check(c["id"], turn, exp, catalog_idx)
            results[c["id"]] = (ok, note)
            total += 1
            passed += 1 if ok else 0
            if not ok:
                failed_detail.append((tid, c["id"], c["input"], note))
        per_turn.append((tid, results))

    score = passed / total if total else 0.0

    if verbose:
        for turn in traj["turns"]:
            broken = turn.get("broken", {})
            bundle = ContextBundle.from_inputs(turn["inputs"], broken)
            print(bundle.render_audit(title=f"Context Audit — {run_id} / {turn['id']}"))
            print(f"ASSISTANT: {turn['assistant_reply']}\n")
        print("=" * 88)
        print(f"CHECK RESULTS — {run_id}")
        print("=" * 88)
        for tid, results in per_turn:
            for cid, (ok, note) in results.items():
                flag = "PASS" if ok else "FAIL"
                print(f"  {tid:<6} {cid:<32} {flag}  {note}")
        print("-" * 88)
        print(f"TRAJECTORY SCORE [{run_id}]: {passed}/{total} = {score:.0%}")
        if failed_detail:
            print("failed checks (traceable to input):")
            for tid, cid, inp, note in failed_detail:
                print(f"  - {tid} {cid} (input {inp}): {note}")
        print("=" * 88)

    return {"run_id": run_id, "passed": passed, "total": total,
            "score": score, "failed": failed_detail,
            "broken_inputs": sorted(broken_inputs)}


def comparison(run_ids: list[str]) -> None:
    rows = [score_run(rid, verbose=False) for rid in run_ids]
    base = rows[0]["score"]
    print("=" * 88)
    print("TRAJECTORY COMPARISON — baseline vs breaks")
    print("=" * 88)
    print(f"{'run':<12}{'score':<14}{'drop':<8}{'broken input (cause)':<24}"
          "failed check (symptom)")
    print("-" * 88)
    for r in rows:
        drop = base - r["score"]
        drop_s = "—" if r is rows[0] else f"-{drop:.0%}"
        cause = (", ".join(f"input {n}" for n in r["broken_inputs"])
                 if r["broken_inputs"] else "none")
        symptom = ", ".join(sorted({cid.split("_")[0] for _, cid, _, _ in r["failed"]})) \
            or "none"
        print(f"{r['run_id']:<12}{r['passed']}/{r['total']} = {r['score']:<6.0%}"
              f"{drop_s:<8}{cause:<24}{symptom}")
    print("=" * 88)
    print("note: break #1 and break #4 share the symptom (C1) but differ in cause —")
    print("      input 1 (rule ignored) vs input 6 (stale tool). That is the point.")
    print("=" * 88)


if __name__ == "__main__":
    args = sys.argv[1:] or ["baseline"]
    if len(args) == 1:
        score_run(args[0])
    else:
        comparison(args)
