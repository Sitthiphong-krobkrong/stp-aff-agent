"""Director = writes the VideoPlan (shots, Thai VO, captions) from product evidence + usable images.

Providers: ollama (local Qwen), claude_cli (`claude -p`, like studio auto.py), file (pre-written plan.json).
Every attempt is validated (schema + claim gate); errors are fed back for a bounded number of retries.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .. import claims
from ..config import Config
from ..schemas import Asset, Product, VideoPlan
from ..util import StepError, log

PROMPT = """คุณคือ creative director ทำคลิปรีวิวสินค้าแนวตั้ง 9:16 ยาว 20-25 วินาที สำหรับ Shopee Video (ภาษาไทย)
ตอบเป็น JSON เท่านั้น ตาม schema นี้:
{{"shots":[{{"style":"hook|title|spec|cta","asset_id":"img00","head":"ข้อความใหญ่ ≤ 18 ตัว ใช้ | ขึ้นบรรทัด",
  "sub":"ข้อความรอง (ไม่บังคับ)","vo":"บทพากย์ช็อตนี้ 1 ประโยคสั้น","focus":[0.5,0.5]}}],
 "shopee_caption":"แคปชันสั้น","hashtags":["#a","#b","#c"],"tiktok_caption":"แคปชัน TikTok"}}

กฎ:
- 6-8 ช็อต: ช็อตแรก hook, ช็อตที่ 2 title (ชื่อ/ประเภทสินค้า), ถัดมา spec ช็อตละ 1 จุดขาย, ช็อตสุดท้าย cta
- vo รวมทั้งหมดประมาณ 55-75 คำพูด (อ่านจบใน ~22 วินาที) ประโยคพูดธรรมชาติ ไม่อ่านสเปกแบบหุ่นยนต์
- ใช้เฉพาะข้อมูลใน FACTS ห้ามเดาตัวเลข ราคา โปร หรือสเปกที่ไม่มี ตัวเลขทุกตัวต้องมีใน FACTS
- ห้ามพูดว่าใช้เอง/ทดสอบเอง/ขายดีอันดับ 1 ห้ามคำ: {banned}
- ห้ามพูดถึง: {avoid}
- ตัวเลขแบต/ความทน ใน head/sub ใส่ * ต่อท้าย
- cta ชวนกดตะกร้า เช่น "กดดูในตะกร้าได้เลย" ห้ามพูดถึงโค้ด
- asset_id เลือกจากรายการ IMAGES ใช้ซ้ำได้ เลือกรูปที่เหมาะกับข้อความ
- shopee_caption + hashtags รวม ≤ 140 ตัวอักษร, hashtags 3-5 อัน
- tiktok_caption ใส่ #affiliate ด้วย

PRODUCT: {name}
FACTS:
{facts}
IMAGES: {images}
"""


def build_prompt(p: Product, assets: list[Asset], cfg: Config) -> str:
    facts = "\n".join(f"- {k}: {v}" for k, v in p.facts.items()) or "- (ไม่มี)"
    if p.price:
        facts += f"\n- ราคา: {p.price:g} บาท"
    imgs = ", ".join(f"{a.id} ({a.width}x{a.height})" for a in assets)
    return PROMPT.format(banned=", ".join(cfg.banned_words), avoid=", ".join(p.avoid_claims) or "-",
                         name=p.name, facts=facts, images=imgs)


def extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # qwen3 thinking blocks
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def _provider(cfg: Config, plan_file: Path | None):
    name = cfg.director.provider
    if name == "file":
        return lambda prompt: Path(plan_file).read_text(encoding="utf-8"), "file"
    if name == "ollama":
        from .ollama import complete
        return (lambda prompt: complete(prompt, cfg)), f"ollama:{cfg.director.model}"
    if name == "claude_cli":
        from .claude_cli import complete
        return (lambda prompt: complete(prompt, cfg)), "claude_cli"
    raise ValueError(f"unknown director provider {name}")


def plan(p: Product, assets: list[Asset], cfg: Config, plan_file: Path | None = None) -> tuple[VideoPlan, list]:
    complete, label = _provider(cfg, plan_file)
    base = build_prompt(p, assets, cfg)
    ids = {a.id for a in assets}
    attempts, feedback = [], ""
    tries = 1 if cfg.director.provider == "file" else cfg.director.retries
    for n in range(1, tries + 1):
        prompt = base + (f"\nแก้ข้อผิดพลาดจากรอบก่อน:\n{feedback}" if feedback else "")
        raw = complete(prompt)
        try:
            vp = VideoPlan.model_validate({**extract_json(raw), "director": label})
            errs = [f"shot{i + 1}: unknown asset_id {s.asset_id}" for i, s in enumerate(vp.shots)
                    if s.asset_id not in ids]
            errs += claims.check(vp, p, cfg.banned_words)
        except (ValueError, ValidationError) as e:
            vp, errs = None, [str(e)[:800]]
        attempts.append({"attempt": n, "errors": errs})
        log.info("director attempt %d: %d errors", n, len(errs))
        if vp and not errs:
            return vp, attempts
        feedback = "\n".join(f"- {e}" for e in errs[:15])
    raise StepError(f"director failed after {tries} attempts: {attempts[-1]['errors'][:5]}")
