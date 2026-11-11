# Proposed Data Model

This is a **design**, not a confirmed deployed schema.

| Entity | Key fields |
|---|---|
| `products` | id, name, brand, model, variant, factual_specs, evidence_status |
| `shops` | id, platform, shop_external_id, display_name |
| `affiliate_offers` | id, product_id, shop_id, listing_url, unique_code, rate, rate_verified_at, status |
| `candidate_evidence` | id, product_id, source_url, observed_at, metric_type, metric_value, confidence |
| `media_assets` | id, source_url, sha256, local_path, license_id, kind, provenance |
| `rights_grants` | id, asset_id, license_name, allowed_platforms, commercial_use, evidence_uri, verified_by, verified_at, expires_at, status |
| `content_projects` | id, product_id, chosen_offer_id, score, status |
| `content_versions` | id, project_id, hook, script, edl_json, prompt_version, model_version |
| `render_jobs` | id, version_id, state, idempotency_key, retries, logs_uri |
| `video_artifacts` | id, render_job_id, path, sha256, duration, width, height, audio_present, subtitles_status |
| `approval_decisions` | id, project_id, version_id, decision, reviewer, decided_at, notes |
| `publications` | id, version_id, offer_id, platform, caption, published_at, external_id, status |
| `performance_snapshots` | id, publication_id, source, captured_at, views, likes, orders_if_confirmed |
| `commission_records` | id, offer_id, external_order_ref, amount, currency, state, source, captured_at |
| `agent_runs` | id, run_type, input_uri, output_uri, model, token_usage, state, error |

## Constraints
- Product != listing/affiliate offer; different shops/variants have different codes and rates.
- `unknown` != zero; no fake values for unavailable sales or commissions.
- SHA-256 and evidence URL link rendered assets to their sources and licenses.
- One neutral content version can correspond to two separate platform publications.
- Keep source timestamps and report import IDs; avoid double-counting orders/commissions.

## Example minimal output manifest
```json
{
  "project_id": "example-only",
  "product_name": "EXAMPLE PRODUCT — NOT A REAL RECOMMENDATION",
  "rights_status": "pending",
  "mp4_path": null,
  "shopee_caption": null,
  "tiktok_caption": null,
  "tiktok_affiliate_comment": null,
  "approval_state": "not_ready"
}
```
