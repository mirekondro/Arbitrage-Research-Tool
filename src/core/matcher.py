import re
from datetime import timedelta
from typing import Optional

from datetime import datetime
from rapidfuzz import fuzz, process

from src.models import Market

SIMILARITY_THRESHOLD = 72.0
DATE_WINDOW_DAYS = 45


def _normalize(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\b(will|the|a|an|in|by|for|to|of|on|be|is|are|does|did|can|would)\b", "", title)
    title = re.sub(r"[^\w\s]", " ", title)
    return " ".join(title.split())


def _jaccard(norm_a: str, norm_b: str) -> float:
    """Token-level Jaccard similarity: |A∩B| / |A∪B|."""
    sa = set(norm_a.split())
    sb = set(norm_b.split())
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def _dates_close(a: Market, b: Market) -> bool:
    if a.close_time is None or b.close_time is None:
        return True
    # Normalise to naive UTC before subtracting to avoid tz-aware vs tz-naive errors
    def _naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    diff = abs((_naive(a.close_time) - _naive(b.close_time)).total_seconds())
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
            norm_b = b_norms[idx]
            # Guard against same-template/different-entity false positives
            # (e.g. "Will Trump pardon Musk" vs "Will Trump pardon Maxwell").
            # Require ≥40% token-level Jaccard overlap so we share the key noun.
            if _jaccard(norm_a, norm_b) < 0.40:
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
