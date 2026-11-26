"""Local, documented media grants used by the autonomous candidate selector.

The registry is an operator-provided, versioned input. This module checks that its
documents and media exist and records their hashes; it cannot interpret a license
on behalf of a human reviewer.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .schemas import Candidate
from .util import StepError, sha256

PLATFORMS = {"shopee", "tiktok"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class MediaGrant(BaseModel):
    listing_url: str = Field(min_length=1)
    media_path: Path
    evidence_path: Path
    owner: str = Field(min_length=1)
    license: str = Field(min_length=1)
    kind: Literal["owned", "licensed"]
    origin: Literal["operator_capture", "brand_supplied"]
    platforms: list[Literal["shopee", "tiktok"]]
    commercial_use: bool
    expires_at: date | None = None
    source_url: str | None = None
    media_sha256: str | None = None
    cleaned_media_path: Path | None = None
    cleaned_media_sha256: str | None = None
    cleaning_method: Literal["crop", "image_edit"] | None = None

    def resolved(self, base: Path) -> "MediaGrant":
        data = self.model_dump()
        for key in ("media_path", "evidence_path", "cleaned_media_path"):
            if data.get(key) is not None:
                p = Path(data[key])
                data[key] = (p if p.is_absolute() else base / p).resolve()
        return MediaGrant.model_validate(data)

    def check(self) -> list[str]:
        errors = []
        if (self.kind == "owned" and self.origin != "operator_capture") or (self.kind == "licensed" and self.origin != "brand_supplied"):
            errors.append("media kind and origin disagree")
        if self.source_url and "img.susercontent.com" in self.source_url.lower():
            errors.append("seller listing CDN image is not an accepted reference")
        if set(self.platforms) != PLATFORMS:
            errors.append("grant must cover Shopee and TikTok")
        if not self.commercial_use:
            errors.append("commercial use not granted")
        if self.expires_at and self.expires_at < date.today():
            errors.append("grant expired")
        if self.media_path.suffix.lower() not in IMAGE_SUFFIXES or not self.media_path.is_file():
            errors.append(f"media file missing/unsupported: {self.media_path}")
        if not self.evidence_path.is_file() or self.evidence_path.stat().st_size == 0:
            errors.append(f"evidence file missing/empty: {self.evidence_path}")
        if self.media_sha256 and self.media_path.is_file() and sha256(self.media_path) != self.media_sha256:
            errors.append(f"media hash mismatch: {self.media_path}")
        if self.cleaned_media_path:
            if not self.cleaning_method:
                errors.append("cleaning_method required for cleaned media")
            if self.cleaned_media_path.suffix.lower() not in IMAGE_SUFFIXES or not self.cleaned_media_path.is_file():
                errors.append(f"cleaned media file missing/unsupported: {self.cleaned_media_path}")
            elif self.cleaned_media_sha256 and sha256(self.cleaned_media_path) != self.cleaned_media_sha256:
                errors.append(f"cleaned media hash mismatch: {self.cleaned_media_path}")
        return errors


class RightsRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise StepError(f"BLOCKED: rights registry missing: {self.path}")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.grants = [MediaGrant.model_validate(x).resolved(self.path.parent) for x in raw["grants"]]
        except (ValueError, KeyError, TypeError) as e:
            raise StepError(f"BLOCKED: invalid rights registry: {e}") from e

    def for_candidate(self, candidate: Candidate, minimum: int = 3) -> tuple[list[MediaGrant], list[str]]:
        matches = [g for g in self.grants if g.listing_url == candidate.listing_url]
        if not matches:
            return [], ["no media grant for listing"]
        valid, reasons, seen = [], [], set()
        for g in matches:
            errors = g.check()
            if errors:
                reasons.extend(errors)
                continue
            digest = sha256(g.media_path)
            if digest in seen:
                reasons.append(f"duplicate media: {g.media_path}")
                continue
            seen.add(digest)
            valid.append(g)
        if len(valid) < minimum:
            reasons.append(f"only {len(valid)} documented images; need {minimum}")
        return (valid if len(valid) >= minimum else []), reasons


def read_manifest(path: Path) -> dict[str, MediaGrant]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    grants = [MediaGrant.model_validate(x) for x in raw["grants"]]
    return {str(g.media_path.resolve()): g for g in grants}
