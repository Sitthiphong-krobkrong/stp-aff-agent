"""Technical + content + rights QA. Produces qa_report.json and check.jpg (one frame per shot)."""
from __future__ import annotations

from pathlib import Path
import re

from PIL import Image

from . import claims, creative_quality
from .assets import usable
from .config import Config
from .schemas import Asset, Product, QAReport, VideoPlan
from .tts import LICENSE_NOTE
from .util import caption_len, probe, run, sha256


def video_checks(mp4: Path, cfg: Config, rep: QAReport, label: str) -> None:
    if not mp4.exists():
        rep.add(f"{label}.exists", False, str(mp4))
        return
    info = probe(mp4)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    rep.add(f"{label}.video_stream", v is not None and v["codec_name"] == "h264",
            f"codec={v and v['codec_name']}")
    if v:
        rep.add(f"{label}.size", (v["width"], v["height"]) == (cfg.video.width, cfg.video.height),
                f"{v['width']}x{v['height']}")
        num, den = (int(x) for x in v["r_frame_rate"].split("/"))
        rep.add(f"{label}.fps", abs(num / den - cfg.video.fps) < 0.01, v["r_frame_rate"])
        rep.add(f"{label}.pix_fmt", v.get("pix_fmt") == "yuv420p", v.get("pix_fmt", ""))
    rep.add(f"{label}.audio_stream", a is not None, a["codec_name"] if a else "missing")
    rep.add(f"{label}.duration", cfg.video.min_duration <= dur <= cfg.video.max_duration + 0.5, f"{dur:.2f}s")


