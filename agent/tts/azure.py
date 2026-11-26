from __future__ import annotations

import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from ..config import Config, secret
from ..util import StepError


def synth(text: str, out: Path, cfg: Config) -> None:
    key = secret("AZURE_SPEECH_KEY")
    if not key:
        raise StepError("AZURE_SPEECH_KEY not set")
    ssml = (f"<speak version='1.0' xml:lang='th-TH'><voice name='{cfg.tts.voice}'>"
            f"<prosody rate='{cfg.tts.rate}'>{escape(text)}</prosody></voice></speak>")
    req = urllib.request.Request(
        f"https://{cfg.tts.azure_region}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode(),
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-48khz-96kbitrate-mono-mp3", "User-Agent": "stp-aff-agent"})
    with urllib.request.urlopen(req, timeout=60) as r:
        Path(out).write_bytes(r.read())
