# Tech Stack & Deployment

## Recommended for Apple Silicon / 24 GB
- **Orchestrator/API**: Python + Pydantic + FastAPI (proposal; adapt if repo already uses another stack).
- **LLM**: native Ollama with `qwen3:8b` for script and planning, optional `qwen3-vl:4b` for keyframes. Use model-specific capabilities and test Thai quality/structured JSON.
- **Vision approach**: FFmpeg extracts timestamped keyframes → vision LLM assesses visible content → validated EDL. Do not claim full-frame understanding.
- **Audio**: existing TTS if its commercial usage is verified; optional licensed cloud TTS or licensed local TTS. MLX Whisper for transcription/alignment where useful.
- **Renderer**: FFmpeg on macOS native process; use actual owned/licensed visuals. `ffprobe` verification.
- **Data**: SQLite for local POC; PostgreSQL after VPS migration.
- **Queue**: durable local DB-backed jobs initially; Redis/RQ only when operations justify it.
- **Docker**: API/orchestrator and dependencies. Ollama and MLX on macOS host to access Metal. Container calls model via `host.docker.internal` with appropriately restricted binding and network controls.
- **Future VPS**: 2 vCPU/4 GB for light prototype; 4 vCPU/8 GB as growth baseline, not for GPU model hosting or heavy multi-render loads.

## Model storage (rough, quantization-dependent)
- Qwen3 8B ~5.2 GB; Qwen3-VL 4B ~3.3 GB; Whisper turbo ~1.6 GB, depending on variant.
- Reserve ~20–30 GB for AI runtime/models/cache, PLUS raw and rendered media. A rough 40+ GB total experiment budget excluding large footage is sensible; verify with `du` and actual downloads.
- Keep single AI inference / video render heavy job at a time initially; enforce concurrency=1.

## Security
- Do not expose unauthenticated Ollama on public network; avoid `0.0.0.0` where unnecessary.
- Limit remote storage with signed URLs and private object ACLs.
- Secrets in env/secret store, never in committed `.env`.
- Disable auto-publish by default.

## Model and API economics
Cloud APIs are optional fallbacks. Prices, names, support and exact rights terms are changeable; verify directly before procurement. Developer seats for Codex/Claude Code do not imply API inference credits for the production agent.
