"""Manual source: a folder per product, using the same product.txt format as stp-aff-studio plus a few keys.

inbox/<product>/
  product.txt     studio format; extra keys:  ลิงก์: <listing url>  ลิงก์ affiliate: <url>
                  ค่าคอม: 7%   ขายแล้ว: 1200   สิทธิ์รูป: owned | listing
                  รูป:  (one image URL per following "- " line)
  images/         optional local images (operator-owned or downloaded by the operator)
"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from ..schemas import Candidate, Product

KEYS = {
    "ชื่อสินค้า": "name", "หมวดสินค้า": "category", "จุดขาย": "points", "สี": "color", "ราคา/โปร": "price",
    "ห้ามพูด": "avoid", "โค้ด Shopee": "code", "ลิงก์": "url", "ลิงก์ affiliate": "aff", "ค่าคอม": "commission",
    "ขายแล้ว": "sold", "สิทธิ์รูป": "rights", "รูป": "images", "แบรนด์": "brand", "แฮชแท็ก": "hashtags",
}
LIST_KEYS = {"points", "images"}


def parse_product_txt(text: str) -> dict:
    out: dict = {"points": [], "images": []}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-") and cur in LIST_KEYS:
            val = line.lstrip("-").strip()
            if val and not val.startswith("("):
                out[cur].append(val)
            continue
        m = re.match(r"^([^:：]+)[:：]\s*(.*)$", line)
        if not m:
            continue
        key = KEYS.get(m.group(1).strip())
        cur = key
        val = m.group(2).strip()
        if not key or not val or val.startswith("("):
            continue
        if key in LIST_KEYS:
            out[key].append(val)
        else:
            out[key] = val
    return out


def _num(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", s)
    return float(m.group(0).replace(",", "")) if m else None


class ManualSource:
    name = "manual"

    def __init__(self, inbox: str | Path):
        self.inbox = Path(inbox)

    def folders(self) -> list[Path]:
        return sorted(p for p in self.inbox.iterdir() if (p / "product.txt").exists())

    def search(self, cfg: Config) -> list[Candidate]:
        out = []
        for d in self.folders():
            info = parse_product_txt((d / "product.txt").read_text(encoding="utf-8"))
            if "name" not in info:
                continue
            local = sorted(str(p) for p in (d / "images").glob("*") if p.suffix.lower() in
                           (".jpg", ".jpeg", ".png", ".webp")) if (d / "images").exists() else []
            comm = _num(info.get("commission"))
            out.append(Candidate(
                source="manual", source_ref=str(d), name=info["name"],
                listing_url=info.get("url", ""), affiliate_link=info.get("aff"),
                price=_num(info.get("price")), category=info.get("category"),
                commission_rate=comm / 100 if comm is not None else None,
                commission_verified=False,  # operator-typed, not an authorized record
                sales_count=int(_num(info.get("sold"))) if info.get("sold") else None,
                image_urls=local + info["images"],
                limitations=["operator-entered data; commission/sales not verified against Shopee records"]))
        return out


def product_from_folder(folder: Path) -> tuple[Product, dict]:
    info = parse_product_txt((Path(folder) / "product.txt").read_text(encoding="utf-8"))
    facts = {f"จุดขาย {i + 1}": p for i, p in enumerate(info["points"])}
    if info.get("color"):
        facts["สี"] = info["color"]
    if info.get("price"):
        facts["ราคา/โปร"] = info["price"]
    avoid = [a.strip() for a in re.split(r"[,，]", info.get("avoid", "")) if a.strip()]
    tags = [t if t.startswith("#") else "#" + t for t in info.get("hashtags", "").split()] if info.get("hashtags") else []
    prod = Product(id=Path(folder).name, name=info["name"], brand=info.get("brand"),
                   listing_url=info.get("url", ""), affiliate_link=info.get("aff"), price=_num(info.get("price")),
                   facts=facts, avoid_claims=avoid, hashtags=tags, tiktok_code=info.get("code"), source="manual")
    return prod, info
