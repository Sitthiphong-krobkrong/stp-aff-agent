# Plan v0.1 — supersedes 07_POC_PLAN where they differ (2026-11-11)

## Requirement (operator, 2026-11-11)
Bot finds products with good commission + popularity → uses product images to make the video → package for
posting with cart pinned. Human approves and posts.

## Verified facts (observed 2026-11-11)
- `stp-aff-agent` was empty (no commits) before this branch.
- `stp-aff-studio` v0.4.0: Python + FFmpeg + Pillow, edge-tts/Paxa TTS, Kanit (SIL OFL 1.1).
- Shopee Affiliate **Open API is not available** on the operator's account yet.
- Shopee Affiliate Open API exists per region (TH dashboard has an "Open API" section once granted); returns
  commission rate, sales, offer link. Field names in `sources/shopee_openapi.py` must be verified on access.

## Decisions
| # | Decision | Status |
|---|---|---|
| D1 | v0.1 = discover/analyze + images→video only. Telegram, scheduling, auto-run later. | accepted |
| D2 | TTS: free edge-tts first; Azure adapter ready. Voice commercial terms = open risk, shown in every QA report. | accepted |
| D3 | Discovery without scraping: CSV from operator's own affiliate dashboard now, Open API when granted. | proposed |
| D4 | Seller listing images: off by default (`allow_listing_images=false`). Operator must opt in and accept risk. | **open — operator to decide** |
| D5 | Posting + cart pinning manual (no public posting API known). | accepted |
| D6 | Product facts for the script come from operator-entered `จุดขาย` (or name/price only). Reading listing descriptions automatically would need scraping → not done. | proposed |

## Steps
- [x] P0 repo scaffold, config, schemas, run state (`runs/<id>/state.json`, `events.jsonl`, resume/regen)
- [x] Discovery: csv / manual / Open API (untested) sources + deterministic scoring with breakdown
- [x] Assets: ingest, SHA-256, size/dup filter, rights gate
- [x] Director: ollama / claude_cli / file + schema validation + claim gate + bounded retry
- [x] TTS: edge / azure / silent, pronounce.json, silence trim
- [x] Renderer: blurred background + product box, text cards above Shopee card zone, per-shot zoom, -15 LUFS,
      SRT, TikTok end-card variant
- [x] QA (ffprobe, claims, rights, captions, tts license) + check.jpg + post.txt + manifest; approval gate
- [ ] Run on Mac with edge-tts + Ollama/Claude director on a real product (operator)
- [ ] Vision filter for listing images with heavy text/watermarks (Qwen-VL) — needed if D4 = yes
- [ ] Market test: 10 clips, compare with own-footage clips (decides whether to automate discovery further)
- [ ] Open API adapter verified live; then Telegram approval + launchd daily run

## Exit gate v0.1
On the Mac: one real product folder → `make` → `final.mp4` with Thai voice, QA publishable, operator approves.
