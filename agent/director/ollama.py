"""Local Ollama (e.g. qwen3:8b on the Mac). Binds to 127.0.0.1 by default; never expose it publicly."""
from __future__ import annotations

import json
import urllib.request

from ..config import Config


def complete(prompt: str, cfg: Config) -> str:
    body = json.dumps({"model": cfg.director.model, "stream": False, "format": "json", "think": False,
                       "options": {"temperature": 0.6},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(cfg.director.ollama_url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=cfg.director.timeout) as r:
        return json.loads(r.read())["message"]["content"]
