"""Deterministic candidate ranking with a full breakdown. Unknown inputs score 0 for that factor and are
listed as unknown — they are never imputed."""
from __future__ import annotations

import math

from .config import ScoreCfg
from .schemas import Candidate


def score(c: Candidate, s: ScoreCfg) -> dict:
    parts, unknown, reasons = {}, [], []

    if c.commission_rate is None:
        parts["commission"] = 0.0; unknown.append("commission_rate")
    else:  # 0%..15% → 0..1
        parts["commission"] = min(c.commission_rate / 0.15, 1.0)

    if c.sales_count is None:
        parts["sales"] = 0.0; unknown.append("sales_count")
    else:  # log scale: 10 → ~0.25, 10k → 1
        parts["sales"] = min(math.log10(c.sales_count + 1) / 4, 1.0)

    if c.rating is None:
        parts["rating"] = 0.0; unknown.append("rating")
    else:
        parts["rating"] = max(0.0, min((c.rating - 4.0) / 1.0, 1.0))

    if c.price is None:
        parts["price"] = 0.0; unknown.append("price")
    elif s.price_sweet_min <= c.price <= s.price_sweet_max:
        parts["price"] = 1.0
    else:
        parts["price"] = 0.4
        reasons.append(f"price {c.price:.0f} outside sweet spot {s.price_sweet_min:.0f}-{s.price_sweet_max:.0f}")

    n_img = len(c.image_urls)
    parts["images"] = min(n_img / max(s.min_images, 1), 1.0)
    eligible = n_img >= s.min_images
    if not eligible:
        reasons.append(f"only {n_img} images (need {s.min_images})")
    if not c.listing_url:
        eligible = False; reasons.append("no listing url")

    w = {"commission": s.w_commission, "sales": s.w_sales, "rating": s.w_rating, "price": s.w_price,
         "images": s.w_images}
    total = sum(parts[k] * w[k] for k in w)
    return {"name": c.name, "source_ref": c.source_ref, "total": round(total, 4),
            "parts": {k: round(v, 3) for k, v in parts.items()}, "weights": w, "unknown": unknown,
            "eligible": eligible, "reasons": reasons, "commission_verified": c.commission_verified}


def rank(cands: list[Candidate], s: ScoreCfg) -> list[tuple[Candidate, dict]]:
    scored = [(c, score(c, s)) for c in cands]
    # eligible first, then score, then name for a stable deterministic order
    return sorted(scored, key=lambda x: (not x[1]["eligible"], -x[1]["total"], x[0].name))
