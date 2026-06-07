"""context_bundle (deterministic) — the seven-input bundle + Context Audit table.

This is the inspection surface the whole capstone hangs on. Every model call is
represented as a ContextBundle holding all seven context-engineering inputs. The
audit table renders them one per row with a single-word STATUS:

    OK     — input is present and well-formed
    GAP    — input could not be filled (a spec gap, not a missing detail)
    BROKEN — input is present but deliberately compromised by a break

The point of the STATUS column: when a later step breaks one input, exactly one
row flips to BROKEN, so the failure is obvious at a glance in a single line.

No LLM calls here — this only assembles and renders inputs.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any

# The seven inputs, in canonical order. Index = audit row number.
SEVEN_INPUTS = [
    "System instructions",
    "Tools the model can call",
    "Retrieved knowledge",
    "Memory of prior turns",
    "User query",
    "Outputs of previous tool calls",
    "Compaction / summarization",
]

# Tool specifications the assistant may call. Deterministic, declared up front.
TOOL_SPECS = [
    {
        "name": "check_stock",
        "description": "Return whether a catalog item is in stock, by item id.",
        "args": {"item_id": "string"},
    },
    {
        "name": "get_price",
        "description": "Return the price of a catalog item, by item id.",
        "args": {"item_id": "string"},
    },
]


@dataclass
class ContextBundle:
    """All seven context inputs for a single model call, plus break marks.

    Empty inputs render as GAP automatically. A break calls mark_broken() to flip
    a specific row to BROKEN with a short reason, making the failure visible in
    one line of the audit table.
    """

    # 1. System instructions
    system_instructions: str = ""
    # 2. Tools the model can call
    tools: list[dict] = field(default_factory=list)
    # 3. Retrieved knowledge — list of {"item": <item>, "score": <int>}
    retrieved: list[dict] = field(default_factory=list)
    # 4. Memory of prior turns — list of short strings
    memory: list[str] = field(default_factory=list)
    # 5. User query
    user_query: str = ""
    # 6. Outputs of previous tool calls — list of {"call": str, "result": Any}
    tool_outputs: list[dict] = field(default_factory=list)
    # 7. Compaction / summarization — running summary string
    compaction: str = ""

    # Break marks: row_number (1-7) -> reason. Set only by the break steps.
    _broken: dict[int, str] = field(default_factory=dict)

    # ---- break hook -------------------------------------------------------
    def mark_broken(self, input_number: int, reason: str) -> "ContextBundle":
        """Flag one input (1-7) as deliberately compromised for this call."""
        if not 1 <= input_number <= 7:
            raise ValueError(f"input_number must be 1-7, got {input_number}")
        self._broken[input_number] = reason
        return self

    # ---- per-input accessors ---------------------------------------------
    def _value_for(self, n: int) -> Any:
        return {
            1: self.system_instructions,
            2: self.tools,
            3: self.retrieved,
            4: self.memory,
            5: self.user_query,
            6: self.tool_outputs,
            7: self.compaction,
        }[n]

    def _detail_for(self, n: int) -> str:
        """Short human-readable summary of an input's content for the table."""
        v = self._value_for(n)
        if n == 1:
            return v or "(none)"
        if n == 2:
            return ", ".join(t["name"] for t in v) if v else "(none)"
        if n == 3:
            if not v:
                return "(none)"
            return "; ".join(
                f"{h['item']['name']}"
                f"[{'in' if h['item']['in_stock'] else 'OUT'}]"
                f"(s={h['score']})"
                for h in v
            )
        if n == 4:
            return " | ".join(v) if v else "(none)"
        if n == 5:
            return v or "(none)"
        if n == 6:
            if not v:
                return "(none)"
            return "; ".join(f"{o['call']} -> {o['result']}" for o in v)
        if n == 7:
            return v or "(none)"
        return "(none)"

    def _status_for(self, n: int) -> str:
        if n in self._broken:
            return "BROKEN"
        v = self._value_for(n)
        return "OK" if v else "GAP"

    # ---- audit rendering --------------------------------------------------
    def audit_rows(self) -> list[dict]:
        rows = []
        for n in range(1, 8):
            rows.append(
                {
                    "n": n,
                    "input": SEVEN_INPUTS[n - 1],
                    "status": self._status_for(n),
                    "detail": self._detail_for(n),
                    "reason": self._broken.get(n, ""),
                }
            )
        return rows

    def render_audit(self, title: str = "Context Audit", width: int = 88) -> str:
        rows = self.audit_rows()
        out = []
        out.append("=" * width)
        out.append(title)
        out.append("=" * width)
        out.append(f"{'#':<2} {'Input':<30} {'STATUS':<7} Detail")
        out.append("-" * width)
        detail_col = width - (2 + 1 + 30 + 1 + 7 + 1)
        for r in rows:
            detail = r["detail"]
            if r["reason"]:
                detail = f"{detail}  <<BREAK: {r['reason']}>>"
            wrapped = textwrap.wrap(detail, width=detail_col) or [""]
            out.append(
                f"{r['n']:<2} {r['input']:<30} {r['status']:<7} {wrapped[0]}"
            )
            for cont in wrapped[1:]:
                out.append(f"{'':<2} {'':<30} {'':<7} {cont}")
        out.append("-" * width)
        counts = {"OK": 0, "GAP": 0, "BROKEN": 0}
        for r in rows:
            counts[r["status"]] += 1
        out.append(
            f"summary: {counts['OK']} OK / {counts['GAP']} GAP / "
            f"{counts['BROKEN']} BROKEN  (7 inputs audited)"
        )
        out.append("=" * width)
        return "\n".join(out)


def _demo() -> None:
    """Step 2 gate: the audit table shows all seven inputs for a sample call."""
    from prepare import load_catalog, retrieve

    catalog = load_catalog()
    query = "I want a good drip coffee maker"
    hits = retrieve(query, k=3, catalog=catalog)

    # A mid-conversation call so every one of the seven slots is genuinely filled.
    bundle = ContextBundle(
        system_instructions=catalog["meta"]["anchor_system_instruction"],
        tools=TOOL_SPECS,
        retrieved=hits,
        memory=[
            "User is furnishing a new apartment kitchen.",
            "User prefers items under $60.",
        ],
        user_query=query,
        tool_outputs=[
            {"call": "get_price(coffee-drip-electric)", "result": "$49.99"},
        ],
        compaction=(
            "Earlier: user asked about kitchen basics; agreed to keep "
            "recommendations under $60 and in-stock only."
        ),
    )

    print(bundle.render_audit(title="Context Audit — sample mid-conversation call"))


if __name__ == "__main__":
    _demo()
