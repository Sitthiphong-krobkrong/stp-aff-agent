import json
from pathlib import Path

import pytest

from agent import claims, creative_quality
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


def test_csv_facts_reach_product_without_invented_attributes(tmp_path):
    from agent.cli import write_inbox

    csv_path = tmp_path / "offers.csv"
    csv_path.write_text(
        "name,listing_url,fact_1,fact_2,observed_at\n"
        "เครื่องบดสับ,https://example.test/item,โถ 250 มล.,ชาร์จ USB,2026-11-15T10:00:00+07:00\n",
        encoding="utf-8",
    )
    src = CsvSource(csv_path)
    candidate = src.search(Config())[0]
    product_dir = write_inbox(candidate, src.extra[candidate.source_ref], tmp_path / "inbox")
    product = product_from_folder(product_dir)[0]

    assert src.extra[candidate.source_ref]["facts"] == ["โถ 250 มล.", "ชาร์จ USB"]
    assert list(product.facts.values()) == ["โถ 250 มล.", "ชาร์จ USB"]


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


def test_price_is_forbidden_in_voice_screen_and_caption():
    vp = demo_plan()
    vp.shots[0].vo = "ราคา 299 บาท"
    vp.shots[1].head = "฿299"
    vp.shopee_caption = "ดูราคาปัจจุบัน"
    errs = claims.check(vp, demo_product(), Config().banned_words)
    assert any("shot1.vo: price mention 'ราคา'" in e for e in errs)
    assert any("shot2.head: price mention '฿'" in e for e in errs)
    assert any("shopee_caption: price mention 'ราคา'" in e for e in errs)


def test_price_number_not_offered_as_script_evidence():
    p = demo_product()
    p.name = "โคมไฟ"
    p.facts = {"สี": "ขาว", "ราคา/โปร": "299"}
    p.price = 299
    assert "299" not in claims.evidence_numbers(p)


def test_director_prompt_hides_price_data():
    from agent.director import build_prompt

    p = demo_product()
    prompt = build_prompt(p, [], Config())
    facts = prompt.split("FACTS:\n", 1)[1].split("\nIMAGES:", 1)[0]
    assert "ราคา" not in facts and "299" not in facts


def test_banned_and_avoid_words_blocked():
    vp = demo_plan()
    vp.shots[1].vo = "ดีที่สุด ถนอมสายตา 100%"
    errs = claims.check(vp, demo_product(), Config().banned_words)
    assert any("ดีที่สุด" in e for e in errs) and any("avoid_claim" in e for e in errs)


def test_battery_head_needs_star():
    vp = demo_plan()
    vp.shots[5].head = "แบต 2000mAh"
    assert any("footnote" in e for e in claims.check(vp, demo_product(), Config().banned_words))


def test_creative_gate_rejects_generic_hook_and_unsupported_outcome():
    vp = demo_plan()
    vp.shots[0].head = "ต้องมี!"
    vp.shots[0].vo = "คุณแม่ต้องมี ดูตัวนี้ก่อน"
    vp.shots[2].vo = "ลูกทานง่าย คุ้มมาก"
    errors = creative_quality.check(vp, demo_product())
    assert any("generic opener" in e for e in errors)
    assert any("no recognizable product attribute" in e for e in errors)
    assert any("ลูกทานง่าย" in e for e in errors)
    assert any("คุ้มมาก" in e for e in errors)


def test_creative_gate_accepts_specific_factual_hook():
    vp = demo_plan()
    vp.shots[0].head = "โคมไฟพับได้"
    vp.shots[0].vo = "โคมไฟตั้งโต๊ะที่พับได้ รุ่นนี้มีอะไรให้ดูบ้าง"
    assert creative_quality.check(vp, demo_product()) == []


def test_creative_gate_accepts_fact_based_hook_without_product_name():
    vp = demo_plan()
    vp.shots[0].head = "พับเก็บได้"
    vp.shots[0].vo = "พับเก็บได้ รุ่นนี้จัดวางยังไง"
    p = demo_product()
    p.facts = {"feature": "พับเก็บได้"}
    assert creative_quality.check(vp, p) == []


