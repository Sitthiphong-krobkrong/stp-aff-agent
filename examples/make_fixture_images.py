"""Generate synthetic product photos for renderer tests (FIXTURE ONLY — not a real product, owned by us)."""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def lamp(path: Path, bg, angle: float, size=(1000, 1000), glow=True):
    w, h = size
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    for y in range(h):  # soft vertical gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(c * (1 - 0.25 * t)) for c in bg))
    d.ellipse((w * .3, h * .82, w * .7, h * .9), fill=(40, 40, 45))           # base
    x0, y0 = w * .5, h * .84
    x1, y1 = x0 + math.cos(angle) * w * .25, y0 - math.sin(angle) * h * .45
    d.line([(x0, y0), (x1, y1)], fill=(60, 60, 70), width=int(w * .03))         # arm
    x2, y2 = x1 + w * .18, y1 - h * .05
    d.line([(x1, y1), (x2, y2)], fill=(60, 60, 70), width=int(w * .03))
    d.pieslice((x2 - w * .14, y2 - h * .05, x2 + w * .14, y2 + h * .18), 180, 360, fill=(245, 245, 240))
    if glow:
        g = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(g).polygon([(x2 - w * .12, y2 + h * .065), (x2 + w * .12, y2 + h * .065),
                                   (x2 + w * .3, h * .82), (x2 - w * .3, h * .82)], fill=(255, 240, 180, 90))
        im = Image.alpha_composite(im.convert("RGBA"), g.filter(ImageFilter.GaussianBlur(25))).convert("RGB")
    im.save(path, quality=92)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/demo-lamp/images")
    out.mkdir(parents=True, exist_ok=True)
    lamp(out / "1.jpg", (225, 215, 200), 1.1)
    lamp(out / "2.jpg", (60, 70, 95), 1.3, size=(1080, 1350))
    lamp(out / "3.jpg", (200, 225, 215), 0.9, glow=False)
    lamp(out / "4.jpg", (240, 200, 170), 1.2, size=(1200, 900))
    lamp(out / "5.jpg", (30, 30, 35), 1.0)
    print(f"fixture images → {out}")
