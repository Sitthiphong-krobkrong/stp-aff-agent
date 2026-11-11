# stp-aff-agent — STP Picks autonomous affiliate agent

Separate from `stp-aff-studio` (read-only reference; never modified from here).

**v0.1 scope (what exists now):** product data → analyze/rank → images → real 9:16 MP4 (Thai text cards,
narration, SRT) → QA → package `post.txt` → stop at human approval. Posting + pinning the cart stays manual.

Handoff baseline: [docs/](docs/) (00–09). Current plan: [docs/10_PLAN_v0.1.md](docs/10_PLAN_v0.1.md).

## Setup (Mac)
```bash
brew install ffmpeg python@3.12            # needs Python >= 3.11 (macOS system python3 is too old)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -r requirements.txt
pytest -q
```
Optional: `ollama pull qwen3:8b` (director), or use `--director claude_cli` (your Claude Code login).

## 1) Discover + analyze
```bash
# rows copied from your Shopee Affiliate dashboard (see examples/offers_sample.csv for columns)
python -m agent discover --source csv --csv offers.csv --top 10
python -m agent discover --source csv --csv offers.csv --top 3 --to-inbox inbox/   # create product folders
# when Open API access is granted (env SHOPEE_AFF_APP_ID / SHOPEE_AFF_SECRET):
python -m agent discover --source shopee_openapi --keyword "โคมไฟ"
```
Score = commission 35% · sales 25% · images 20% · rating 10% · price 10%. Unknown values score 0 and are
listed as unknown (never guessed). Full breakdown saved to `runs/discover-*.json`.

## 2) Images → video
```bash
python -m agent make inbox/<product>                        # director=ollama, tts=edge (config/agent.toml)
python -m agent make inbox/<product> --director claude_cli
python -m agent make examples/demo-lamp --plan examples/demo-lamp/plan.json   # fixed script, no LLM
python -m agent regen runs/<id> --from plan                 # new script; also: --from voice|render
python -m agent decide runs/<id> approve|reject
```
Output in `runs/<id>/out/`: `final.mp4`, `final_tt.mp4` (TikTok end card if `โค้ด Shopee` set), `post.txt`,
`*.srt`, `check.jpg`, `qa_report.json`, `manifest.json`. Evidence: `product.json`, `assets/assets.json`
(source URL, SHA-256, rights), `events.jsonl`.

### Product folder (`inbox/<name>/`)
Same `product.txt` as studio, plus `ลิงก์:`, `ลิงก์ affiliate:`, `ค่าคอม:`, `ขายแล้ว:`, `สิทธิ์รูป: owned|listing`,
`รูป:` (URL list) and/or an `images/` folder.

## Guardrails (enforced in code)
- **Claim gate:** every number on screen / in VO / captions must exist in product evidence; banned words and
  `ห้ามพูด` blocked; battery-type figures need `*` (renderer adds `*ตามสเปกผู้ผลิต`).
- **Rights gate:** seller listing images are rejected unless `allow_listing_images = true` in config
  (operator accepts the risk; QA records it). `owned`/`licensed` images always allowed.
- **TTS:** `edge` (free) is default; QA attaches a non-blocking warning that its commercial terms are unverified.
  `silent` = renderer test → QA blocks approval. Switch to `azure` with `AZURE_SPEECH_KEY`.
- **Approval:** `decide approve` refuses unless QA is publishable. Nothing is posted automatically.

## Known limits
- edge-tts only works on the Mac (cloud sandboxes can't reach the endpoint).
- No scraping of Shopee pages. Discovery = CSV from your dashboard until Open API access is granted.
- Open API client and Ollama/Claude director are written but **not yet executed against the real services**.
