import re
from datetime import timedelta
from typing import Optional

from rapidfuzz import fuzz, process

from src.models import Market

SIMILARITY_THRESHOLD = 72.0
DATE_WINDOW_DAYS = 45


def _normalize(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\b(will|the|a|an|in|by|for|to|of|on|be|is|are|does|did|can|would)\b", "", title)
    title = re.sub(r"[^\w\s]", " ", title)
    return " ".join(title.split())


def _dates_close(a: Market, b: Market) -> bool:
    if a.close_time is None or b.close_time is None:
        return True
    diff = abs((a.close_time - b.close_time).total_seconds())
    return diff < DATE_WINDOW_DAYS * 86_400


def find_matches(
    markets_a: list[Market],
    markets_b: list[Market],
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[tuple[Market, Market, float]]:
    """Return (mkt_a, mkt_b, similarity_score) pairs above threshold."""
    if not markets_a or not markets_b:
        return []

    b_norms = [_normalize(m.title) for m in markets_b]
    matches: list[tuple[Market, Market, float]] = []
    seen: set[tuple[str, str]] = set()  # deduplicate by (id_a, id_b)

    for mkt_a in markets_a:
        norm_a = _normalize(mkt_a.title)
        results = process.extract(norm_a, b_norms, scorer=fuzz.token_set_ratio, limit=5)
        for _match_str, score, idx in results:
            if score < threshold:
                continue
            mkt_b = markets_b[idx]
            if not _dates_close(mkt_a, mkt_b):
                continue
            key = (mkt_a.id, mkt_b.id)
            if key in seen:
                continue
            seen.add(key)
            matches.append((mkt_a, mkt_b, float(score)))

    return matches
