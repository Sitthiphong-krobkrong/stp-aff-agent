# Agent Instructions — STP Autonomous Affiliate Agent

## Mission
Create an autonomous, evidence-driven affiliate content factory producing real Thai-language vertical MP4 product videos and approval-ready publishing packages.

## Hard boundaries
- Work only in `stp-aff-agent`. `stp-aff-studio` is read-only for architectural reference; never change its files, branches, secrets, configuration or deployment.
- No automatic publication without explicit human approval; use only authorized platform APIs or manual handoff.
- Never scrape restricted Shopee/TikTok endpoints or bypass access controls.
- Never invent sales, commission rates, reviews, product features, or personal product-testing claims.
- Never assume Shopee listing images, customer videos, songs, fonts or TTS voices are commercially reusable.
- Require documented rights for all third-party assets on both Shopee and TikTok; otherwise reject candidate and try another.
- No secrets in code, prompts, logs or Git.
- Distinguish actual executions from proposals/mocks.

## Engineering workflow
1. Inspect repository and dependencies before changes.
2. Use a feature branch/PR; minimize scope and preserve independent deployment.
3. Build deterministic orchestration with bounded retries, observability and explicit states.
4. Use typed JSON schemas and validate all model outputs.
5. Verify output video with ffprobe, inspect subtitle/voice/scene synchronization and record media provenance.
6. Run tests and report exactly which tests passed/failed.
7. Keep AI and asset providers replaceable via adapters. Prefer local Mac workers; design control plane for future VPS.

## Definition of done for POC
Autonomously discover at least 3 sourced candidates, rank deterministically, find rights-cleared media for one product, produce an actual playable Thai-language 9:16 MP4 with narration and subtitles, generate separate publishing text, store evidence and QA report, and stop at approval. If sourcing fails, report blocked—not success.
