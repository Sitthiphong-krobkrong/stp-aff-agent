"""Ingest product reference images with documented commercial rights for both platforms."""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

from .config import Config
from .rights import MediaGrant
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


def usable(a: Asset) -> bool:
    evidence = Path(a.rights_evidence_path) if a.rights_evidence_path else None
    return bool(a.rejected is None and a.rights in (RightsStatus.OWNED, RightsStatus.LICENSED)
                and a.rights_owner and a.rights_license
                and set(a.allowed_platforms) == {"shopee", "tiktok"}
                and evidence and evidence.is_file() and a.rights_evidence_sha256
                and sha256(evidence) == a.rights_evidence_sha256)


def ingest(sources: list[str], run_dir: Path, cfg: Config, declared_rights: str | None,
           grants: dict[str, MediaGrant] | None = None) -> list[Asset]:
    adir = run_dir / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    assets: list[Asset] = []
    seen: set[str] = set()
    for i, src in enumerate(sources):
        grant = (grants or {}).get(str(Path(src).resolve())) if not src.startswith(("http://", "https://")) else None
        aid = f"img{i:02d}"
        if grant is None:
            assets.append(Asset(id=aid, path="", sha256="", source_url=src, width=0, height=0,
                                rights=RightsStatus.UNKNOWN, rights_note="no documented media grant",
                                rejected="no documented media grant; source image not fetched"))
            continue
        grant_errors = grant.check()
        rights = RightsStatus(grant.kind) if not grant_errors else RightsStatus.UNKNOWN
        note = f"documented: {grant.license}" if not grant_errors else "; ".join(grant_errors)
        if grant_errors:
            assets.append(Asset(id=aid, path="", sha256="", source_url=src, width=0, height=0,
                                rights=RightsStatus.UNKNOWN, rights_note=note,
                                rejected="invalid rights grant: " + "; ".join(grant_errors)))
            continue
        evidence_hash = sha256(grant.evidence_path)
        evidence_copy = adir / "evidence" / f"{evidence_hash}{grant.evidence_path.suffix.lower()}"
        evidence_copy.parent.mkdir(parents=True, exist_ok=True)
        if not evidence_copy.exists():
            shutil.copy2(grant.evidence_path, evidence_copy)
        original = adir / "original" / f"{aid}{Path(src).suffix.lower()}"
        original.parent.mkdir(parents=True, exist_ok=True)
        clean_input = grant.cleaned_media_path or Path(src)
        grant_fields = {"rights_owner": grant.owner, "rights_license": grant.license,
                        "rights_evidence_path": str(evidence_copy),
                        "rights_evidence_sha256": sha256(evidence_copy),
                        "source_media_sha256": sha256(grant.media_path),
                        "allowed_platforms": list(grant.platforms),
                        "reference_original_path": str(original.relative_to(run_dir)),
                        "reference_cleaning": grant.cleaning_method or "none"}
        try:
            _fetch(src, original)
            with Image.open(clean_input) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                w, h = im.size
                out = adir / f"{aid}.jpg"
                im.save(out, quality=92)
        except Exception as e:  # noqa: BLE001 - record and continue with other images
            assets.append(Asset(id=aid, path="", sha256="", source_url=src, width=0, height=0,
                                rights=rights, rights_note=note, rejected=f"fetch/decode failed: {e}",
                                **grant_fields))
            continue
        digest = sha256(out)
        a = Asset(id=aid, path=str(out.relative_to(run_dir)), sha256=digest,
                  source_url=grant.source_url or src if grant else src, width=w,
                  height=h, rights=rights, rights_note=note, **grant_fields)
        if digest in seen:
            a.rejected = "duplicate image"
        elif min(w, h) < MIN_SIDE:
            a.rejected = f"too small ({w}x{h}, need short side >= {MIN_SIDE})"
        seen.add(digest)
        assets.append(a)
    write_json(run_dir / "assets" / "assets.json", [a.model_dump(mode="json") for a in assets])
    return assets