def test_creative_gate_blocks_unproved_claims_seen_in_live_ollama_sample():
    vp = demo_plan()
    vp.shots[1].vo = "ไม่ต้องต้มให้ยุ่ง"
    vp.shots[2].vo = "มีดสแตนเลส ปลอดภัย ทำความสะอาดง่าย"
    errors = creative_quality.check(vp, demo_product())
    assert any("ไม่ต้องต้ม" in e for e in errors)
    assert any("ปลอดภัย" in e for e in errors)
    assert any("ทำความสะอาดง่าย" in e for e in errors)


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


# ---------------------------------------------------------------- dashboard dump
def test_dashboard_dump_parsing():
    from agent.sources.dashboard import DashboardSource
    src = DashboardSource(ROOT / "tests" / "fixtures" / "dashboard_dump.json")
    c = {x.source_ref: x for x in src.search(Config())}
    assert set(c) == {"1001", "1002", "1003"}          # out-of-stock and duplicate dropped
    a = c["1001"]
    assert a.price == 83 and a.commission_rate == pytest.approx(0.10) and a.commission_verified
    assert a.sales_count == 10000 and a.affiliate_link.startswith("https://shopee.co.th/universal-link/")
    assert a.image_urls[0] == "https://down-th.img.susercontent.com/file/th-test-1001-0"
    assert src.extra["1001"]["variants"] == ["สี: ขาว, เทา"]


def test_dashboard_rank_and_inbox(tmp_path):
    from agent.cli import write_inbox
    from agent.sources.dashboard import DashboardSource
    src = DashboardSource(ROOT / "tests" / "fixtures" / "dashboard_dump.json")
    ranked = rank(src.search(Config()), ScoreCfg())
    assert [c.source_ref for c, _ in ranked] == ["1002", "1001", "1003"]
    d = write_inbox(ranked[0][0], src.extra["1002"], tmp_path)
    p = product_from_folder(d)[0]
    assert "180" in "".join(p.facts.values()) and p.price == 178 and p.affiliate_link


# ---------------------------------------------------------------- director retry loop
def test_director_feeds_claim_errors_back_and_retries(monkeypatch):
    import agent.director as director
    from agent.schemas import Asset
    good = (DEMO / "plan.json").read_text(encoding="utf-8")
    bad = good.replace("หรี่ไฟได้ 10 ระดับ เลือก", "หรี่ไฟได้ 12 ระดับ เลือก")
    prompts = []

    def fake(prompt):
        prompts.append(prompt)
        return "<think>x</think>" + (bad if len(prompts) == 1 else good)

    cfg = Config()
    cfg.director.provider = "ollama"
    monkeypatch.setattr(director, "_provider", lambda cfg, pf: (fake, "fake"))
    assets = [Asset(id=f"img0{i}", path="x", sha256="x", width=1000, height=1000) for i in range(5)]
    vp, attempts = director.plan(demo_product(), assets, cfg)
    assert len(attempts) == 2 and attempts[0]["errors"] and not attempts[1]["errors"]
    assert "'12'" in prompts[1]                       # error was fed back to the model
    assert vp.director == "fake"


def test_director_rewrites_generic_hook(monkeypatch):
    import agent.director as director
    from agent.schemas import Asset
    good = json.loads((DEMO / "plan.json").read_text(encoding="utf-8"))
    bad = json.loads(json.dumps(good))
    bad["shots"][0]["head"] = "ของมันต้องมี"
    bad["shots"][0]["vo"] = "คุณแม่ต้องมี ดูตัวนี้ก่อน"
    prompts = []

    def fake(prompt):
        prompts.append(prompt)
        return json.dumps(bad if len(prompts) == 1 else good, ensure_ascii=False)

    cfg = Config()
    monkeypatch.setattr(director, "_provider", lambda cfg, pf: (fake, "fake"))
    assets = [Asset(id=f"img0{i}", path="x", sha256="x", width=1000, height=1000) for i in range(5)]
    _, attempts = director.plan(demo_product(), assets, cfg)
    assert len(attempts) == 2
    assert any("generic opener" in e for e in attempts[0]["errors"])
    assert "generic opener" in prompts[1]
