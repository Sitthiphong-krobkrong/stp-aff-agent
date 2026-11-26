"""Claude Code CLI in print mode (same approach as stp-aff-studio auto.py). Uses the operator's own login."""
from __future__ import annotations

import shutil

from ..config import Config
from ..util import StepError, run


def complete(prompt: str, cfg: Config) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise StepError("claude CLI not found on PATH")
    return run([exe, "-p", prompt, "--output-format", "text"], timeout=cfg.director.timeout)
