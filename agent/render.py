"""Still images → vertical MP4 with Thai text cards, narration and SRT.

Same proven pattern as stp-aff-studio: render each shot to its own segment, concat with -c copy, build the
audio in a separate pass (one giant filter_complex hangs/drops audio), loudnorm the VO to -15 LUFS.

Layout (1080x1920): text lives in the upper half (y 220-760) because Shopee's product card covers the
bottom ~22%. Product image sits in a box at y 790-1440 over a blurred, darkened copy of itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import Config
from .schemas import Shot
from .util import run

FG_X0, FG_X1, FG_Y1 = 40, 1040, 1500     # product image box; top edge follows the text block
FG_MIN_TOP, FG_MAX_TOP = 700, 900
HEAD_Y, SUB_GAP, SUBTITLE_Y = 300, 22, 640
THAI_MARKS = set(chr(c) for c in [0x0E31, *range(0x0E34, 0x0E3B), *range(0x0E47, 0x0E4F)])
COLORS = {  # head text fill, box fill
    "hook": ((20, 20, 20), (255, 205, 40, 240)),
    "title": ((255, 214, 60), (0, 0, 0, 185)),
    "spec": ((255, 214, 60), (0, 0, 0, 185)),
    "cta": ((255, 255, 255), (255, 120, 20, 245)),
}


# ------------------------------------------------------------------ timing
@dataclass
class Timing:
    tempo: float
    slots: list[float]
    starts: list[float]
    total: float
    warning: str = ""


def plan_timing(vo_durs: list[float], styles: list[str], cfg: Config) -> Timing:
    v = cfg.video
    n = len(vo_durs)
    holds = [v.cta_hold if s == "cta" else 0.0 for s in styles]
    speech = sum(vo_durs)
    budget = v.max_duration - n * (v.lead + v.gap) - sum(holds) - v.tail
    tempo = max(1.0, speech / budget) if budget > 0 else v.max_tempo
    warning = ""
    if tempo > v.max_tempo:
        warning = f"script too long: needs x{tempo:.2f} speed-up, capped at x{v.max_tempo}"
        tempo = v.max_tempo
    slots = [round(v.lead + d / tempo + v.gap + h, 3) for d, h in zip(vo_durs, holds)]
    slots[-1] = round(slots[-1] + v.tail, 3)
    starts = [round(sum(slots[:i]), 3) for i in range(n)]
    return Timing(tempo, slots, starts, round(sum(slots), 3), warning)


# ------------------------------------------------------------------ fonts / text
@lru_cache(maxsize=64)
def font(fonts_dir: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path(fonts_dir) / f"Kanit-{weight}.ttf"), size)


def _split_safe(text: str, n: int) -> tuple[str, str]:
    """Split at character n without separating Thai combining marks from their base."""
    while 0 < n < len(text) and text[n] in THAI_MARKS:
        n -= 1
    return text[:n], text[n:]


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("|"):
        words, cur = para.split(" "), ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=fnt) <= max_w:
                cur = trial
                continue
            if cur:
                lines.append(cur)
            cur = w
            while draw.textlength(cur, font=fnt) > max_w:  # single long Thai run: hard split
                k = len(cur)
                while k > 1 and draw.textlength(cur[:k], font=fnt) > max_w:
                    k -= 1
                a, cur = _split_safe(cur, k)
                lines.append(a)
        if cur:
            lines.append(cur)
    return lines


def fit_lines(draw, text, cfg: Config, weight: str, size: int, max_w: int, max_lines: int, min_size: int):
    while True:
        f = font(str(cfg.fonts_dir), weight, size)
        lines = wrap(draw, text, f, max_w)
        if len(lines) <= max_lines or size <= min_size:
            return f, lines[:max_lines] if size > min_size else lines
        size -= 6


def _box_lines(draw, lines, f, cy, fill, box, pad=34, r=30, line_h=None):
    line_h = line_h or int(f.size * 1.25)
    w = max(draw.textlength(l, font=f) for l in lines) + pad * 2
    h = line_h * len(lines) + pad
    x0, y0 = (1080 - w) / 2, cy
    draw.rounded_rectangle((x0, y0, x0 + w, y0 + h), r, fill=box)
    y = y0 + pad / 2 + line_h / 2
    for l in lines:
        draw.text((540, y), l, font=f, fill=fill, anchor="mm")
        y += line_h
    return y0 + h


def make_card(shot: Shot, out: Path, cfg: Config, subtitle: str | None = None) -> int:
    """Draw text card; returns y where the product image may start."""
    W, H = cfg.video.width, cfg.video.height
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fill, box = COLORS[shot.style]
    hf, hl = fit_lines(d, shot.head, cfg, "Bold", 112 if shot.style == "hook" else 100, W - 200, 2, 64)
    y = _box_lines(d, hl, hf, HEAD_Y - 80, fill, box)
    if shot.sub:
        sf, sl = fit_lines(d, shot.sub, cfg, "Medium", 54, W - 220, 2, 40)
        y = _box_lines(d, sl, sf, y + SUB_GAP, (255, 255, 255), (0, 0, 0, 160), pad=26, r=22)
    sub_text = subtitle if subtitle is not None else shot.vo
    if sub_text:
        tf, tl = fit_lines(d, sub_text, cfg, "SemiBold", 58, W - 140, 2, 42)
        ty = max(SUBTITLE_Y, y + 60)
        for l in tl:
            d.text((W // 2, ty), l, font=tf, fill=(255, 255, 255), anchor="mm", stroke_width=6,
                   stroke_fill=(0, 0, 0))
            ty += int(tf.size * 1.3)
        y = ty - int(tf.size * 0.6)
    if "*" in shot.head + (shot.sub or ""):
        d.text((W // 2, FG_Y1 + 32), "*ตามสเปกผู้ผลิต", font=font(str(cfg.fonts_dir), "Medium", 34),
               fill=(235, 235, 235), anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
    im.save(out)
    return int(min(max(y + 40, FG_MIN_TOP), FG_MAX_TOP))


# ------------------------------------------------------------------ frames
def compose_frame(src: Path, out: Path, cfg: Config, top: int = FG_MIN_TOP) -> tuple[float, float]:
    """Blurred cover background + product image fitted into FG_BOX. Returns zoom anchor (0..1, 0..1)."""
    W, H = cfg.video.width, cfg.video.height
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    bg = ImageOps.fit(img, (W, H)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
    x0, y0, x1, y1 = FG_X0, top, FG_X1, FG_Y1
    fg = ImageOps.contain(img, (x1 - x0, y1 - y0))
    mask = Image.new("L", fg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *fg.size), 28, fill=255)
    px, py = x0 + (x1 - x0 - fg.width) // 2, y0 + (y1 - y0 - fg.height) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((px + 8, py + 14, px + fg.width + 8, py + fg.height + 14), 28,
                                             fill=(0, 0, 0, 150))
    bg = Image.alpha_composite(bg.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(14))).convert("RGB")
    bg.paste(fg, (px, py), mask)
    bg.save(out, quality=95)
    return (px + fg.width / 2) / W, (py + fg.height / 2) / H


def render_segment(frame: Path, card: Path, slot: float, anchor: tuple[float, float], out: Path,
                   cfg: Config, zoom_in: bool = True) -> None:
    v = cfg.video
    W, H, fps = v.width, v.height, v.fps
    z = f"1.0+{v.zoom}*t/{slot:.3f}" if zoom_in else f"{1 + v.zoom}-{v.zoom}*t/{slot:.3f}"
    ax, ay = anchor
    vf = (f"[0:v]fps={fps},scale=w='{W}*({z})':h='{H}*({z})':eval=frame,"
          f"crop={W}:{H}:x='(iw-{W})*{ax:.3f}':y='(ih-{H})*{ay:.3f}',setsar=1[v0];"
          f"[v0][1:v]overlay=0:0,format=yuv420p[o]")
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(fps), "-t", f"{slot:.3f}", "-i", frame,
         "-loop", "1", "-i", card, "-filter_complex", vf, "-map", "[o]", "-t", f"{slot:.3f}", "-r", str(fps),
         "-c:v", "libx264", "-preset", v.preset, "-crf", str(v.crf), "-an", out], timeout=600)


def build_audio(vo: list[Path], timing: Timing, out: Path, cfg: Config, normalize: bool = True) -> None:
    lead = cfg.video.lead
    ins, fc = [], []
    for i, p in enumerate(vo):
        ins += ["-i", p]
        fc.append(f"[{i}:a]atempo={timing.tempo:.4f},adelay={int((timing.starts[i] + lead) * 1000)}:all=1[a{i}]")
    norm = f",loudnorm=I={cfg.video.vo_lufs}:TP=-1.5:LRA=11" if normalize else ""
    fc.append("".join(f"[a{i}]" for i in range(len(vo))) + f"amix=inputs={len(vo)}:normalize=0:duration=longest,"
              f"apad,atrim=0:{timing.total:.3f}{norm},aresample=48000,"
              f"aformat=sample_fmts=s16:channel_layouts=stereo[o]")
    run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[o]", out], timeout=300)


def concat_and_mux(segs: list[Path], audio: Path, out: Path, work: Path) -> None:
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in segs), encoding="utf-8")
    vid = work / "video_only.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vid])
    run(["ffmpeg", "-v", "error", "-y", "-i", vid, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out])


def srt(lines: list[str], timing: Timing, lead: float, out: Path) -> None:
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    rows = []
    for i, (t, st, sl) in enumerate(zip(lines, timing.starts, timing.slots)):
        rows.append(f"{i + 1}\n{ts(st + lead)} --> {ts(st + sl)}\n{t.replace('|', ' ')}\n")
    out.write_text("\n".join(rows), encoding="utf-8")
