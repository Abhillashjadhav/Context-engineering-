"""report-side (deterministic) — render the V1-vs-V2 HTML diff dashboard.

V1 = baseline (clean run). V2 = a broken run. For each break this emits the
seven-input Context Audit for the break's turn, baseline beside broken, with the
row(s) that changed highlighted and BROKEN cells flagged — so the clean-vs-broken
diff is visible at a glance. Reads only the trajectory logs + the locked scorer;
generates nothing, scores nothing it didn't already score.

    python3 dashboard_html.py   ->   runs/dashboard.html
"""

from __future__ import annotations

import html

from report import (BREAK_TITLES, DASHBOARD_RUNS, RUNS_DIR, load_trajectory,
                    score_run)


def esc(s) -> str:
    return html.escape(str(s))


def _turn_map(traj: dict, tid: str):
    """Return ({input_n: audit_row}, assistant_reply) for a turn id."""
    for turn in traj["turns"]:
        if turn["id"] == tid:
            return {r["n"]: r for r in turn["audit"]}, turn["assistant_reply"]
    return {}, ""


def _break_turn(traj: dict):
    """The turn id carrying the break, and the set of broken input numbers."""
    for turn in traj["turns"]:
        if turn.get("broken"):
            return turn["id"], {int(k) for k in turn["broken"]}
    return None, set()


def _status_badge(status: str) -> str:
    return f'<span class="badge {status.lower()}">{status}</span>'


def _cell(row: dict) -> str:
    detail = esc(row["detail"])
    reason = (f'<div class="reason">BREAK: {esc(row["reason"])}</div>'
              if row.get("reason") else "")
    return f'{_status_badge(row["status"])}<div class="detail">{detail}</div>{reason}'


def _scoreboard(results: dict, base: float) -> str:
    head = ("<tr><th>run</th><th>score</th><th>drop vs V1</th>"
            "<th>broken input (cause)</th><th>failed check (symptom)</th></tr>")
    body = []
    for rid in DASHBOARD_RUNS:
        r = results[rid]
        drop = "—" if rid == "baseline" else f"-{base - r['score']:.0%}"
        cause = (", ".join(f"input {n}" for n in r["broken_inputs"])
                 if r["broken_inputs"] else "none")
        symptom = ", ".join(sorted({c.split("_")[0]
                                    for _, c, _, _ in r["failed"]})) or "none"
        cls = "ok-row" if rid == "baseline" else "break-row"
        body.append(
            f'<tr class="{cls}"><td><b>{rid}</b><br><span class="sub">'
            f'{esc(BREAK_TITLES[rid])}</span></td>'
            f'<td class="num">{r["passed"]}/{r["total"]}<br>{r["score"]:.0%}</td>'
            f'<td class="num">{drop}</td><td>{esc(cause)}</td>'
            f'<td>{esc(symptom)}</td></tr>')
    return f'<table class="scoreboard">{head}{"".join(body)}</table>'


def _diff_block(rid: str, baseline: dict, results: dict) -> str:
    traj = load_trajectory(rid)
    tid, broken_inputs = _break_turn(traj)
    v2_rows, v2_reply = _turn_map(traj, tid)
    v1_rows, v1_reply = _turn_map(baseline, tid)

    rows_html = []
    for n in range(1, 8):
        v1, v2 = v1_rows[n], v2_rows[n]
        changed = (v1["status"] != v2["status"]) or (v1["detail"] != v2["detail"])
        broken = v2["status"] == "BROKEN"
        cls = "broken-row" if broken else ("changed-row" if changed else "")
        marker = "◀ broke here" if broken else ("changed" if changed else "")
        rows_html.append(
            f'<tr class="{cls}"><td class="num">{n}</td>'
            f'<td class="inp">{esc(v1["input"])}</td>'
            f'<td>{_cell(v1)}</td><td>{_cell(v2)}</td>'
            f'<td class="mark">{marker}</td></tr>')

    failed = "".join(
        f'<li><code>{esc(cid)}</code> <b>FAIL</b> on {esc(t)} '
        f'(input {esc(inp)}): {esc(note)}</li>'
        for t, cid, inp, note in results[rid]["failed"])

    return f"""
    <section class="break">
      <h2>{esc(rid)} — {esc(BREAK_TITLES[rid])}</h2>
      <p class="meta">break turn: <b>{esc(tid)}</b> &middot; broken input(s):
         <b>{', '.join(f'input {n}' for n in sorted(broken_inputs))}</b></p>
      <table class="audit">
        <tr><th>#</th><th>Input</th><th>V1 — baseline (clean)</th>
            <th>V2 — {esc(rid)} (broken)</th><th></th></tr>
        {''.join(rows_html)}
      </table>
      <div class="replies">
        <div class="reply v1"><span class="tag">V1 reply</span>{esc(v1_reply)}</div>
        <div class="reply v2"><span class="tag">V2 reply</span>{esc(v2_reply)}</div>
      </div>
      <ul class="failed">{failed}</ul>
    </section>"""


