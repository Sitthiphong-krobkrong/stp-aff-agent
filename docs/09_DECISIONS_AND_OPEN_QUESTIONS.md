# Decisions, Constraints, Open Questions

## Accepted product decisions
- **Separate repo**, not long-running branch inside Studio.
- Studio existing implementation is independent and unchanged.
- Human only approves/rejects/regenerates before release in steady-state operation.
- Shopee Video is main affiliate conversion channel; TikTok STP Picks is secondary traffic channel.
- One neutral master video, separate captions and upload paths.
- POC focuses on automated sourcing and a **real video**, not just scripts/prompts.
- Asset licensing is a candidate eligibility gate.

## Engineering recommendations (not yet proven)
- Native Ollama Qwen3 8B + Qwen3-VL 4B; FFmpeg and licensed TTS; API via Docker; Apple Metal on host.
- Modular monolith / deterministic jobs, optional later cloud fallback.
- Mac native worker now, VPS control plane later.
- Codex implementer, Claude Code architect/reviewer; independent branches/worktrees.

## Open questions / blockers
1. Does GitHub connector currently have write permission? Previously 403.
2. Does `stp-aff-agent` contain any deployed or working code now?
3. What permitted sources provide product discovery, affiliate eligibility and seller statistics?
4. Can specific brand/product imagery be commercially reused across Shopee/TikTok? Need explicit evidence.
5. Which TTS/musical assets have license covering cross-platform monetized video?
6. Which publishing APIs/permissions are actually available for the accounts?
7. What disk capacity, chip family, budget and scheduling frequency are desired?

## Source-of-truth priority
Actual live code and source terms > documented evidence and tests > project handoff > planning assumptions. Update this file as things become verified.
