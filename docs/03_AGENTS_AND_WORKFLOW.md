# Logical Agents & State Machine

Logical roles; **not nine separate LLMs**:

| Role | Responsibilities | Required evidence/output |
|---|---|---|
| Scout | candidate discovery | URLs, timestamps, source limitations |
| Research | product/offer facts | verified fields vs unknowns |
| Opportunity | deterministic ranking | score breakdown and reasons |
| Asset | source rights-cleared media | license grants and provenance |
| Creative | hook/script/scene plan | structured JSON with claim citations |
| Video Producer | TTS, subtitles, edit/render | MP4 + ffprobe metadata |
| QA | rights, product accuracy, video correctness | blocking/pass report |
| Publishing | approved packages, authorized integrations | platform-specific status |
| Analytics | views/orders/commissions | actual sourced metrics, attribution caveats |

```mermaid
stateDiagram-v2
  [*] --> DISCOVERING
  DISCOVERING --> RESEARCHING
  RESEARCHING --> VERIFYING_ASSETS
  VERIFYING_ASSETS --> PLANNING
  PLANNING --> RENDERING
  RENDERING --> QA
  QA --> READY_FOR_APPROVAL: pass
  QA --> PLANNING: retry within budget
  READY_FOR_APPROVAL --> APPROVED
  READY_FOR_APPROVAL --> REJECTED
  READY_FOR_APPROVAL --> PLANNING: regenerate
  APPROVED --> PUBLISHING: authorized
  APPROVED --> MANUAL_HANDOFF: API unavailable
  PUBLISHING --> PUBLISHED
  PUBLISHED --> MONITORING
  VERIFYING_ASSETS --> SKIPPED: no licensed media
  RENDERING --> FAILED: retries exhausted
```

Persist `run_id`, timestamps, state transitions, retry counts, errors, model versions, inputs/outputs, provenance, and human decisions. A candidate skipped for rights failure is not a completed job.
