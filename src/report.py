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

import reliability
from context_bundle import ContextBundle
from prepare import load_catalog

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
CHECKLIST_PATH = ROOT / "eval" / "checklist.json"
FAILURE_MODES_PATH = ROOT / "eval" / "failure_modes.json"
DEFENSES_PATH = ROOT / "eval" / "defenses.json"


def load_checklist() -> dict:
    with open(CHECKLIST_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_failure_modes() -> dict:
    """Part 2 — the validator-side failure-mode lens (Drew Breunig taxonomy)."""
    with open(FAILURE_MODES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_defenses() -> dict:
    """Part 3 — defenses per mode + recovery mapping + no-break incidents."""
    with open(DEFENSES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def harness_step_count() -> int:
    """Deterministic step count of the baseline trajectory: each model action
    (a tool call or a generated turn) is one step."""
    traj = load_trajectory("baseline")
    return sum(len(t["tool_calls"]) for t in traj["turns"]) + len(traj["turns"])


def mode_label(fm: dict, run_id: str) -> str:
    """One-line failure-mode label for a run, e.g. 'Clash (loose)' / 'none (gap)'."""
    tag = fm["break_tags"].get(run_id)
    if tag is None:
        return "—"
    if not tag["modes"]:
        return "none (gap)"
    names = ", ".join(fm["taxonomy"][m]["name"] for m in tag["modes"])
    fit = tag.get("fit", "")
    return names + (f" ({fit})" if fit and fit != "strong" else "")


def _wrap(text: str, width: int, indent: str = "") -> str:
    import textwrap
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


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


DASHBOARD_RUNS = ["baseline", "break1", "break2", "break3", "break4"]
BREAK_TITLES = {
    "baseline": "Clean baseline (all seven inputs OK)",
    "break1": "System instruction present-but-ignored (Replit pattern)",
    "break2": "Retrieval gap",
    "break3": "Compaction drops a constraint",
    "break4": "Stale prior tool output",
}


def _broken_lines(run_id: str) -> list[dict]:
    """For a run, the turn(s) with a BROKEN audit row + the row details."""
    traj = load_trajectory(run_id)
    out = []
    for turn in traj["turns"]:
        if turn.get("broken"):
            rows = [r for r in turn["audit"] if r["status"] == "BROKEN"]
            out.append({"turn": turn["id"], "reply": turn["assistant_reply"],
                        "rows": rows})
    return out


def dashboard(write_md: bool = True) -> None:
    results = {rid: score_run(rid, verbose=False) for rid in DASHBOARD_RUNS}
    base = results["baseline"]["score"]
    fm = load_failure_modes()

    lines = []
    P = lines.append
    P("=" * 100)
    P("CONTEXT AUDIT HARNESS — TRACE DASHBOARD")
    P("context is the variable, not the model  |  presence != sufficiency")
    P("=" * 100)
    P(f"{'run':<11}{'score':<13}{'drop':<7}{'broken input (cause)':<23}"
      f"{'failed check (sympt.)':<23}failure mode (Breunig)")
    P("-" * 100)
    for rid in DASHBOARD_RUNS:
        r = results[rid]
        drop_s = "—" if rid == "baseline" else f"-{base - r['score']:.0%}"
        cause = (", ".join(f"in{n}" for n in r["broken_inputs"])
                 if r["broken_inputs"] else "none")
        symptom = ", ".join(sorted({c.split("_")[0]
                                    for _, c, _, _ in r["failed"]})) or "none"
        P(f"{rid:<11}{r['passed']}/{r['total']} = {r['score']:<5.0%}"
          f"{drop_s:<7}{cause:<23}{symptom:<23}{mode_label(fm, rid)}")
    P("=" * 100)
    P("THE ONE LINE THAT FLIPPED  (the failure is visible in a single audit row)")
    P("=" * 100)
    for rid in DASHBOARD_RUNS[1:]:
        r = results[rid]
        P(f"\n[{rid}] {BREAK_TITLES[rid]}")
        for bl in _broken_lines(rid):
            for row in bl["rows"]:
                P(f"  {bl['turn']}  row {row['n']} {row['input']} -> BROKEN")
                P(f"         cause: {row['reason']}")
        for tid, cid, inp, note in r["failed"]:
            P(f"  {tid}  {cid} FAIL (input {inp}): {note}")
    P("=" * 100)
    P("HEADLINE — break #1 vs break #4: same symptom, opposite cause, opposite fix")
    P("=" * 100)
    P("  symptom (both):  recommended an out-of-stock item  ->  C1 fails")
    P("  break #1 cause:  input 1 — model IGNORED a truthful rule (row 1 BROKEN)")
    P("  break #4 cause:  input 6 — a LYING tool output was trusted (row 6 BROKEN)")
    P("  break #1 fix:    make the model obey the rule already in context")
    P("  break #4 fix:    fix the stale tool; the model behaved correctly on bad data")
    P("  takeaway:        the symptom (C1) does NOT tell you where it failed.")
    P("                   the Context Audit row that flipped does.")

    # ---- Part 2: the failure-mode lens ------------------------------------
    P("=" * 100)
    P("PART 2 — FAILURE-MODE LENS (Drew Breunig taxonomy)")
    P("=" * 100)
    for key in ["poisoning", "distraction", "confusion", "clash"]:
        m = fm["taxonomy"][key]
        P(f"  {m['name']:<12} {m['definition']}")
    P("-" * 100)
    P("  per-break tagging (reasoned honestly, not forced 1:1):")
    for rid in DASHBOARD_RUNS[1:]:
        tag = fm["break_tags"][rid]
        flag = f"   [{tag['flag']}]" if tag.get("flag") else ""
        P(f"\n  [{rid}] {mode_label(fm, rid)}{flag}")
        P(_wrap(tag["rationale"], 94, "    "))
    P("-" * 100)
    P("  input-axis vs mode-axis: the seven-input audit says WHERE it broke;")
    P("  the taxonomy says HOW the context failed. They are orthogonal — Poisoning")
    P("  appears at input 3 (break2) AND input 6 (break4); break1 & break4 share the")
    P("  C1 symptom but split across modes (Clash vs Poisoning). break3 is invisible")
    P("  to the mode axis (omission gap) yet loud on the input axis (rows 4 & 7).")

    # ---- Part 2: worked examples -----------------------------------------
    P("=" * 100)
    P("WORKED EXAMPLES (real cases round out the modes the synthetic breaks miss)")
    P("=" * 100)
    for cs in fm["case_studies"].values():
        modes = ", ".join(fm["taxonomy"][m]["name"] for m in cs["modes"])
        P(f"  {cs['name']} ({cs['date']}) — {modes}")
        P(_wrap(cs["summary"], 94, "    "))
    cov = fm["coverage"]
    P("-" * 100)
    P(f"  synthetic breaks cover: {', '.join(c.capitalize() for c in cov['synthetic_breaks_cover'])}"
      f"   |   case studies cover: {', '.join(c.capitalize() for c in cov['case_studies_cover'])}")
    P(_wrap(cov["note"], 96, "  "))

    # ---- Part 3: defenses, recovery, reliability ceiling ------------------
    lines.extend(_part3_lines(results, base))

    text = "\n".join(lines)
    print(text)
    if write_md:
        _write_markdown(results, base, fm)


def _part3_lines(results, base) -> list[str]:
    df = load_defenses()
    L = []
    A = L.append
    A("=" * 100)
    A("PART 3 — DEFENSES & RECOVERY (one defense per mode; apply it, re-run)")
    A("=" * 100)
    A(f"  {'break':<8}{'mode':<16}{'defense':<26}{'break':<8}{'recover':<9}"
      f"{'delta':<8}rows flipped -> OK")
    A("-" * 100)
    rec_results = {}
    for bid in sorted(df["recoveries"]):
        rec = df["recoveries"][bid]
        rr = score_run(rec["run"], verbose=False)
        rec_results[bid] = rr
        bscore = results[bid]["score"]
        delta = rr["score"] - bscore
        rows = ", ".join(f"row {n}" for n in rec["flips_rows"])
        sim = "  (SIMULATED)" if rec.get("simulated") else ""
        A(f"  {bid:<8}{rec['mode']:<16}{rec['defense']:<26}"
          f"{bscore:<8.0%}{rr['score']:<9.0%}+{delta:<7.0%}{rows}{sim}")
    A("-" * 100)
    A("  applied (how each defense was realized in the harness):")
    for bid in sorted(df["recoveries"]):
        rec = df["recoveries"][bid]
        A(f"    [{bid} -> {rec['run']}] {rec['applied']}")
    # the sharp break3 finding
    b3 = df["recoveries"]["break3"]
    A("")
    A("  SHARP FINDING (break3):")
    A(_wrap(b3["finding"], 94, "    "))

    # modes with no break here -> map defense to real incidents
    A("=" * 100)
    A("DEFENSES FOR MODES WITH NO BREAK HERE (no faked recovery — mapped to real cases)")
    A("=" * 100)
    nb = df["no_break_modes"]
    A("  " + _wrap(nb["note"], 96, "  ").lstrip())
    A("-" * 100)
    for key in ["distraction", "confusion"]:
        m = nb[key]
        A(f"  {key.capitalize()}  ->  incident: {m['incident']}")
        A(f"      defense: {m['defense']}")
        A(_wrap(m["incident_note"], 92, "      "))

    # reliability ceiling
    steps = harness_step_count()
    A("")
    A(reliability.render(harness_steps=steps, width=100))
    p95 = reliability.success(0.95, steps)
    A(f"  this harness runs ~{steps} steps; even at p=0.95 that is "
      f"{p95:.0%} end-to-end. defenses raise p, never the ceiling's shape.")

    # four-defense audit one-pager (the harness as a feature)
    A("=" * 100)
    A("FOUR-DEFENSE AUDIT — the harness as a feature")
    A("=" * 100)
    A("  Poisoning  / guardrails    : IN SCOPE — verify-before-act + retrieval")
    A("                               correction (recover2, recover4).")
    A("  Clash      / isolation     : SIMULATED ONLY — single-thread rule-gate")
    A("                               approximation (recover1); no real orchestrator.")
    A("  Distraction/ compaction    : IN SCOPE as the CURE for break3 (scoped")
    A("                               compaction); no Distraction break to recover.")
    A("  Confusion  / tool loadout  : STRUCTURALLY SATISFIED — only 2 narrow tools")
    A("                               (check_stock, get_price); no Confusion break.")
    A(f"  reliability ceiling        : ~{steps} steps -> {p95:.0%} at p=0.95. The")
    A("                               defenses raise p; they cannot cross the ceiling.")
    A("=" * 100)
    return L


def _md_table(results, base, fm) -> list[str]:
    rows = ["| run | score | drop | broken input (cause) | failed check (symptom) "
            "| failure mode (Breunig) |",
            "|---|---|---|---|---|---|"]
    for rid in DASHBOARD_RUNS:
        r = results[rid]
        drop_s = "—" if rid == "baseline" else f"-{base - r['score']:.0%}"
        cause = (", ".join(f"input {n}" for n in r["broken_inputs"])
                 if r["broken_inputs"] else "none")
        symptom = ", ".join(sorted({c.split("_")[0]
                                    for _, c, _, _ in r["failed"]})) or "none"
        rows.append(f"| {rid} | {r['passed']}/{r['total']} = {r['score']:.0%} | "
                    f"{drop_s} | {cause} | {symptom} | {mode_label(fm, rid)} |")
    return rows


def _part3_md(results) -> list[str]:
    df = load_defenses()
    steps = harness_step_count()
    p95 = reliability.success(0.95, steps)
    md = ["## Part 3 — Defenses & recovery (one defense per mode)\n",
          f"*Source: {df['source']}.* Apply the matching defense, re-run, watch the "
          "broken row flip back to OK and the score recover.\n",
          "| break | mode | defense | break | recover | delta | rows flipped → OK | simulated? |",
          "|---|---|---|---|---|---|---|---|"]
    for bid in sorted(df["recoveries"]):
        rec = df["recoveries"][bid]
        rr = score_run(rec["run"], verbose=False)
        bscore = results[bid]["score"]
        rows = ", ".join(f"row {n}" for n in rec["flips_rows"])
        sim = "yes (simulated)" if rec.get("simulated") else "no"
        md.append(f"| {bid} | {rec['mode']} | {rec['defense']} | {bscore:.0%} | "
                  f"{rr['score']:.0%} | +{rr['score'] - bscore:.0%} | {rows} | {sim} |")
    md.append("\n**How each defense was realized:**")
    for bid in sorted(df["recoveries"]):
        rec = df["recoveries"][bid]
        md.append(f"- **{bid} → {rec['run']}** — {rec['applied']}")
    md.append(f"\n> **Sharp finding (break3).** {df['recoveries']['break3']['finding']}\n")

    nb = df["no_break_modes"]
    md.append("### Defenses for modes with no break here\n")
    md.append(nb["note"] + "\n")
    md.append("| mode | defense | incident |")
    md.append("|---|---|---|")
    for key in ["distraction", "confusion"]:
        m = nb[key]
        md.append(f"| {key.capitalize()} | {m['defense']} | {m['incident']} — "
                  f"{m['incident_note']} |")

    md.append("\n### Reliability ceiling\n")
    md.append("`success = per_step_reliability ^ step_count` — a structural ceiling. "
              "Defenses raise *p*; they cannot change the shape of *p^n*.\n")
    md += reliability.render_markdown(harness_steps=steps)
    md.append(f"\nThis harness runs ~**{steps} steps**; even at p=0.95 that is "
              f"**{p95:.0%}** end-to-end. The article's anchors: 0.95^20 ≈ 36%, "
              "0.95^5 ≈ 77%.\n")

    md.append("### Four-defense audit — the harness as a feature\n")
    md.append("| defense (mode) | status in this harness |")
    md.append("|---|---|")
    md.append("| guardrails (Poisoning) | **in scope** — verify-before-act + retrieval correction (recover2, recover4) |")
    md.append("| isolation (Clash) | **simulated only** — single-thread rule-gate; no real orchestrator (recover1) |")
    md.append("| compaction (Distraction) | **in scope as the cure** for break3 (scoped compaction); no Distraction break |")
    md.append("| tool loadout (Confusion) | **structurally satisfied** — only 2 narrow tools; no Confusion break |")
    md.append(f"| reliability ceiling | ~{steps} steps → {p95:.0%} at p=0.95; defenses raise p, not the ceiling |")
    md.append("")
    return md


def _write_markdown(results, base, fm) -> None:
    md = []
    md.append("# Context Audit Harness — Trace Dashboard\n")
    md.append("> *context is the variable, not the model* — and "
              "*presence ≠ sufficiency*.\n")
    md.append("Baseline vs four breaks. Each break compromises exactly one of the "
              "seven context inputs; the score drops and the Context Audit shows "
              "which row flipped.\n")
    md.append("## Scoreboard\n")
    md += _md_table(results, base, fm)
    md.append("\n## The one line that flipped\n")
    md.append("For each break, the single audit row that went BROKEN (the cause) "
              "and the check it tripped (the symptom):\n")
    for rid in DASHBOARD_RUNS[1:]:
        r = results[rid]
        md.append(f"### {rid} — {BREAK_TITLES[rid]}\n")
        for bl in _broken_lines(rid):
            for row in bl["rows"]:
                md.append(f"- **{bl['turn']} · row {row['n']} "
                          f"({row['input']}) → BROKEN** — {row['reason']}")
        for tid, cid, inp, note in r["failed"]:
            md.append(f"- {tid} · `{cid}` **FAIL** (input {inp}): {note}")
        md.append("")
    md.append("## Headline: break #1 vs break #4\n")
    md.append("Same symptom, opposite root cause, opposite fix:\n")
    md.append("| | break #1 | break #4 |")
    md.append("|---|---|---|")
    md.append("| symptom | recommends OOS item → C1 fails | recommends OOS item → C1 fails |")
    md.append("| cause | input 1 — rule ignored (row 1 BROKEN) | input 6 — stale tool trusted (row 6 BROKEN) |")
    md.append("| the tool said | \"out of stock\" (truthful) | \"in stock\" (stale/lying) |")
    md.append("| the rule was | present and ignored | honored on bad data |")
    md.append("| fix | make the model obey the rule | fix the stale tool |")
    md.append("\n**The symptom (C1) does not tell you where it failed. The Context "
              "Audit row that flipped does.**\n")

    # ---- Part 2: failure-mode lens ---------------------------------------
    md.append("## Part 2 — Failure-mode lens (Drew Breunig taxonomy)\n")
    md.append(f"*Source: {fm['source']}.* Tagging is interpretive and reasoned "
              "honestly — not forced 1:1.\n")
    md.append("| mode | definition |")
    md.append("|---|---|")
    for key in ["poisoning", "distraction", "confusion", "clash"]:
        m = fm["taxonomy"][key]
        md.append(f"| **{m['name']}** | {m['definition']} |")
    md.append("\n### Per-break tagging\n")
    for rid in DASHBOARD_RUNS[1:]:
        tag = fm["break_tags"][rid]
        flag = f" — _{tag['flag']}_" if tag.get("flag") else ""
        md.append(f"- **{rid} → {mode_label(fm, rid)}**{flag}  \n  {tag['rationale']}")
    md.append("\n### Input-axis vs mode-axis\n")
    md.append("The seven-input audit says **where** it broke; the taxonomy says "
              "**how** the context failed. They are orthogonal: Poisoning shows up at "
              "input 3 (break2) *and* input 6 (break4); break1 and break4 share the C1 "
              "symptom but split across modes (Clash vs Poisoning); break3 is invisible "
              "to the mode axis (omission gap) yet loud on the input axis (rows 4 & 7).\n")
    md.append("### Worked examples\n")
    md.append("Real cases supply the two modes the synthetic breaks never produce:\n")
    md.append("| case | date | failure mode(s) |")
    md.append("|---|---|---|")
    for cs in fm["case_studies"].values():
        modes = ", ".join(fm["taxonomy"][m]["name"] for m in cs["modes"])
        md.append(f"| {cs['name']} | {cs['date']} | {modes} |")
    md.append("")
    for cs in fm["case_studies"].values():
        md.append(f"- **{cs['name']}** — {cs['summary']}")
    cov = fm["coverage"]
    md.append(f"\n> **Coverage.** Synthetic breaks cover "
              f"{', '.join(c.capitalize() for c in cov['synthetic_breaks_cover'])}; "
              f"case studies cover "
              f"{', '.join(c.capitalize() for c in cov['case_studies_cover'])}. "
              f"{cov['note']}\n")

    md += _part3_md(results)

    out_path = RUNS_DIR / "report.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print(f"\nmarkdown dashboard written -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    args = sys.argv[1:] or ["dashboard"]
    if args[0] == "dashboard":
        dashboard()
    elif len(args) == 1:
        score_run(args[0])
    else:
        comparison(args)
