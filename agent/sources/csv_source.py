"""CSV source: rows the operator copied/exported from the Shopee Affiliate dashboard (their own account).

Columns (header names, any order; extra columns ignored):
  name, listing_url, affiliate_link, price, commission_rate (7 or 7% or 0.07), sales_count, rating,
  shop_name, category, image_urls (separated by space or |)
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from ..config import Config
from ..schemas import Candidate


def _f(v: str | None) -> float | None:
    if v is None or not str(v).strip():
        return None
    s = str(v).strip().lower().replace(",", "")
    mult = 1.0
    if s.endswith("k"):
        s, mult = s[:-1], 1000.0
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) * mult if m else None


def _rate(v: str | None) -> float | None:
    x = _f(v)
    if x is None:
        return None
    return x / 100 if x > 1 else x


class CsvSource:
    name = "csv"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def search(self, cfg: Config) -> list[Candidate]:
        out = []
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f)):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                if not row.get("name") or not row.get("listing_url"):
                    continue
                sales = _f(row.get("sales_count"))
                out.append(Candidate(
                    source="csv", source_ref=f"{self.path.name}#{i + 2}", name=row["name"],
                    listing_url=row["listing_url"], affiliate_link=row.get("affiliate_link") or None,
                    shop_name=row.get("shop_name") or None, price=_f(row.get("price")),
                    commission_rate=_rate(row.get("commission_rate")), commission_verified=False,
                    sales_count=int(sales) if sales is not None else None, rating=_f(row.get("rating")),
                    category=row.get("category") or None,
                    image_urls=[u for u in re.split(r"[\s|]+", row.get("image_urls", "")) if u],
                    limitations=["copied from affiliate dashboard by operator; values as of export time"]))
        return out
