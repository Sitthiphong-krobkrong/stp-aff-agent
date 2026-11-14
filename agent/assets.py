"""Ingest product images into a run: copy/download, hash, measure, filter, attach rights status.

Rights gate (fail closed): an asset is usable only if rights is OWNED/LICENSED, or it is a seller listing
image AND config.allow_listing_images is true (operator explicitly accepted that risk).
"""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

from .config import Config
from .schemas import Asset, RightsStatus
from .util import sha256, write_json

MIN_SIDE = 480
UA = "stp-aff-agent/0.1 (+operator-run)"


def _fetch(src: str, dst: Path) -> None:
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r, open(dst, "wb") as f:
            shutil.copyfileobj(r, f)
    else:
        shutil.copyfile(src, dst)


def rights_for(declared: str | None, cfg: Config) -> tuple[RightsStatus, str]:
    d = (declared or "listing").strip().lower()
    if d in ("owned", "own", "ถ่ายเอง"):
        return RightsStatus.OWNED, "operator declared: own photos"
    if d in ("licensed", "license"):
        return RightsStatus.LICENSED, "operator declared: licensed (attach evidence in rights_note)"
    if cfg.allow_listing_images:
        return RightsStatus.LISTING_RISK_ACCEPTED, "seller listing image; operator accepted risk via config"
    return RightsStatus.UNKNOWN, "seller listing image; not allowed (allow_listing_images=false)"


def usable(a: Asset) -> bool:
    return a.rejected is None and a.rights in (RightsStatus.OWNED, RightsStatus.LICENSED,
                                               RightsStatus.LISTING_RISK_ACCEPTED)


def ingest(sources: list[str], run_dir: Path, cfg: Config, declared_rights: str | None) -> list[Asset]:
    adir = run_dir / "assets"
    adir.mkdir(exist_ok=True)
    rights, note = rights_for(declared_rights, cfg)
    assets: list[Asset] = []
    seen: set[str] = set()
    for i, src in enumerate(sources):
        raw = adir / f"raw_{i:02d}"
        aid = f"img{i:02d}"
        try:
            _fetch(src, raw)
            with Image.open(raw) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                w, h = im.size
                out = adir / f"{aid}.jpg"
                im.save(out, quality=92)
        except Exception as e:  # noqa: BLE001 - record and continue with other images
            assets.append(Asset(id=aid, path="", sha256="", source_url=src, width=0, height=0,
                                rights=rights, rights_note=note, rejected=f"fetch/decode failed: {e}"))
            continue
        finally:
            raw.unlink(missing_ok=True)
        digest = sha256(out)
        a = Asset(id=aid, path=str(out.relative_to(run_dir)), sha256=digest, source_url=src, width=w,
                  height=h, rights=rights, rights_note=note)
        if digest in seen:
            a.rejected = "duplicate image"
        elif min(w, h) < MIN_SIDE:
            a.rejected = f"too small ({w}x{h}, need short side >= {MIN_SIDE})"
        seen.add(digest)
        assets.append(a)
    write_json(run_dir / "assets" / "assets.json", [a.model_dump(mode="json") for a in assets])
    return assets
