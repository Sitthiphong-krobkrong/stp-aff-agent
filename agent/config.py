"""Configuration: config/agent.toml (committed defaults) + config/local.toml (gitignored) + env for secrets."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent


class VideoCfg(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    max_duration: float = 25.0
    min_duration: float = 15.0
    max_tempo: float = 1.12          # never speed VO up more than this
    lead: float = 0.05
    gap: float = 0.25
    tail: float = 0.3
    cta_hold: float = 0.4
    vo_lufs: float = -15.0
    zoom: float = 0.15
    crossfade: float = 0.4            # seconds of crossfade between shots
    text_fade: float = 0.3            # seconds for text card fade-in
    crf: int = 19
    preset: str = "veryfast"
    # AI video (LTX-2-mlx) — set ai_video = true in local.toml to enable
    ai_video: bool = False
    ai_width: int = 288               # 9:16 vertical, must be multiple of 32
    ai_height: int = 512              # must be multiple of 32
    ai_frame_rate: int = 24           # LTX native fps (FFmpeg re-times to video.fps)
    ai_model: str = "dgrauet/ltx-2.3-mlx-q4"
    ai_timeout: float = 600           # seconds per clip


class TTSCfg(BaseModel):
    provider: str = "edge"            # edge (free, unofficial) | azure | silent (tests only)
    voice: str = "th-TH-NiwatNeural"
    rate: str = "-5%"
    azure_region: str = "southeastasia"


class DirectorCfg(BaseModel):
    provider: str = "ollama"          # ollama | claude_cli | file
    model: str = "qwen3:8b"
    ollama_url: str = "http://127.0.0.1:11434"
    retries: int = 3
    timeout: float = 300


class SourceCfg(BaseModel):
    provider: str = "manual"          # manual | csv | shopee_openapi
    openapi_url: str = "https://open-api.affiliate.shopee.co.th/graphql"
    keyword: str = ""
    limit: int = 20


class ScoreCfg(BaseModel):
    w_commission: float = 0.35
    w_sales: float = 0.25
    w_rating: float = 0.10
    w_price: float = 0.10
    w_images: float = 0.20
    price_sweet_min: float = 99
    price_sweet_max: float = 1500
    min_images: int = 4


class Config(BaseModel):
    runs_dir: Path = ROOT / "runs"
    fonts_dir: Path = ROOT / "fonts"
    pronounce: Path = ROOT / "config" / "pronounce.json"
    # rights stance for seller listing images. False = fail closed (handoff default).
    allow_listing_images: bool = False
    banned_words: list[str] = Field(default_factory=lambda: [
        "ดีที่สุด", "ถูกที่สุด", "ไม่มีดีเลย์", "รีวิวของจริง", "ทดสอบจริง", "ใช้เองจริง", "ขายดีอันดับ 1"])
    video: VideoCfg = VideoCfg()
    tts: TTSCfg = TTSCfg()
    director: DirectorCfg = DirectorCfg()
    source: SourceCfg = SourceCfg()
    score: ScoreCfg = ScoreCfg()


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: Path | None = None) -> Config:
    data: dict = {}
    for p in (ROOT / "config" / "agent.toml", ROOT / "config" / "local.toml", path):
        if p and Path(p).exists():
            data = _merge(data, tomllib.loads(Path(p).read_text(encoding="utf-8")))
    return Config.model_validate(data)


def secret(name: str) -> str | None:
    """Secrets only from environment (load .env yourself / launchd EnvironmentVariables). Never from git."""
    return os.environ.get(name) or None
