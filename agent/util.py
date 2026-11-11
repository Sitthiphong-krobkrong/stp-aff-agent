"""Small helpers: safe subprocess (argv list, never shell=True), hashing, ffprobe."""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("agent")


class StepError(RuntimeError):
    """A pipeline step failed in a way that should be recorded and possibly retried."""


def run(argv: list[str], timeout: float | None = None) -> str:
    """Run a command without a shell. Raises StepError with stderr tail on failure."""
    argv = [str(a) for a in argv]
    log.debug("run: %s", " ".join(argv)[:500])
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise StepError(f"timeout after {timeout}s: {argv[0]}") from e
    if p.returncode != 0:
        raise StepError(f"{argv[0]} exited {p.returncode}: {p.stderr.strip()[-800:]}")
    return p.stdout


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(out)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def caption_len(text: str) -> int:
    """Shopee caption length as the project counts it: emoji/pictographs count 2, joiners/variation selectors 0."""
    n = 0
    for ch in text:
        cp = ord(ch)
        if cp in (0x200D, 0xFE0F, 0xFE0E):
            continue
        n += 2 if (cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF) else 1
    return n


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic on same filesystem


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
