from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import Config
from ..util import StepError


def synth_all(lines: list[str], outs: list[Path], cfg: Config) -> None:
    try:
        import edge_tts
    except ImportError as e:
        raise StepError("pip install edge-tts") from e

    async def go():
        sem = asyncio.Semaphore(3)

        async def one(t, o):
            async with sem:
                for attempt in range(3):
                    try:
                        await edge_tts.Communicate(t, cfg.tts.voice, rate=cfg.tts.rate).save(str(o))
                        return
                    except Exception:  # noqa: BLE001 - network flakiness; bounded retry
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1.5 * (attempt + 1))
        await asyncio.gather(*(one(t, o) for t, o in zip(lines, outs)))

    try:
        asyncio.run(go())
    except Exception as e:  # noqa: BLE001
        raise StepError(f"edge-tts failed (needs internet to speech.platform.bing.com; blocked in cloud): {e}") from e
