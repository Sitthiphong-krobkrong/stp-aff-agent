"""Run directory = unit of work. Durable state + append-only event log so a crashed run can resume.

runs/<run_id>/
  state.json        current state, step results, retries
  events.jsonl      append-only transitions/errors
  product.json      facts used (evidence)
  candidates.json   discovery + score breakdown (when discovered)
  assets/           ingested images (+ assets.json provenance/rights)
  plan.json         validated director output
  work/             intermediates (safe to delete)
  out/              final.mp4, final_tt.mp4, post.txt, *.srt, check.jpg, qa_report.json
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .schemas import now_iso
from .util import read_json, write_json

STATES = ["NEW", "DISCOVERED", "RESEARCHED", "ASSETS_READY", "PLANNED", "VOICED", "RENDERED",
          "QA_DONE", "READY_FOR_APPROVAL", "APPROVED", "REJECTED", "REGENERATE", "POSTED",
          "SKIPPED", "FAILED"]
TERMINAL = {"READY_FOR_APPROVAL", "APPROVED", "REJECTED", "POSTED", "SKIPPED", "FAILED"}


def slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^0-9A-Za-z฀-๿]+", "-", text).strip("-").lower()
    return s[:n] or "item"


class Run:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.state_file = self.path / "state.json"

    @classmethod
    def create(cls, runs_dir: Path, name: str) -> "Run":
        rid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + slug(name)
        r = cls(Path(runs_dir) / rid)
        (r.path / "assets").mkdir(parents=True, exist_ok=True)
        (r.path / "work").mkdir(exist_ok=True)
        (r.path / "out").mkdir(exist_ok=True)
        write_json(r.state_file, {"run_id": rid, "state": "NEW", "created_at": now_iso(), "steps": {},
                                  "retries": {}})
        write_json(r.p("version.json"), {"version": 1})
        r.event("created", name=name)
        return r

    @property
    def id(self) -> str:
        return self.path.name

    def state(self) -> dict:
        return read_json(self.state_file)

    def event(self, kind: str, **data) -> None:
        with open(self.path / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": now_iso(), "event": kind, **data}, ensure_ascii=False) + "\n")

    def set_state(self, new: str, **info) -> None:
        assert new in STATES, new
        st = self.state()
        old = st["state"]
        st["state"] = new
        st["updated_at"] = now_iso()
        st.update(info)
        write_json(self.state_file, st)
        self.event("transition", frm=old, to=new, **info)

    def step_done(self, step: str) -> bool:
        return self.state()["steps"].get(step, {}).get("ok", False)

    def mark_step(self, step: str, ok: bool, **info) -> None:
        st = self.state()
        st["steps"][step] = {"ok": ok, "at": now_iso(), **info}
        if not ok:
            st["retries"][step] = st["retries"].get(step, 0) + 1
        write_json(self.state_file, st)
        self.event("step", step=step, ok=ok, **info)

    def retries(self, step: str) -> int:
        return self.state()["retries"].get(step, 0)

    def version(self) -> int:
        p = self.p("version.json")
        return int(read_json(p)["version"]) if p.exists() else 1

    def snapshot_version(self) -> Path:
        """Preserve reviewable inputs and output before a requested revision."""
        old = self.version()
        dest = self.p("versions", f"v{old:03d}")
        if dest.exists():
            raise ValueError(f"version {old} was already snapshotted")
        dest.mkdir(parents=True)
        for name in ("state.json", "version.json", "product.json", "candidate.json", "rights.json", "plan.json"):
            src = self.p(name)
            if src.is_file():
                shutil.copy2(src, dest / name)
        if self.p("out").exists():
            shutil.copytree(self.p("out"), dest / "out")
        self.event("version_snapshot", version=old, path=str(dest))
        return dest

    def invalidate_from(self, step_order: list[str], step: str) -> None:
        """Regenerate: forget results of `step` and everything after it."""
        st = self.state()
        for s in step_order[step_order.index(step):]:
            st["steps"].pop(s, None)
        write_json(self.state_file, st)
        self.event("invalidate", from_step=step)

    def p(self, *parts: str) -> Path:
        return self.path.joinpath(*parts)
