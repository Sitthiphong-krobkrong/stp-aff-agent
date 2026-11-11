"""Deterministic claim gate. The LLM writes; this decides whether the words may ship.

Rules
1. Every number in on-screen text / narration / captions must appear in the product evidence
   (name, facts, price). Numbers are compared after removing thousands separators.
2. No banned words (config) and no product-specific avoid_claims.
3. Battery/durability style claims must carry '*' (footnote "*ตามสเปกผู้ผลิต" is added by renderer).
4. Captions: Shopee caption + hashtags <= 150 (emoji = 2), 3-5 hashtags.
"""
from __future__ import annotations

import re

from .schemas import Product, VideoPlan
from .util import caption_len

NUM = re.compile(r"\d+(?:[.,]\d+)*")
STAR_TRIGGERS = ("แบต", "mAh", "ชั่วโมง", "ทนทาน", "อายุการใช้งาน", "กันน้ำ")


def _nums(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM.findall(text)}


def evidence_numbers(p: Product) -> set[str]:
    blob = " ".join([p.name, *(p.facts.values())] + ([str(int(p.price)) if p.price and p.price == int(p.price)
                                                       else str(p.price)] if p.price else []))
    return _nums(blob)


def shopee_post(plan: VideoPlan) -> str:
    return f"{plan.shopee_caption.strip()} {' '.join(plan.hashtags)}".strip()


def check(plan: VideoPlan, p: Product, banned: list[str]) -> list[str]:
    errs: list[str] = []
    allowed = evidence_numbers(p)
    texts = []
    for i, s in enumerate(plan.shots):
        for field in ("head", "sub", "vo"):
            v = getattr(s, field)
            if v:
                texts.append((f"shot{i + 1}.{field}", v))
    texts += [("shopee_caption", plan.shopee_caption), ("tiktok_caption", plan.tiktok_caption)]

    for where, t in texts:
        for n in _nums(t) - allowed:
            errs.append(f"{where}: number '{n}' not found in product evidence")
        for w in banned:
            if w and w in t:
                errs.append(f"{where}: banned word '{w}'")
        for w in p.avoid_claims:
            if w and w.lower() in t.lower():
                errs.append(f"{where}: avoid_claim '{w}'")
        if where.startswith("shot") and where.endswith(("head", "sub")) and any(k in t for k in STAR_TRIGGERS) \
                and _nums(t) and "*" not in t:
            errs.append(f"{where}: battery/durability figure needs '*' footnote")

    n = caption_len(shopee_post(plan))
    if n > 150:
        errs.append(f"shopee caption+hashtags {n} chars > 150")
    if not 3 <= len(plan.hashtags) <= 5:
        errs.append("need 3-5 hashtags")
    for h in plan.hashtags:
        if not h.startswith("#") or " " in h:
            errs.append(f"bad hashtag '{h}'")
    return errs
