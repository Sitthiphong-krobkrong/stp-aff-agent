"""Technical + content + rights QA. Produces qa_report.json and check.jpg (one frame per shot)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import claims
from .assets import usable
from .config import Config
from .schemas import Asset, Product, QAReport, VideoPlan
from .tts import LICENSE_NOTE
from .util import caption_len, probe, run


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


def run_qa(*, plan: VideoPlan, product: Product, assets: list[Asset], outputs: dict[str, Path],
           tts_provider: str, timing_warning: str, cfg: Config) -> QAReport:
    rep = QAReport()
    for label, mp4 in outputs.items():
        video_checks(mp4, cfg, rep, label)

    errs = claims.check(plan, product, cfg.banned_words)
    rep.add("claims", not errs, "; ".join(errs) or "all numbers traced to evidence")

    by_id = {a.id: a for a in assets}
    used = sorted({s.asset_id for s in plan.shots})
    bad = [f"{i}:{by_id[i].rights.value}" for i in used if i not in by_id or not usable(by_id[i])]
    rep.add("rights.assets", not bad, ", ".join(bad) or
            ", ".join(sorted({by_id[i].rights.value for i in used})))
    if any(by_id[i].rights.value == "listing_image_risk_accepted" for i in used if i in by_id):
        rep.add("rights.listing_images", True, "uses seller listing images (risk accepted by operator)",
                blocking=False)

    rep.add("tts.provider", tts_provider != "silent", LICENSE_NOTE.get(tts_provider, tts_provider),
            blocking=tts_provider == "silent")
    if tts_provider == "edge":
        rep.add("tts.license", False, LICENSE_NOTE["edge"], blocking=False)
    rep.add("font.license", True, "Kanit — SIL OFL 1.1", blocking=False)
    rep.add("timing", not timing_warning, timing_warning or "VO fits within max duration", blocking=False)

    n = caption_len(claims.shopee_post(plan))
    rep.add("caption.shopee_len", n <= 150, f"{n}/150")
    rep.add("caption.tiktok_affiliate_tag", "#affiliate" in plan.tiktok_caption.lower(),
            "TikTok caption should disclose #affiliate", blocking=False)
    rep.add("affiliate_link", bool(product.affiliate_link), product.affiliate_link or
            "no affiliate link — pin cart by product search in app", blocking=False)
    return rep.finalize()
