"""Dashboard dump source: JSON saved by the operator's bookmarklet (tools/bookmarklet.js) while they browse
affiliate.shopee.co.th/offer/product_offer in their own logged-in browser.

The bookmarklet calls the same endpoint the page itself uses (/api/v3/offer/product/list) a few times with
human-like pauses and downloads the raw response. No bot logs in, no anti-bot is bypassed; parsing lives here
so it can be fixed/tested without reinstalling the bookmarklet.

Observed response shape (2026-11-11): data.list[] items with
  item_id, long_link (affiliate link), product_link, default_commission_rate "7%", seller_commission_rate "5%",
  batch_item_for_item_card_full{ name, images[], price (THB*100000), historical_sold, sold, stock,
  item_rating.rating_star, shop_name, brand, tier_variations[{name, options[]}], catid }
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

from ..config import Config
from ..schemas import Candidate

IMG_CDN = "https://down-th.img.susercontent.com/file/"
PRICE_DIV = 100000


def _pct(v) -> float | None:
    try:
        x = float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
    return x / 100 if x > 0 else None


def parse_item(it: dict, captured_at: str) -> tuple[Candidate, dict] | None:
    card = it.get("batch_item_for_item_card_full") or {}
    name = card.get("name")
    if not name:
        return None
    price = card.get("price") or card.get("price_min")
    shopee_rate, seller_rate = _pct(it.get("default_commission_rate")), _pct(it.get("seller_commission_rate"))
    rating = (card.get("item_rating") or {}).get("rating_star")
    variants = [f"{t.get('name', '')}: {', '.join(o for o in t.get('options', []) if o)}"
                for t in card.get("tier_variations") or [] if t.get("options")]
    c = Candidate(
        source="dashboard", source_ref=str(it.get("item_id") or card.get("itemid")), observed_at=captured_at,
        name=name.strip(), listing_url=it.get("product_link", ""), affiliate_link=it.get("long_link"),
        shop_name=card.get("shop_name"), price=int(price) / PRICE_DIV if price else None,
        commission_rate=shopee_rate, commission_verified=shopee_rate is not None,
        sales_count=card.get("historical_sold"), rating=round(rating, 2) if rating else None,
        category=str(card.get("catid")) if card.get("catid") else None,
        image_urls=[IMG_CDN + i for i in card.get("images") or []],
        limitations=["commission = rate shown in operator's affiliate dashboard at capture time "
                     f"(seller extra: {it.get('seller_commission_rate', '?')})",
                     "sales_count = Shopee historical_sold (rounded by Shopee)",
                     "seller listing images — usable only with allow_listing_images"])
    extra = {"variants": variants, "stock": card.get("stock"), "brand": card.get("brand") or None,
             "seller_rate": seller_rate}
    return c, extra


class DashboardSource:
    name = "dashboard"

    def __init__(self, path: str | Path):
        pat = str(Path(path).expanduser())
        self.paths = [Path(x) for x in sorted(glob.glob(pat))] if any(ch in pat for ch in "*?") else [Path(pat)]
        self.paths = self.paths[-1:] if len(self.paths) > 1 else self.paths  # newest dump (dated filename) only
        if not self.paths or not self.paths[0].exists():
            raise FileNotFoundError(
                f"ไม่เจอไฟล์ {path}\n"
                "   1) เปิด https://affiliate.shopee.co.th/offer/product_offer ใน Chrome/Safari (login แล้ว)\n"
                "   2) กด bookmark 'ส่งให้ bot' (ติดตั้ง: python -m agent bookmarklet | pbcopy)\n"
                "   3) รอ alert 'บันทึก N สินค้าแล้ว' แล้วรันคำสั่งนี้ใหม่ (หรือระบุไฟล์เอง: --file <path>)")

    def search(self, cfg: Config) -> list[Candidate]:
        self.extra: dict[str, dict] = {}
        seen, out = set(), []
        for p in self.paths:
            dump = json.loads(Path(p).read_text(encoding="utf-8"))
            items = dump.get("list") if isinstance(dump, dict) else dump
            for it in items or []:
                got = parse_item(it, dump.get("captured_at", "") if isinstance(dump, dict) else "")
                if not got:
                    continue
                c, extra = got
                if c.source_ref in seen or extra["stock"] == 0:
                    continue
                seen.add(c.source_ref)
                self.extra[c.source_ref] = extra
                out.append(c)
        return out