def _contrast() -> str:
    return """
    <section class="headline">
      <h2>Headline — break #1 vs break #4: same symptom, opposite cause</h2>
      <table class="contrast">
        <tr><th></th><th>break #1</th><th>break #4</th></tr>
        <tr><td>symptom</td><td>recommends OOS item → C1 fails</td>
            <td>recommends OOS item → C1 fails</td></tr>
        <tr><td>cause</td><td><b>input 1</b> — rule ignored (row 1 BROKEN)</td>
            <td><b>input 6</b> — stale tool trusted (row 6 BROKEN)</td></tr>
        <tr><td>the tool said</td><td>"out of stock" (truthful)</td>
            <td>"in stock" (stale / lying)</td></tr>
        <tr><td>the rule was</td><td>present and ignored</td>
            <td>honored on bad data</td></tr>
        <tr><td>fix</td><td>make the model obey the rule</td>
            <td>fix the stale tool</td></tr>
      </table>
      <p class="punch">The symptom does not tell you where it failed.
         The Context Audit row that flipped does.</p>
    </section>"""


CSS = """
:root{--ok:#1a7f37;--gap:#6e7781;--broken:#cf222e;--bg:#0d1117;--panel:#161b22;
--line:#30363d;--txt:#e6edf3;--sub:#8b949e;--hi:#3d2c00;--chg:#1c2a3a;}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;margin:0;padding:32px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
.thesis{color:var(--sub);margin:0 0 24px}
table{border-collapse:collapse;width:100%;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{background:#1f2630;color:var(--sub);font-weight:600}
.num{text-align:center;white-space:nowrap}.inp{white-space:nowrap;color:var(--sub)}
.sub{color:var(--sub);font-size:12px}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700;color:#fff}
.badge.ok{background:var(--ok)}.badge.gap{background:var(--gap)}.badge.broken{background:var(--broken)}
.detail{margin-top:4px;color:var(--txt);font-size:12.5px;white-space:pre-wrap}
.reason{margin-top:5px;color:#ffb4ab;font-size:11.5px;font-style:italic}
.broken-row{background:rgba(207,34,46,.14)}.changed-row{background:var(--chg)}
.mark{color:var(--broken);font-weight:700;white-space:nowrap;font-size:12px}
.scoreboard .break-row td{border-left:0}.ok-row{background:rgba(26,127,55,.10)}
.meta{color:var(--sub);margin:6px 0 10px}
.replies{display:flex;gap:14px;margin:12px 0}
.reply{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:12.5px}
.reply .tag{display:block;color:var(--sub);font-size:11px;margin-bottom:5px;text-transform:uppercase;letter-spacing:.04em}
.reply.v1{border-left:3px solid var(--ok)}.reply.v2{border-left:3px solid var(--broken)}
.failed{margin:10px 0 0;padding-left:18px;color:#ffb4ab;font-size:12.5px}
.failed code{color:#ffd7d5}
.contrast td:first-child{color:var(--sub);white-space:nowrap}
.punch{margin:14px 0 0;font-size:15px;font-weight:700;color:#ffd7d5}
.legend{margin:8px 0 0;color:var(--sub);font-size:12px}
footer{margin-top:34px;color:var(--sub);font-size:12px;border-top:1px solid var(--line);padding-top:12px}
"""


def build() -> str:
    baseline = load_trajectory("baseline")
    results = {rid: score_run(rid, verbose=False) for rid in DASHBOARD_RUNS}
    base = results["baseline"]["score"]

    blocks = "".join(_diff_block(rid, baseline, results)
                     for rid in DASHBOARD_RUNS[1:])

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Context Audit Harness — V1 vs V2 diff</title><style>{CSS}</style></head>
<body>
<h1>Context Audit Harness — V1 vs V2 diff</h1>
<p class="thesis">V1 = clean baseline &nbsp;·&nbsp; V2 = broken run &nbsp;|&nbsp;
   <i>context is the variable, not the model — presence ≠ sufficiency</i></p>

<h2>Scoreboard</h2>
{_scoreboard(results, base)}
<p class="legend">Each break compromises exactly one input; the score drops and
   the audit row that flipped names the cause.
   <span class="badge ok">OK</span>
   <span class="badge gap">GAP</span>
   <span class="badge broken">BROKEN</span></p>

{blocks}
{_contrast()}

<footer>Generated deterministically from runs/*.json by the locked scorer.
  Re-running the harness reproduces this byte-for-byte.</footer>
</body></html>"""


def main() -> None:
    out = RUNS_DIR / "dashboard.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build())
    print(f"HTML dashboard written -> {out}")


if __name__ == "__main__":
    main()
