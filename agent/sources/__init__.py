"""Product sources. Each returns Candidates with evidence; none may invent commission/sales.

Allowed: operator input (manual/csv), Shopee Affiliate Open API (authorized credentials).
Not allowed: scraping Shopee public pages/internal endpoints, bypassing anti-bot or login controls.
"""
from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..schemas import Candidate


class ProductSource(Protocol):
    name: str

    def search(self, cfg: Config) -> list[Candidate]: ...


def get_source(name: str, **kw) -> ProductSource:
    if name == "manual":
        from .manual import ManualSource
        return ManualSource(**kw)
    if name == "csv":
        from .csv_source import CsvSource
        return CsvSource(**kw)
    if name == "dashboard":
        from .dashboard import DashboardSource
        return DashboardSource(**kw)
    if name == "shopee_openapi":
        from .shopee_openapi import ShopeeOpenAPISource
        return ShopeeOpenAPISource(**kw)
    raise ValueError(f"unknown product source: {name}")
