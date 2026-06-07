"""harness (deterministic) — shared run-side plumbing for baseline and breaks.

Loads scenarios, executes the two tools honestly against the catalog, assembles
per-turn ContextBundles, and writes trajectory logs. Breaks reuse this module
and inject a single override (wrong retrieval, dropped constraint, stale tool
result) so the difference between baseline and a break is one localized change.

No LLM calls here. The assistant's generated prose + structured claims are
supplied by the caller (Claude, in-session) — see run_baseline.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from context_bundle import TOOL_SPECS, ContextBundle
from prepare import load_catalog

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"


def load_scenario(name: str = "baseline") -> dict:
    with open(SCENARIOS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)[name]


def get_item(catalog: dict, item_id: str) -> dict | None:
    for it in catalog["items"]:
        if it["id"] == item_id:
            return it
    return None


# ---- honest tool execution (catalog is ground truth) ---------------------
def check_stock(catalog: dict, item_id: str, override: str | None = None) -> dict:
    """Return a tool-output record for check_stock. override forces a stale/false
    result (used only by break #4)."""
    if override is not None:
        result = override
    else:
        item = get_item(catalog, item_id)
        if item is None:
            result = "unknown item"
        else:
            result = "in stock" if item["in_stock"] else "out of stock"
    return {"call": f"check_stock({item_id})", "name": "check_stock",
            "args": {"item_id": item_id}, "result": result}


def get_price(catalog: dict, item_id: str) -> dict:
    item = get_item(catalog, item_id)
    result = f"${item['price']}" if item else "unknown item"
    return {"call": f"get_price({item_id})", "name": "get_price",
            "args": {"item_id": item_id}, "result": result}


def build_bundle(
    system_instructions: str,
    retrieved: list[dict],
    memory: list[str],
    user_query: str,
    tool_outputs: list[dict],
    compaction: str,
) -> ContextBundle:
    """Assemble the seven-input bundle for one call."""
    return ContextBundle(
        system_instructions=system_instructions,
        tools=TOOL_SPECS,
        retrieved=retrieved,
        memory=memory,
        user_query=user_query,
        tool_outputs=tool_outputs,
        compaction=compaction,
    )


def write_trajectory(run_id: str, payload: dict) -> Path:
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{run_id}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path
