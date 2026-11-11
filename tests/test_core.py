import json
from pathlib import Path

import pytest

from agent import claims
from agent.config import Config, ScoreCfg
from agent.render import plan_timing, wrap, font, _split_safe
from agent.schemas import Candidate, Product, VideoPlan
from agent.scoring import rank, score
from agent.sources.csv_source import CsvSource
from agent.sources.manual import parse_product_txt, product_from_folder
from agent.sources.shopee_openapi import sign
from agent.util import caption_len

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo-lamp"


def demo_plan(**over) -> VideoPlan:
    d = json.loads((DEMO / "plan.json").read_text(encoding="utf-8"))
    d.update(over)
    return VideoPlan.model_validate(d)


def demo_product() -> Product:
    return product_from_folder(DEMO)[0]


# ---------------------------------------------------------------- sources
def test_parse_studio_product_txt():
    info = parse_product_txt((DEMO / "product.txt").read_text(encoding="utf-8"))
    assert info["name"].startswith("DEMO")
    assert len(info["points"]) == 4
    assert info["code"] == "DEMO-ABC-123"
    assert info["rights"] == "owned"


def test_product_avoid_claims_split():
    p = demo_product()
    assert p.avoid_claims == ["ถนอมสายตา 100%", "ไม่ร้อนเลย"]
    assert p.price == 299
    assert p.hashtags[0] == "#โคมไฟตั้งโต๊ะ"


def test_csv_source_parses_units_and_unknowns():
    c = {x.name[:8]: x for x in CsvSource(ROOT / "examples" / "offers_sample.csv").search(Config())}
    assert c["SAMPLE A"].commission_rate == pytest.approx(0.12)
    assert c["SAMPLE A"].sales_count == 8200
    assert c["SAMPLE C"].commission_rate is None          # unknown stays unknown
    assert c["SAMPLE D"].commission_rate == pytest.approx(0.08)
    assert all(not x.commission_verified for x in c.values())


def test_openapi_signature_is_deterministic():
    assert sign("1", "s", "{}", 100) == sign("1", "s", "{}", 100)
    assert len(sign("1", "s", "{}", 100)) == 64


# ---------------------------------------------------------------- scoring
def test_unknown_is_not_imputed():
    c = Candidate(source="t", source_ref="1", name="x", listing_url="u", image_urls=["a"] * 5)
    s = score(c, ScoreCfg())
    assert s["parts"]["commission"] == 0 and "commission_rate" in s["unknown"]


def test_rank_is_deterministic_and_eligibility_first():
    mk = lambda n, imgs, cr: Candidate(source="t", source_ref=n, name=n, listing_url="u",
                                       image_urls=["i"] * imgs, commission_rate=cr)
    cands = [mk("b", 1, 0.15), mk("a", 5, 0.05), mk("c", 5, 0.05)]
    order = [c.name for c, _ in rank(cands, ScoreCfg())]
    assert order == ["a", "c", "b"]  # ineligible last; ties broken by name
    assert order == [c.name for c, _ in rank(list(reversed(cands)), ScoreCfg())]


# ---------------------------------------------------------------- claim gate
def test_demo_plan_passes_claim_gate():
    assert claims.check(demo_plan(), demo_product(), Config().banned_words) == []


def test_invented_number_is_blocked():
    vp = demo_plan()
    vp.shots[3].vo = "หรี่ไฟได้ 12 ระดับ"
    errs = claims.check(vp, demo_product(), Config().banned_words)
    assert any("'12'" in e for e in errs)


def test_banned_and_avoid_words_blocked():
    vp = demo_plan()
    vp.shots[1].vo = "ดีที่สุด ถนอมสายตา 100%"
    errs = claims.check(vp, demo_product(), Config().banned_words)
    assert any("ดีที่สุด" in e for e in errs) and any("avoid_claim" in e for e in errs)


def test_battery_head_needs_star():
    vp = demo_plan()
    vp.shots[5].head = "แบต 2000mAh"
    assert any("footnote" in e for e in claims.check(vp, demo_product(), Config().banned_words))


def test_caption_length_counts_emoji_as_two():
    assert caption_len("ab💡") == 4
    assert caption_len("👍🏻") == 4
    vp = demo_plan(shopee_caption="ก" * 150)
    assert any("> 150" in e for e in claims.check(vp, demo_product(), []))


def test_plan_schema_requires_hook_and_cta():
    d = json.loads((DEMO / "plan.json").read_text(encoding="utf-8"))
    d["shots"][0]["style"] = "spec"
    with pytest.raises(Exception):
        VideoPlan.model_validate(d)


# ---------------------------------------------------------------- render helpers
def test_timing_fits_max_duration_and_caps_tempo():
    cfg = Config()
    t = plan_timing([2.0] * 7, ["hook"] + ["spec"] * 5 + ["cta"], cfg)
    assert t.tempo == 1.0 and t.total <= cfg.video.max_duration
    t2 = plan_timing([5.0] * 7, ["hook"] + ["spec"] * 5 + ["cta"], cfg)
    assert t2.tempo == cfg.video.max_tempo and t2.warning


def test_thai_split_keeps_marks_with_base():
    a, b = _split_safe("ที่สุด", 2)  # index 2 is a tone mark → must move left
    assert not b or b[0] not in "่ี"
    assert a + b == "ที่สุด"


def test_wrap_respects_width():
    from PIL import Image, ImageDraw
    cfg = Config()
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f = font(str(cfg.fonts_dir), "SemiBold", 58)
    lines = wrap(d, "เปลี่ยนแสงได้ 3 โหมด ขาว วอร์ม และธรรมชาติ ใช้ได้ทั้งอ่านหนังสือและทำงาน", f, 900)
    assert len(lines) >= 2 and all(d.textlength(l, font=f) <= 900 for l in lines)
