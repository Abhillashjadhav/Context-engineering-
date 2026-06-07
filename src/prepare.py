"""prepare (deterministic) — catalog loading + local retrieval.

This phase only assembles inputs. No LLM calls, no network, no embeddings — the
retrieval is a reproducible keyword-overlap scorer so every run is identical and
the breaks (especially the retrieval gap, #2) are controllable by hand.

Steps 1-2 live here. Step 1 = catalog + retrieve(). Later steps add the context
bundle and scenario builders.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"

# Minimal stopword list — kept tiny and explicit so retrieval stays predictable.
_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "with", "my", "i",
    "me", "is", "it", "that", "this", "something", "want", "need", "looking",
    "some", "any", "in", "on", "keep", "make", "get", "do", "you", "have",
    "can", "please", "would", "like", "good", "best",
}

# Field weights: a name hit is stronger evidence than a description hit.
_NAME_WEIGHT = 3
_TAG_WEIGHT = 2
_DESC_WEIGHT = 1


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    """Load and return the raw catalog object (meta + items)."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-char tokens."""
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return [t for t in tokens if t and len(t) > 1 and t not in _STOPWORDS]


def _score_item(query_tokens: list[str], item: dict) -> int:
    """Deterministic overlap score: weighted token matches across fields."""
    name_tokens = set(_tokenize(item.get("name", "")))
    tag_tokens = set(_tokenize(" ".join(item.get("tags", []))))
    desc_tokens = set(_tokenize(item.get("description", "")))

    score = 0
    for tok in query_tokens:
        if tok in name_tokens:
            score += _NAME_WEIGHT
        if tok in tag_tokens:
            score += _TAG_WEIGHT
        if tok in desc_tokens:
            score += _DESC_WEIGHT
    return score


def retrieve(query: str, k: int = 3, catalog: dict | None = None) -> list[dict]:
    """Return the top-k catalog items for a query, highest score first.

    Returns a list of dicts: {"item": <item>, "score": <int>}. Ties are broken
    by catalog order (stable) so output is fully reproducible. Zero-score items
    are excluded — an empty list means "nothing relevant retrieved", which is a
    legitimate signal the bundler/breaks can act on.
    """
    catalog = catalog or load_catalog()
    query_tokens = _tokenize(query)

    scored = []
    for idx, item in enumerate(catalog["items"]):
        s = _score_item(query_tokens, item)
        if s > 0:
            scored.append((s, idx, item))

    # Sort by score desc, then original index asc (stable tie-break).
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"item": it, "score": s} for s, _, it in scored[:k]]


def _demo() -> None:
    """Step 1 gate: a sample query returns a sane top-k."""
    catalog = load_catalog()
    print(f"Loaded {catalog['meta']['item_count']} items from {CATALOG_PATH.name}")
    print(f"Anchor rule: {catalog['meta']['anchor_system_instruction']}\n")

    for query in [
        "something to keep my coffee warm",
        "drip coffee maker",
        "warm blanket for bed",
        "knife set for the kitchen",
    ]:
        print(f"QUERY: {query!r}")
        for hit in retrieve(query, k=3, catalog=catalog):
            it = hit["item"]
            stock = "IN STOCK" if it["in_stock"] else "OUT OF STOCK"
            print(f"  [{hit['score']:>2}] {it['name']:<28} ${it['price']:<7} {stock}")
        print()


if __name__ == "__main__":
    _demo()