def contact_sheet(mp4: Path, starts: list[float], slots: list[float], out: Path, work: Path) -> None:
    frames = []
    for i, (s, d) in enumerate(zip(starts, slots)):
        p = work / f"qa_{i}.jpg"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s + d * 0.6:.2f}", "-i", mp4, "-frames:v", "1",
             "-vf", "scale=270:480", p])
        frames.append(Image.open(p))
    cols = min(4, len(frames))
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 270 + (cols + 1) * 8, rows * 480 + (rows + 1) * 8), (30, 30, 30))
    for i, f in enumerate(frames):
        sheet.paste(f, (8 + (i % cols) * 278, 8 + (i // cols) * 488))
    sheet.save(out, quality=88)


def subtitle_checks(path: Path, lines: list[str], starts: list[float], slots: list[float],
                    lead: float, rep: QAReport, label: str) -> None:
    """Check the SRT contract against planned speech and rendered scene timing."""
    if not path.is_file():
        rep.add(f"{label}.subtitles", False, "SRT missing")
        return
    blocks = [b.splitlines() for b in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()) if b.strip()]
    if len(blocks) != len(lines) or len(starts) != len(lines) or len(slots) != len(lines):
        rep.add(f"{label}.subtitles", False, f"{len(blocks)} SRT blocks; expected {len(lines)}")
        return

    def seconds(value: str) -> float:
        h, m, rest = value.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    errors = []
    for i, (block, expected, start, slot) in enumerate(zip(blocks, lines, starts, slots), 1):
        try:
            number = int(block[0])
            left, right = block[1].split(" --> ")
            actual_text = " ".join(block[2:]).strip()
            if number != i or actual_text != expected.replace("|", " ").strip():
                errors.append(f"shot {i}: text/order mismatch")
            if abs(seconds(left) - (start + lead)) > 0.02 or abs(seconds(right) - (start + slot)) > 0.02:
                errors.append(f"shot {i}: timing mismatch")
        except (IndexError, ValueError):
            errors.append(f"shot {i}: malformed SRT")
    rep.add(f"{label}.subtitles", not errors,
            "; ".join(errors) or f"{len(blocks)} lines match planned speech and scene timing")


def run_qa(*, plan: VideoPlan, product: Product, assets: list[Asset], outputs: dict[str, Path],
           tts_provider: str, timing_warning: str, cfg: Config, tts_rights: dict | None = None,
           subtitle_expectations: dict[str, dict] | None = None) -> QAReport:
    rep = QAReport()
    for label, mp4 in outputs.items():
        video_checks(mp4, cfg, rep, label)
        if subtitle_expectations and label in subtitle_expectations:
            ex = subtitle_expectations[label]
            subtitle_checks(mp4.with_suffix(".srt"), ex["lines"], ex["starts"], ex["slots"],
                            cfg.video.lead, rep, label)

    errs = claims.check(plan, product, cfg.banned_words)
    rep.add("claims", not errs, "; ".join(errs) or "numeric and banned-word checks passed; general claims need human review")
    style_errors = creative_quality.check(plan, product)
    rep.add("creative_quality", not style_errors,
            "; ".join(style_errors) or "specific hook and generic sales-language checks passed; human still reviews the script")

    by_id = {a.id: a for a in assets}
    used = sorted({s.asset_id for s in plan.shots})
    bad = [f"{i}:{by_id[i].rights.value if i in by_id else 'missing'}"
           for i in used if i not in by_id or not usable(by_id[i])]
    rep.add("rights.assets", not bad, ", ".join(bad) or
            ", ".join(sorted({by_id[i].rights.value for i in used})))
    undocumented = []
    for i in used:
        a = by_id.get(i)
        if not a:
            undocumented.append(f"{i}: missing asset")
            continue
        evidence = Path(a.rights_evidence_path) if a.rights_evidence_path else None
        if (a.rights.value not in ("owned", "licensed") or
                set(a.allowed_platforms) != {"shopee", "tiktok"} or
                not a.rights_owner or not a.rights_license or not evidence or
                not evidence.is_file() or not a.rights_evidence_sha256 or
                sha256(evidence) != a.rights_evidence_sha256):
            undocumented.append(f"{i}: no valid documented grant for both platforms")
    rep.add("rights.documented_assets", not undocumented,
            "; ".join(undocumented) or "evidence files recorded and hashes match; human must review license scope")
    run_dir = next(iter(outputs.values())).parent.parent
    missing_originals = []
    for i in used:
        a = by_id.get(i)
        if not a or not a.reference_original_path or not a.source_media_sha256:
            missing_originals.append(f"{i}: original reference not recorded")
            continue
        original = run_dir / a.reference_original_path
        if not original.is_file() or sha256(original) != a.source_media_sha256:
            missing_originals.append(f"{i}: original reference hash mismatch")
    rep.add("visual.original_reference", not missing_originals,
            "; ".join(missing_originals) or "original references retained for comparison with cleaned render inputs")
    if any(by_id[i].rights.value == "listing_image_risk_accepted" for i in used if i in by_id):
        rep.add("rights.listing_images", False, "seller listing images lack documented rights",
                blocking=False)

    rep.add("tts.provider", tts_provider != "silent", LICENSE_NOTE.get(tts_provider, tts_provider))
    voice_evidence = tts_rights or {}
    voice_path = Path(voice_evidence["path"]) if voice_evidence.get("path") else None
    voice_documented = bool(voice_path and voice_path.is_file() and
                            voice_path.stat().st_size > 0 and
                            sha256(voice_path) == voice_evidence.get("sha256"))
    rep.add("tts.license", voice_documented,
            str(voice_path) if voice_documented else
            f"{LICENSE_NOTE.get(tts_provider, tts_provider)}; no rights evidence configured")
    if cfg.video.ai_video:
        model_doc = cfg.video.ai_rights_evidence
        rep.add("visual.model_rights", bool(model_doc and model_doc.is_file() and model_doc.stat().st_size > 0),
                str(model_doc) if model_doc else "no AI video model/output rights evidence configured")
    rep.add("font.license", True, "Kanit — SIL OFL 1.1", blocking=False)
    rep.add("timing", not timing_warning, timing_warning or "VO fits within max duration")

    n = caption_len(claims.shopee_post(plan))
    rep.add("caption.shopee_len", n <= 150, f"{n}/150")
    rep.add("caption.tiktok_affiliate_tag", "#affiliate" in plan.tiktok_caption.lower(),
            "TikTok caption should disclose #affiliate", blocking=False)
    rep.add("affiliate_link", bool(product.affiliate_link), product.affiliate_link or
            "no affiliate link — pin cart by product search in app", blocking=False)
    return rep.finalize()
