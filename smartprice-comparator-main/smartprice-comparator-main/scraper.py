"""
ai_matcher.py - Multi-result product matcher.
Uses sentence-transformers if available, else falls back to token similarity.
Always returns ALL matching products above threshold (not just one).
"""

import re

# ── Try loading sentence-transformers ──────────────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer, util as st_util
    _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    _USE_ST = True
except Exception:
    _MODEL = None
    _USE_ST = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize(text: str) -> list:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]


def token_similarity(query_tokens: list, product_name: str) -> float:
    if not query_tokens:
        return 0.0
    product_tokens = normalize(product_name)
    product_set = set(product_tokens)
    matched = sum(1 for t in query_tokens if t in product_set)
    base = matched / len(query_tokens)
    phrase_bonus = 0.2 if " ".join(query_tokens) in " ".join(product_tokens) else 0.0
    return min(1.0, base + phrase_bonus)


def semantic_similarity(query: str, product_name: str) -> float:
    try:
        q_emb = _MODEL.encode(query, convert_to_tensor=True)
        p_emb = _MODEL.encode(product_name, convert_to_tensor=True)
        score = float(st_util.cos_sim(q_emb, p_emb)[0][0])
        return max(0.0, score)
    except Exception:
        return 0.0


def compute_similarity(query: str, query_tokens: list, product_name: str) -> float:
    if _USE_ST:
        return semantic_similarity(query, product_name)
    return token_similarity(query_tokens, product_name)


# ── Price parsing ─────────────────────────────────────────────────────────────

def parse_price(price_str) -> float:
    if isinstance(price_str, (int, float)):
        return float(price_str)
    cleaned = re.sub(r"[^\d.]", "", str(price_str))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ── Main matcher ──────────────────────────────────────────────────────────────

def match_products(query: str, products: list, threshold: float = 0.35) -> list:
    """
    Filter and rank ALL products matching the query.

    Returns list of product dicts enriched with:
      - similarity_score  (float)
      - price_numeric     (float)
      - price_display     (str)
    """
    query_tokens = normalize(query)
    scored = []

    for product in products:
        name = product.get("product_name", "")
        score = compute_similarity(query, query_tokens, name)

        if score < threshold:
            continue

        price_numeric = parse_price(product.get("price", 0))
        if price_numeric > 0:
            price_display = f"₹{int(price_numeric):,}"
        else:
            price_display = product.get("price", "Price N/A")  # preserve original like "₹65"

        enriched = {
            **product,
            "similarity_score": round(score, 3),
            "price_numeric": price_numeric,
            "price_display": price_display,
        }
        scored.append(enriched)

    # Sort by similarity desc, then price asc for ties
    scored.sort(key=lambda x: (-x["similarity_score"], x["price_numeric"]))
    return scored