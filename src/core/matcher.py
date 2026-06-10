import re
from datetime import timedelta
from typing import Optional

from datetime import datetime
from rapidfuzz import fuzz, process

from src.models import Market

SIMILARITY_THRESHOLD = 70.0   # was 72 — loosened to catch cross-platform finance titles
DATE_WINDOW_DAYS = 45

# ── Synonym normalisation ──────────────────────────────────────────────────────
#
# Different platforms use different abbreviations for the same entity.
# We collapse them to a canonical token BEFORE stopword removal so Jaccard
# and token_set_ratio comparisons work across platforms.
#
# Rules:
#   - Entity names only (Fed / FOMC → federalreserve, BTC → bitcoin, …)
#   - Do NOT collapse directional words (cut / raise, above / below) — they
#     encode opposite market outcomes and must stay distinct to avoid false arb.
#
_SYNONYMS: list[tuple[str, str]] = [
    # US central bank
    (r"\b(fed|fomc)\b",                     "federalreserve"),
    (r"\bfederal reserve\b",                "federalreserve"),
    # Inflation indices
    (r"\bcpi\b",                            "consumerprices"),
    (r"\bpce\b",                            "consumerprices"),
    (r"\bcore inflation\b",                 "coreinflation"),
    # Jobs / labour
    (r"\bnonfarm payrolls?\b",              "nonfarm"),
    (r"\bjobs report\b",                    "nonfarm"),
    # Macro
    (r"\bgdp\b",                            "economicgrowth"),
    (r"\bus government\b",                  "usgovernment"),
    (r"\bpotus\b",                          "president"),
    (r"\bscotus\b",                         "supremecourt"),
    # Crypto tickers → full names (so BTC on one platform matches Bitcoin on another)
    (r"\bbtc\b",                            "bitcoin"),
    (r"\beth\b",                            "ethereum"),
    (r"\bsol\b",                            "solana"),
    (r"\bxrp\b",                            "ripple"),
    (r"\bbnb\b",                            "binancecoin"),
    (r"\bada\b",                            "cardano"),
    (r"\bdoge\b",                           "dogecoin"),
    # Common ticker abbreviations in market titles
    (r"\bs&p\b",                            "sp500"),
    (r"\bspx\b",                            "sp500"),
    (r"\bsp500\b",                          "sp500"),
    (r"\bnasdaq\b",                         "nasdaq"),
]

# Filler words that add no discriminating signal across platforms
_STOPWORDS = re.compile(
    r"\b(will|the|a|an|in|by|for|to|of|on|be|is|are|does|did|can|would|at|"
    r"end|above|below|reach|hit|exceed|cross|over|under)\b"
)


def _apply_synonyms(title: str) -> str:
    """Replace platform-specific abbreviations with canonical tokens."""
    for pattern, replacement in _SYNONYMS:
        title = re.sub(pattern, replacement, title)
    return title


def _normalize(title: str) -> str:
    title = title.lower()
    title = _apply_synonyms(title)
    title = _STOPWORDS.sub("", title)
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
            # "Will Trump pardon Elon Musk" → {trump, pardon, elon, musk}
            # "Will Trump pardon Ghislaine Maxwell" → {trump, pardon, ghislaine, maxwell}
            # Jaccard = 2/6 = 0.33 < 0.35 → blocked ✓
            # Note: synonym normalization happens before this check, so canonical
            # tokens like "federalreserve" increase overlap for finance markets.
            if _jaccard(norm_a, norm_b) < 0.35:
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
