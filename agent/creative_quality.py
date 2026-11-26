"""Small deterministic style gate for AI plans; factual review still belongs to a human."""
from __future__ import annotations

import re

from .schemas import Product, VideoPlan

# These patterns are weak or imply outcomes the supplied listing facts cannot prove.
GENERIC_HOOKS = ("ต้องมี", "เคยได้ยิน", "หลุดมือบ่อย", "รั่วซึมอีกแล้ว", "ใครเคย", "มาดูกัน", "ปัญหานี้")
EMPTY_SALES_LANGUAGE = ("ราคาแค่", "คุ้มมาก", "คุ้มค่า", "ของมันต้องมี", "ห้ามพลาด", "ง่ายสะดวกมาก")
UNSUPPORTED_OUTCOMES = (
    "ไม่ต้องกลัวหลุด", "ลูกทานง่าย", "ใส่ได้ทั้งวัน", "ใช้ได้ทุกที่", "หายห่วง",
    "ไม่ต้องต้ม", "ปลอดภัย", "ทำความสะอาดง่าย", "พกพาได้สะดวก",
)


def _title_anchors(product: Product) -> set[str]:
    """Four-character title fragments allow Thai hooks to use natural word boundaries."""
    title = product.name.lower()
    words = re.findall(r"[ก-๿]{4,}|[a-zA-Z]{3,}", title)
    return {word[i:i + 4] for word in words for i in range(len(word) - 3)}


def check(plan: VideoPlan, product: Product) -> list[str]:
    errors: list[str] = []
    hook = plan.shots[0]
    hook_text = f"{hook.head} {hook.vo}".lower()
    if any(phrase in hook_text for phrase in GENERIC_HOOKS):
        errors.append("hook: generic opener; start with a concrete product attribute or question based on product facts")
    anchors = _title_anchors(product)
    named = any(anchor in hook_text for anchor in anchors)
    fact = any(len(value.strip()) >= 4 and value.strip().lower() in hook_text
               for value in product.facts.values())
    if (anchors or product.facts) and not (named or fact):
        errors.append("hook: no recognizable product attribute from the supplied title or facts")
    for i, shot in enumerate(plan.shots, 1):
        text = f"{shot.head} {shot.sub or ''} {shot.vo}".lower()
        for phrase in EMPTY_SALES_LANGUAGE + UNSUPPORTED_OUTCOMES:
            if phrase in text:
                errors.append(f"shot{i}: unsupported or generic sales phrase '{phrase}'")
    return errors
