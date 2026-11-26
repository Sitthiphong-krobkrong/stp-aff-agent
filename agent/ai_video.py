"""Local LTX image-to-video from a documented real-product reference."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config, ROOT
from .util import StepError, log

LTX_DIR = ROOT / "tools" / "ltx-2-mlx"
LTX_CLI = LTX_DIR / ".venv" / "bin" / "ltx-2-mlx"


def available() -> bool:
    """Check for the installed CLI, not just a source checkout."""
    return LTX_CLI.is_file()


def _ltx_frames(duration_sec: float, frame_rate: int = 24) -> int:
    """Pick the smallest valid LTX frame count (8k+1 grid) that covers the duration."""
    raw = int(duration_sec * frame_rate) + 1
    k = (raw - 1 + 7) // 8  # ceil to next 8k+1
    return 8 * k + 1


def generate_clip(
    image: Path,
    prompt: str,
    out: Path,
    duration: float,
    cfg: Config,
) -> Path:
    """Generate a short AI video clip from a product image.

    Returns the output path on success; raises StepError on failure.
    """
    if not available():
        raise StepError("LTX-2-mlx not installed at tools/ltx-2-mlx")

    v = cfg.video
    frames = _ltx_frames(duration, v.ai_frame_rate)
    out.parent.mkdir(parents=True, exist_ok=True)

    argv = [
        str(LTX_CLI), "generate",
        "--prompt", prompt,
        "--image", str(image.resolve()),
        "--distilled",
        "--model", v.ai_model,
        "--low-ram",
        "-H", str(v.ai_height),
        "-W", str(v.ai_width),
        "-f", str(frames),
        "--frame-rate", str(v.ai_frame_rate),
        "--quiet",
        "-o", str(out.resolve()),
    ]

    log.info("LTX: %dx%d %d frames (%.1fs) from %s", v.ai_width, v.ai_height, frames, duration, image.name)
    try:
        p = subprocess.run(
            argv, capture_output=True, text=True, timeout=v.ai_timeout,
            cwd=str(LTX_DIR),
        )
    except subprocess.TimeoutExpired as e:
        raise StepError(f"LTX generation timed out after {v.ai_timeout}s") from e

    if p.returncode != 0:
        msg = (p.stderr.strip() or p.stdout.strip())[-800:]
        raise StepError(f"LTX generation failed: {msg}")

    if not out.exists():
        raise StepError(f"LTX did not produce output at {out}")

    log.info("LTX clip ready: %s", out.name)
    return out


def product_prompt(product_name: str, style: str) -> str:
    """Animate the supplied product reference; avoid adding unsupported visual details."""
    motion = {
        "hook": "dramatic slow reveal, camera pulling back",
        "title": "slow smooth orbit, product rotating gently",
        "spec": "close-up detail, slow dolly in",
        "cta": "glamour shot, soft glow, slow zoom in",
    }
    m = motion.get(style, "slow orbit, studio lighting")
    return (f"Studio video of the exact product in the reference image ({product_name}). "
            f"{m}. Preserve its shape, color, parts and proportions. "
            "Keep the product stationary except for subtle camera motion. "
            "Do not invent accessories, demonstrations, labels, logos, watermarks or readable text. "
            "Plain clean background, no hands, no additional objects.")
