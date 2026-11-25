"""TTS providers → one mono 48k WAV per line, leading/trailing silence trimmed.

edge   : unofficial Microsoft Edge read-aloud endpoint (edge-tts). Commercial-use terms unverified;
         QA blocks approval without a documented grant for the selected voice.
azure  : Azure AI Speech REST, needs AZURE_SPEECH_KEY and a documented grant for the selected voice.
silent : placeholder durations for renderer tests only. QA marks the package NOT publishable.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import Config
from ..util import StepError, run

LICENSE_NOTE = {
    "edge": "edge-tts (unofficial endpoint) — commercial voice rights unverified",
    "azure": "Azure AI Speech — verify selected voice and output terms",
    "silent": "no voice (renderer test only)",
}


def apply_pronounce(text: str, pron: dict[str, str]) -> str:
    for k in sorted(pron, key=len, reverse=True):  # longest first so "PD 3.1" wins over "PD"
        text = text.replace(k, pron[k])
    return text


def load_pronounce(path: Path) -> dict[str, str]:
    if not Path(path).exists():
        return {}
    return {k: v for k, v in json.loads(Path(path).read_text(encoding="utf-8")).items() if not k.startswith("_")}


def trim_silence(src: Path, dst: Path) -> None:
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af",
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse", "-ar", "48000", "-ac", "1", dst])


def synth_lines(lines: list[str], workdir: Path, cfg: Config) -> list[Path]:
    """Synthesize every line (already pronunciation-substituted). Returns trimmed WAV paths."""
    prov = cfg.tts.provider
    workdir.mkdir(parents=True, exist_ok=True)
    raws = [workdir / f"vo_raw_{i}.mp3" for i in range(len(lines))]
    if prov == "edge":
        from .edge import synth_all
        synth_all(lines, raws, cfg)
    elif prov == "azure":
        from .azure import synth
        for t, o in zip(lines, raws):
            synth(t, o, cfg)
    elif prov == "silent":
        from .silent import synth
        for t, o in zip(lines, raws):
            synth(t, o)
    else:
        raise StepError(f"unknown tts provider {prov}")
    outs = []
    for i, r in enumerate(raws):
        o = workdir / f"vo_{i}.wav"
        if prov == "silent":
            run(["ffmpeg", "-v", "error", "-y", "-i", r, "-ar", "48000", "-ac", "1", o])
        else:
            trim_silence(r, o)
        outs.append(o)
    return outs
