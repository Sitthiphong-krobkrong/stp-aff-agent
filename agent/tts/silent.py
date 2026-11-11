"""Renderer-test placeholder: silence with a duration estimated from Thai text length (~16 chars/s)."""
from __future__ import annotations

from pathlib import Path

from ..util import run


def estimate(text: str) -> float:
    return max(0.8, len(text.replace(" ", "")) / 16.0)


def synth(text: str, out: Path) -> None:
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", f"{estimate(text):.3f}", "-c:a", "libmp3lame", out])
