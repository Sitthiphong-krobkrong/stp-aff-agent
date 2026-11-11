# Product Requirements — v2.0

## Primary outcome
Autonomous affiliate content creation from product discovery through fully rendered video and publishing package. Human intervention only at release approval (apart from one-time setup, credentials, policies, exceptional blockers).

## Functional requirements
1. Discover >=3 candidate products from permitted sources with URLs, observation dates, and evidence of demand. Do **not** assert top-seller ranking without verifiable sales data.
2. Research and validate product identity, variant, price, seller and seller terms; preserve unknowns.
3. Check affiliate eligibility/commission from actual authorized records; unverified commission remains `unknown`.
4. Score candidates using documented deterministic criteria (quality, evidence, estimated demand, suitability for video, availability of licensed media).
5. Acquire media with documented commercial reuse rights covering **both** Shopee and TikTok; otherwise skip candidate.
6. Generate evidence-grounded Thai hook, script, CTA, edit decision list and captions.
7. Produce **playable MP4 9:16**, configurable 1080x1920, with meaningful product visuals, Thai narration and readable timed Thai subtitles; no platform watermark.
8. Validate MP4 with ffprobe and content QA; capture asset provenance and generated-media disclosure requirements.
9. Produce separate Shopee caption <=150 characters, TikTok caption, and TikTok affiliate comment with product-specific Unique Code only if provided and verified.
10. Queue package for human approve/reject/regenerate; do not post before approval.
11. Publish only via supported authorized means; otherwise hand off ready-to-upload assets with explicit manual final action.
12. Record job state, decisions, publication references, sourced performance and actual commissions where available.

## Nonfunctional requirements
- Independent repo `stp-aff-agent`, no mutations to `stp-aff-studio`.
- Portable Mac→VPS orchestration, bounded retry and idempotency, configurable storage and provider adapters.
- Local-first budget; avoid running multiple memory-heavy AI models and renderer simultaneously on 24 GB unified memory.
- Audit trail, rights evidence, structured logs, safe subprocess execution and secrets management.
- Fail closed on rights uncertainty and unsupported product claims.

## Human approval contract
Approval is for the completed package (video, product/shop identity, evidence, caption, affiliate routing, disclosure). `REJECT` and `REGENERATE` create traceable decisions. Technical inability to publish automatically does not count as a successful auto-post.

## Exclusions for first POC
- Live publication or account automation.
- Claims of confirmed sales/commission without platform data.
- Complex multi-agent framework/UI/dashboard before first working video.
- Unlicensed scraping and generative demonstrations of unsupported product behavior.
