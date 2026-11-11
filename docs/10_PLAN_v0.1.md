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
| D3 | Discovery: bookmarklet the operator clicks on their own dashboard (same endpoint the page uses) → JSON → `auto`. Bot-driven browser rejected: Shopee showed a crawler CAPTCHA (`scene=crawler_item`) on first visit (observed 2026-11-11). Open API when granted. | accepted |
| D4 | Seller listing images allowed (`allow_listing_images=true`); operator accepted the risk 2026-11-11. Recorded in every QA report. | accepted |
| D5 | Posting + cart pinning manual (no public posting API known). | accepted |
| D6 | Product facts for the script come from operator-entered `จุดขาย` (or name/price only). Reading listing descriptions automatically would need scraping → not done. | proposed |

## Observed dashboard data (2026-11-11, operator's logged-in session, read-only)
`GET /api/v3/offer/product/list?list_type=0&sort_type=1&page_offset=<items>&page_limit=20&client_type=1`
→ `data.list[]`: item_id, long_link (affiliate link), product_link, default/seller commission %, and
`batch_item_for_item_card_full` with name, images[] (CDN ids, ~9), price×100000, historical_sold, stock,
item_rating, shop_name, tier_variations. `data.total_count` = 500. Image CDN: down-th.img.susercontent.com/file/<id>.

## Steps
- [x] P0 repo scaffold, config, schemas, run state (`runs/<id>/state.json`, `events.jsonl`, resume/regen)
- [x] Discovery: csv / manual / Open API (untested) sources + deterministic scoring with breakdown
- [x] Assets: ingest, SHA-256, size/dup filter, rights gate
- [x] Director: ollama / claude_cli / file + schema validation + claim gate + bounded retry
- [x] TTS: edge / azure / silent, pronounce.json, silence trim
- [x] Renderer: blurred background + product box, text cards above Shopee card zone, per-shot zoom, -15 LUFS,
      SRT, TikTok end-card variant
- [x] QA (ffprobe, claims, rights, captions, tts license) + check.jpg + post.txt + manifest; approval gate
- [x] Bookmarklet + dashboard source + `auto` command (dedupe ledger `runs/made.json`)
- [ ] Run `auto` on Mac with a real dump (images download, claude_cli director) (operator)
- [ ] Vision filter for listing images with heavy text/watermarks (Qwen-VL) — needed if D4 = yes
- [ ] Market test: 10 clips, compare with own-footage clips (decides whether to automate discovery further)
- [ ] Open API adapter verified live; then Telegram approval + launchd daily run

## Exit gate v0.1
On the Mac: one real product folder → `make` → `final.mp4` with Thai voice, QA publishable, operator approves.
