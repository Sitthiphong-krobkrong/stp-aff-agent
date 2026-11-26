"""Contract tests for fail-closed autonomous selection and human approval."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from PIL import Image

from agent import cli
from agent.director import build_prompt
from agent.assets import ingest, usable
from agent.config import Config
from agent.qa import subtitle_checks
from agent.render import Timing, srt
from agent.rights import RightsRegistry
from agent.review_web import review_state
from agent.runs import Run
from agent.schemas import Candidate, Product, QAReport
from agent.util import StepError, read_json, write_json


def setup_registry(tmp_path: Path, candidates: list[Candidate]) -> Path:
    evidence = tmp_path / "license.txt"
    evidence.write_text("operator-supplied rights document for both target platforms", encoding="utf-8")
    grants = []
    for n, c in enumerate(candidates):
        for i in range(3):
            media = tmp_path / f"product{n}-image{i}.png"
            Image.new("RGB", (600, 600), (n * 50, i * 60, 30)).save(media)
            grants.append({"listing_url": c.listing_url, "media_path": str(media),
                           "evidence_path": str(evidence), "owner": "Test Operator",
                           "license": "test grant", "kind": "licensed", "origin": "brand_supplied",
                           "platforms": ["shopee", "tiktok"], "commercial_use": True})
    path = tmp_path / "rights_registry.json"
    write_json(path, {"grants": grants})
    return path


def candidates(count: int) -> list[Candidate]:
    return [Candidate(source="csv", source_ref=f"row#{i}", name=f"Product {i}",
                      listing_url=f"https://example.test/product/{i}",
                      commission_rate=(count - i) / 100, image_urls=[]) for i in range(count)]


def auto_args(tmp_path: Path, registry: Path) -> argparse.Namespace:
    source_doc = tmp_path / "source.txt"
    source_doc.write_text("authorized test CSV export", encoding="utf-8")
    (tmp_path / "offers.csv").write_text("name,listing_url,observed_at\n", encoding="utf-8")
    return argparse.Namespace(source="csv", csv=str(tmp_path / "offers.csv"), file="", keyword=None,
                              inbox=str(tmp_path / "inbox"), count=1, max_candidates=3, tts=None,
                              director=None, rights_registry=str(registry), source_evidence=str(source_doc),
                              config=None, plan=None)


def test_registry_rejects_missing_document_and_wrong_platform(tmp_path):
    c = candidates(1)[0]
    registry = setup_registry(tmp_path, [c])
    grants = read_json(registry)["grants"]
    grants[0]["platforms"] = ["shopee"]
    write_json(registry, {"grants": grants})
    valid, reasons = RightsRegistry(registry).for_candidate(c)
    assert not valid and any("Shopee and TikTok" in r for r in reasons)
    grants[0]["platforms"] = ["shopee", "tiktok"]
    Path(grants[1]["evidence_path"]).unlink()
    valid, reasons = RightsRegistry(registry).for_candidate(c)
    assert not valid and any("evidence file missing" in r for r in reasons)


def test_registry_rejects_seller_listing_cdn_reference(tmp_path):
    c = candidates(1)[0]
    registry = setup_registry(tmp_path, [c])
    grants = read_json(registry)["grants"]
    grants[0]["source_url"] = "https://down-th.img.susercontent.com/file/example"
    write_json(registry, {"grants": grants})
    valid, reasons = RightsRegistry(registry).for_candidate(c)
    assert not valid and any("seller listing CDN" in r for r in reasons)


def test_ingest_preserves_document_and_hash_in_run(tmp_path):
    c = candidates(1)[0]
    registry = setup_registry(tmp_path, [c])
    grants, errors = RightsRegistry(registry).for_candidate(c)
    assert not errors and len(grants) == 3
    run_dir = tmp_path / "run"
    assets = ingest([str(g.media_path) for g in grants], run_dir, Config(), "documented",
                    grants={str(g.media_path): g for g in grants})
    assert all(a.rejected is None and a.rights.value == "licensed" for a in assets)
    assert all(Path(a.rights_evidence_path).is_file() for a in assets)
    assert all(set(a.allowed_platforms) == {"shopee", "tiktok"} for a in assets)
    Path(grants[0].evidence_path).unlink()
    assert Path(assets[0].rights_evidence_path).is_file()
    assert (run_dir / assets[0].reference_original_path).is_file()
    assert assets[0].reference_cleaning == "none"


def test_ingest_uses_cleaned_reference_and_retains_original(tmp_path):
    c = candidates(1)[0]
    registry = setup_registry(tmp_path, [c])
    grants = read_json(registry)["grants"]
    clean = tmp_path / "clean-product.png"
    Image.new("RGB", (600, 600), (240, 220, 200)).save(clean)
    grants[0]["cleaned_media_path"] = str(clean)
    grants[0]["cleaning_method"] = "image_edit"
    write_json(registry, {"grants": grants})
    valid, errors = RightsRegistry(registry).for_candidate(c)
    assert not errors
    run_dir = tmp_path / "run"
    assets = ingest([str(g.media_path) for g in valid], run_dir, Config(), "documented",
                    grants={str(g.media_path): g for g in valid})
    assert assets[0].reference_cleaning == "image_edit"
    with Image.open(run_dir / assets[0].path) as rendered_input:
        assert rendered_input.getpixel((300, 300))[0] > 200
    with Image.open(run_dir / assets[0].reference_original_path) as original:
        assert original.getpixel((300, 300))[0] == 0


def test_listing_image_without_grant_is_never_fetched(tmp_path, monkeypatch):
    from agent import assets as assets_mod

    def unexpected_fetch(src, dst):
        raise AssertionError("listing image must not be fetched")

    monkeypatch.setattr(assets_mod, "_fetch", unexpected_fetch)
    out = ingest(["https://example.test/listing.jpg"], tmp_path, Config(),
                 "listing")
    assert len(out) == 1 and out[0].rejected
    assert not usable(out[0]) and not list((tmp_path / "assets").glob("img*.jpg"))


def test_render_refuses_legacy_listing_reference(tmp_path):
    from agent.pipeline import Pipeline
    from agent.schemas import Asset, RightsStatus

    run = Run.create(tmp_path, "legacy listing")
    plan = read_json(Path(__file__).parent.parent / "examples" / "demo-lamp" / "plan.json")
    write_json(run.p("plan.json"), plan)
    ids = {s["asset_id"] for s in plan["shots"]}
    write_json(run.p("assets", "assets.json"), [Asset(id=i, path=f"assets/{i}.jpg",
        sha256="x", width=600, height=600, rights=RightsStatus.LISTING_RISK_ACCEPTED).model_dump()
        for i in ids])
    with pytest.raises(StepError, match="without documented rights"):
        Pipeline(run, Config())._render_variant("shopee")


def test_ai_video_mode_does_not_fall_back_to_stills(tmp_path, monkeypatch):
    from agent import ai_video
    from agent.pipeline import Pipeline
    from agent.schemas import Asset, RightsStatus

    run = Run.create(tmp_path, "ai video")
    plan = read_json(Path(__file__).parent.parent / "examples" / "demo-lamp" / "plan.json")
    write_json(run.p("plan.json"), plan)
    ids = {s["asset_id"] for s in plan["shots"]}
    write_json(run.p("assets", "assets.json"), [Asset(id=i, path=f"assets/{i}.jpg",
        sha256="x", width=600, height=600, rights=RightsStatus.OWNED).model_dump()
        for i in ids])
    monkeypatch.setattr("agent.pipeline.assets_mod.usable", lambda asset: True)
    monkeypatch.setattr(ai_video, "available", lambda: False)
    cfg = Config()
    cfg.video.ai_video = True
    with pytest.raises(StepError, match="LTX-2-mlx is unavailable"):
        Pipeline(run, cfg)._render_variant("shopee")


def test_ai_video_requires_output_rights_evidence_before_assets(tmp_path):
    from agent.pipeline import Pipeline

    run = Run.create(tmp_path, "no model rights")
    cfg = Config()
    cfg.video.ai_video = True
    with pytest.raises(StepError, match="model/output rights evidence is missing"):
        Pipeline(run, cfg).step_assets()


def test_auto_continues_after_failed_candidate_and_records_batch(tmp_path, monkeypatch):
    cs = candidates(3)
    registry = setup_registry(tmp_path, cs)
    args = auto_args(tmp_path, registry)
    cfg = Config(runs_dir=tmp_path / "runs")
    cfg.tts.rights_evidence = tmp_path / "license.txt"
    monkeypatch.setattr(cli, "_cfg", lambda a: cfg)
    monkeypatch.setattr(cli, "_make_source", lambda a: type("Source", (), {"search": lambda self, cfg: cs,
                                                                            "extra": {}})())
    seen = []

    def fake_execute(run, cfg, folder, plan_file):
        seen.append(folder.name)
        if len(seen) == 1:
            run.set_state("QA_DONE", publishable=False)
        else:
            run.p("out", "final.mp4").write_bytes(b"test mp4 placeholder")
            write_json(run.p("out", "qa_report.json"), {"publishable": True})
            run.set_state("READY_FOR_APPROVAL")
        return 0

    monkeypatch.setattr(cli, "_execute", fake_execute)
    assert cli.cmd_auto(args) == 0
    assert len(seen) == 2
    report = read_json(next(cfg.runs_dir.glob("auto-*.json")))
    assert report["status"] == "COMPLETED" and report["ready_packages"] == 1
    assert [x["state"] for x in report["attempts"]] == ["QA_DONE", "READY_FOR_APPROVAL"]
    ledger = read_json(cfg.runs_dir / "made.json")
    assert set(ledger) == {cs[1].source_ref}


def test_auto_blocks_when_fewer_than_three_candidates(tmp_path, monkeypatch):
    cs = candidates(2)
    registry = setup_registry(tmp_path, cs)
    args = auto_args(tmp_path, registry)
    cfg = Config(runs_dir=tmp_path / "runs")
    cfg.tts.rights_evidence = tmp_path / "license.txt"
    monkeypatch.setattr(cli, "_cfg", lambda a: cfg)
    monkeypatch.setattr(cli, "_make_source", lambda a: type("Source", (), {"search": lambda self, cfg: cs})())
    assert cli.cmd_auto(args) == 2
    report = read_json(next(cfg.runs_dir.glob("auto-*.json")))
    assert report["status"] == "BLOCKED" and report["source_count"] == 2
    assert not list(cfg.runs_dir.glob("*/state.json"))


def test_old_ready_state_cannot_be_approved_without_documented_rights(tmp_path):
    run = Run.create(tmp_path, "old-ready")
    run.set_state("READY_FOR_APPROVAL")
    write_json(run.p("out", "qa_report.json"), {"publishable": True,
                                                "checks": [{"name": "rights.assets", "ok": True,
                                                            "blocking": True}]})
    args = argparse.Namespace(run=str(run.path), decision="approve", note="", reviewed=True)
    assert cli.cmd_decide(args) == 2
    assert not run.p("out", "decision.json").exists()


def test_subtitle_gate_catches_text_and_timing_drift(tmp_path):
    path = tmp_path / "final.srt"
    timing = Timing(tempo=1, slots=[2.0, 2.0], starts=[0.0, 1.6], total=3.6, crossfade=0.4)
    srt(["สวัสดี", "ดูสินค้า"], timing, 0.05, path)
    rep = QAReport()
    subtitle_checks(path, ["สวัสดี", "ดูสินค้า"], timing.starts, timing.slots, 0.05, rep, "shopee")
    assert rep.checks[0].ok
    path.write_text(path.read_text().replace("ดูสินค้า", "ดูอย่างอื่น"), encoding="utf-8")
    rep = QAReport()
    subtitle_checks(path, ["สวัสดี", "ดูสินค้า"], timing.starts, timing.slots, 0.05, rep, "shopee")
    assert not rep.checks[0].ok and rep.checks[0].blocking


def test_revision_preserves_old_package_and_sends_feedback(tmp_path, monkeypatch):
    run = Run.create(tmp_path, "revision")
    write_json(run.p("product.json"), Product(id="lamp", name="โคมไฟ",
                                               listing_url="https://example.test/lamp", facts={"สี": "ขาว"}))
    write_json(run.p("plan.json"), {"shots": [{"vo": "คำเดิม"}]})
    run.p("out", "final.mp4").write_bytes(b"old package")
    write_json(run.p("out", "qa_report.json"), {"publishable": True, "checks": [
        {"name": "rights.documented_assets", "ok": True}, {"name": "tts.license", "ok": True}]})
    run.set_state("READY_FOR_APPROVAL")
    cfg = Config(runs_dir=tmp_path)
    cfg.director.provider = "ollama"
    monkeypatch.setattr(cli, "_cfg", lambda a: cfg)

    def fake_execute(run, cfg, folder, plan_file):
        assert run.version() == 2
        assert read_json(run.p("review_feedback.json"))["instruction"] == "เปลี่ยน hook"
        assert "คำเดิม" in run.p("versions", "v001", "plan.json").read_text()
        assert "ห้ามคำนี้" in build_prompt(Product.model_validate(read_json(run.p("product.json"))), [], cfg)
        run.p("out", "final.mp4").write_bytes(b"new package")
        run.set_state("READY_FOR_APPROVAL")
        return 0

    monkeypatch.setattr(cli, "_execute", fake_execute)
    args = argparse.Namespace(run=str(run.path), instruction="เปลี่ยน hook",
                              avoid_phrase=["ห้ามคำนี้"], director=None, config=None)
    assert cli.cmd_revise(args) == 0
    assert run.p("versions", "v001", "out", "final.mp4").read_bytes() == b"old package"
    assert run.p("out", "final.mp4").read_bytes() == b"new package"


def test_reject_requires_reviewable_state(tmp_path):
    run = Run.create(tmp_path, "unready")
    args = argparse.Namespace(run=str(run.path), decision="reject", note="", reviewed=False)
    assert cli.cmd_decide(args) == 2
    assert not run.p("out", "decision.json").exists()


def test_regen_cannot_overwrite_reviewable_package(tmp_path):
    run = Run.create(tmp_path, "reviewable")
    run.p("out", "final.mp4").write_bytes(b"approved candidate")
    run.set_state("READY_FOR_APPROVAL")
    args = argparse.Namespace(run=str(run.path), frm="plan", plan=None)
    assert cli.cmd_regen(args) == 2
    assert run.p("out", "final.mp4").read_bytes() == b"approved candidate"


def test_review_ui_does_not_label_legacy_ready_run_as_reviewable(tmp_path):
    run = Run.create(tmp_path, "legacy")
    run.set_state("READY_FOR_APPROVAL")
    write_json(run.p("out", "qa_report.json"), {"publishable": True, "checks": []})
    assert review_state(run) == "EVIDENCE_NEEDED"
    write_json(run.p("out", "qa_report.json"), {"publishable": True, "checks": [
        {"name": "rights.documented_assets", "ok": True}, {"name": "tts.license", "ok": True}]})
    assert review_state(run) == "READY_FOR_APPROVAL"


def test_revision_allowed_for_other_qa_failure_only_with_rights(tmp_path):
    run = Run.create(tmp_path, "qa-failed")
    write_json(run.p("product.json"), {"name": "สินค้า"})
    write_json(run.p("plan.json"), {"shots": []})
    run.p("out", "final.mp4").write_bytes(b"video")
    run.set_state("QA_DONE")
    write_json(run.p("out", "qa_report.json"), {"publishable": False, "checks": [
        {"name": "rights.documented_assets", "ok": True},
        {"name": "tts.license", "ok": True},
        {"name": "shopee.pix_fmt", "ok": False}]})
    assert cli.revision_ready(run)
    write_json(run.p("out", "qa_report.json"), {"publishable": False, "checks": [
        {"name": "rights.documented_assets", "ok": True},
        {"name": "tts.license", "ok": False}]})
    assert not cli.revision_ready(run)
