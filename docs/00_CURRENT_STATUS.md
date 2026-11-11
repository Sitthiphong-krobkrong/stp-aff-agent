# Current Status & Provenance

**As of 2026-11-11.** This is a handoff record compiled from project discussions, not a live repository audit.

## Established decisions
- Two independent repositories: `stp-aff-studio` (existing Toolkit) and `stp-aff-agent` (new autonomous system).
- Existing Toolkit workflow: make neutral 9:16 video, publish separately to Shopee Video (main channel) and TikTok STP Picks (secondary), Shopee caption max 150 characters, attach matching Shopee cart manually; Unique Code used in TikTok comment.
- Autonomous system goal: scout → research → rights-clear → produce **actual MP4** → QA → approval; human only approves/rejects/regenerates prior to release.
- Environment: Apple Silicon Mac, 24 GB unified memory; VS Code/Zed; Codex and Claude Code; future VPS possible.
- Separate repo and runtime are more important than sharing the existing renderer in v0.1.

## Reported access and implementation status
- In prior conversation, GitHub repository search located `Sitthiphong-krobkrong/stp-aff-agent`, initially empty, with `main` branch. An attempted README creation via ChatGPT GitHub connector repeatedly returned **403 Resource not accessible by integration**. No successful push was verified in the conversation.
- A small starter ZIP was previously discussed/delivered in chat, but **its code, contents and execution have not been independently re-verified here**. Do not assume the zip was imported or that a POC is running.
- Current repository content, write permissions and deployment status must be rechecked live.
- No verified autonomous product discovery + licensed assets + genuine MP4 run has been established in this handoff.

## Critical unknowns
- Whether the new repository now contains code (may have changed since prior checks).
- Exact technology and rendering internals of `stp-aff-studio`.
- Permitted product feeds, affiliate rates, shop listing rights and approved publishing APIs.
- Which TTS voice/license can be used commercially for Shopee and TikTok.
- Actual chip generation, disk space, performance and operating constraints of Mac.

## Do not report as complete
- Automated posting to either platform.
- Accurate live commission access.
- Commercial reuse rights without evidence.
- Local AI benchmarking or production-grade video quality.
