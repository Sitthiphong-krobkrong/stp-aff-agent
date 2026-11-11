"""Typed contracts between pipeline stages. Every model output is validated against these before use."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ product / offer
class Candidate(BaseModel):
    """One product listing as seen by a ProductSource. Unknown values stay None (never 0)."""
    source: str                               # e.g. "manual", "shopee_openapi", "csv"
    source_ref: str                           # id/url inside that source
    observed_at: str = Field(default_factory=now_iso)
    name: str
    listing_url: str
    affiliate_link: Optional[str] = None
    shop_name: Optional[str] = None
    price: Optional[float] = None             # THB
    commission_rate: Optional[float] = None   # 0.07 = 7%; None = unknown
    commission_verified: bool = False         # True only when read from an authorized record
    sales_count: Optional[int] = None         # as reported by the source; None = unknown
    rating: Optional[float] = None
    category: Optional[str] = None
    image_urls: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)  # what this source cannot tell us


class Product(BaseModel):
    """Facts the script may use. Only values in `facts`, `price`, `name` may be stated in the video."""
    id: str
    name: str
    brand: Optional[str] = None
    listing_url: str
    affiliate_link: Optional[str] = None
    price: Optional[float] = None
    facts: dict[str, str] = Field(default_factory=dict)       # "แบต": "5000mAh*", ...
    avoid_claims: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    tiktok_code: Optional[str] = None         # Shopee search code for TikTok comment; only if provided
    source: str = "manual"
    observed_at: str = Field(default_factory=now_iso)


# ------------------------------------------------------------------ assets / rights
class RightsStatus(str, Enum):
    OWNED = "owned"                           # operator shot it
    LICENSED = "licensed"                     # documented license covering Shopee + TikTok
    LISTING_RISK_ACCEPTED = "listing_image_risk_accepted"  # seller listing image, operator accepted risk
    UNKNOWN = "unknown"


class Asset(BaseModel):
    id: str
    kind: Literal["image", "video"] = "image"
    path: str                                  # relative to run dir
    sha256: str
    source_url: Optional[str] = None
    width: int
    height: int
    rights: RightsStatus = RightsStatus.UNKNOWN
    rights_note: str = ""
    ingested_at: str = Field(default_factory=now_iso)
    rejected: Optional[str] = None             # reason if filtered out


# ------------------------------------------------------------------ plan (director output)
class Shot(BaseModel):
    style: Literal["hook", "title", "spec", "cta"]
    asset_id: str
    head: str = Field(min_length=1, max_length=40)    # big text; "|" = line break
    sub: Optional[str] = Field(default=None, max_length=60)
    vo: str = Field(min_length=2, max_length=140)     # Thai narration for this shot (also the subtitle)
    focus: tuple[float, float] = (0.5, 0.5)

    @field_validator("focus")
    @classmethod
    def _focus(cls, v):
        x, y = v
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("focus must be within 0..1")
        return v


class VideoPlan(BaseModel):
    shots: list[Shot] = Field(min_length=5, max_length=9)
    shopee_caption: str
    hashtags: list[str] = Field(min_length=3, max_length=5)
    tiktok_caption: str
    director: str = "unknown"                  # provider/model that wrote it

    @field_validator("shots")
    @classmethod
    def _order(cls, shots):
        if shots[0].style != "hook":
            raise ValueError("first shot must be style=hook")
        if shots[-1].style != "cta":
            raise ValueError("last shot must be style=cta")
        return shots


# ------------------------------------------------------------------ QA / package
class Check(BaseModel):
    name: str
    ok: bool
    blocking: bool = True
    detail: str = ""


class QAReport(BaseModel):
    checks: list[Check] = Field(default_factory=list)
    publishable: bool = False
    created_at: str = Field(default_factory=now_iso)

    def add(self, name: str, ok: bool, detail: str = "", blocking: bool = True):
        self.checks.append(Check(name=name, ok=ok, detail=detail, blocking=blocking))

    def finalize(self) -> "QAReport":
        self.publishable = all(c.ok for c in self.checks if c.blocking)
        return self
