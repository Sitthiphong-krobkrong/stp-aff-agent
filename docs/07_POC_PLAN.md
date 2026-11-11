# POC v0.1 — One Real Autonomous Video

## Goal
One end-to-end experiment with no user-selected product: discover three candidates → select one based on sourced evidence and usable assets → render one **actual Thai 9:16 MP4** → create a reviewable package. Do not publish.

## Steps
1. Repository audit. Verify current code and create a feature branch; avoid Studio modifications.
2. `ProductScout`: discover >=3 candidates using permitted sources; record URLs, observed data, scope limitations. No invented 'best seller' status.
3. `Research`: validate product facts and listing identity; rank with deterministic score breakdown. Affiliate commissions stay unknown unless verified.
4. `Rights`: locate commercially licensed product media; verify rights for both platforms. If no rights, skip candidate and try another. If all fail, stop and report blockers.
5. `Director`: local Qwen/Ollama produces typed Thai script and timestamped EDL; validate factual claims against evidence.
6. `Producer`: create narration with authorized TTS, subtitles with Thai font license, and FFmpeg vertical video. Motion graphics from rights-cleared stills are acceptable; unlicensed uploads are not.
7. `QA`: ffprobe width/height, duration, streams, codec; human-inspect sample for legibility and sync. Check claims and rights.
8. `Package`: `final.mp4`, `shopee_caption.txt` <=150 chars, `tiktok_caption.txt`, optional validated affiliate comment, `product_evidence.json`, `asset_licenses.json`, `qa_report.json`.
9. Present to human as READY_FOR_APPROVAL; do not post.

## Acceptance criteria
- All three discovered candidates trace to actual sources.
- At least one candidate has permitted media covering both distribution channels, or accurately report that experiment was blocked.
- MP4 file exists, is playable, has 9:16 dimensions, Thai narration and readable Thai subtitles.
- Does not make unverified sales/reviews/commission/test claims.
- Each copied media asset has rights evidence.
- Distinct Shopee/TikTok texts and accurate product-specific code handling.
- `stp-aff-studio` remains untouched.

## MVP fallback
If truly autonomous product sourcing is blocked, an isolated **mocked** product fixture may test rendering, but label this as a renderer-only technical test, **not** success of the autonomous POC.

## Suggested tree
```text
stp-aff-agent/
  app/{api,orchestrator,scout,research,rights,creative,video,qa,publishing}/
  providers/{llm,vision,tts,media_sources}/
  schemas/
  tests/
  docs/
  compose.yaml
  AGENTS.md
  CLAUDE.md
```
Adapt folder names to real repository, not vice versa.
