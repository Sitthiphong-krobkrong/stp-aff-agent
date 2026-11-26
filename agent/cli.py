"""stp-aff-agent CLI.

  python -m agent bookmarklet                  # print the "ส่งให้ bot" bookmark
  python -m agent auto --count 3 --director claude_cli   # Downloads/stp-offers-*.json → videos
  python -m agent discover [--file dump.json] [--top 10] [--to-inbox inbox/]
  python -m agent new inbox/<product>
  python -m agent make inbox/<product> [--plan plan.json] [--tts edge|azure|silent] [--director ollama|claude_cli|file]
  python -m agent resume runs/<run_id>
  python -m agent regen runs/<run_id> --from plan
  python -m agent revise runs/<run_id> --instruction "..." [--avoid-phrase "..."]
  python -m agent decide runs/<run_id> approve --reviewed [--note ...]
  python -m agent status
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from . import config as config_mod
from .pipeline import STEPS, Pipeline
from .runs import Run
from .rights import MediaGrant, RightsRegistry
from .schemas import now_iso
from .scoring import rank
from .sources import get_source
from .util import StepError, read_json, sha256, write_json


def _cfg(a) -> config_mod.Config:
    cfg = config_mod.load(Path(a.config) if a.config else None)
    if getattr(a, "tts", None):
        cfg.tts.provider = a.tts
    if getattr(a, "director", None):
        cfg.director.provider = a.director
    if getattr(a, "plan", None):
        cfg.director.provider = "file"
    return cfg


def _make_source(a):
    kw = {"csv": {"path": a.csv}, "manual": {"inbox": a.inbox}, "shopee_openapi": {"keyword": a.keyword},
          "dashboard": {"path": a.file}}[a.source]
    return get_source(a.source, **kw)


def write_inbox(c, extra: dict, inbox: Path, media_grants: list[MediaGrant] | None = None,
                score: dict | None = None) -> Path:
    """Product folder from a discovered candidate. Facts = only what the source returned (name, variants, price)."""
    import re as _re
    ref = _re.sub(r"[^0-9A-Za-z฀-๿-]+", "-", c.source_ref.split("#")[-1])[:35].strip("-")
    d = inbox / f"{ref}-{_re.sub(r'[^0-9A-Za-z฀-๿]+', '-', c.name)[:30].strip('-')}"
    d.mkdir(parents=True, exist_ok=True)
    points = list(extra.get("facts", [])) or [c.name]
    points += list(extra.get("variants", []))
    image_lines = ([f"- {g.media_path}" for g in media_grants] if media_grants else
                   [f"- {u}" for u in c.image_urls[:8]])
    lines = [f"ชื่อสินค้า: {c.name}", f"แบรนด์: {extra.get('brand') or ''}", f"หมวดสินค้า: {c.category or ''}",
             "จุดขาย:", *[f"- {p}" for p in points],
             f"ราคา/โปร: {c.price:g}" if c.price is not None else "ราคา/โปร: ", "ห้ามพูด: ",
             f"ลิงก์: {c.listing_url}", f"ลิงก์ affiliate: {c.affiliate_link or ''}",
             f"ค่าคอม: {c.commission_rate * 100:g}" if c.commission_rate is not None else "ค่าคอม: ",
             f"ขายแล้ว: {c.sales_count if c.sales_count is not None else ''}",
             "สิทธิ์รูป: documented" if media_grants else "สิทธิ์รูป: listing", "รูป:",
             *image_lines]
    (d / "product.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if media_grants:
        write_json(d / "rights.json", {"grants": [g.model_dump(mode="json") for g in media_grants]})
    write_json(d / "candidate.json", {"candidate": c.model_dump(mode="json"), "extra": extra,
                                      "score": score})
    return d


def cmd_discover(a) -> int:
    cfg = _cfg(a)
    src = _make_source(a)
    cands = src.search(cfg)
    ranked = rank(cands, cfg.score)
    out = cfg.runs_dir / f"discover-{now_iso().replace(':', '')}.json"
    write_json(out, [{"candidate": c.model_dump(mode="json"), "score": s} for c, s in ranked])
    print(f"{len(cands)} candidates from {a.source} → {out}\n")
    print(f"{'#':>2} {'score':>6} {'comm':>6} {'sold':>7} {'price':>7} {'img':>3}  ok  name")
    for i, (c, s) in enumerate(ranked[: a.top], 1):
        comm = f"{c.commission_rate * 100:.1f}%" if c.commission_rate is not None else "?"
        print(f"{i:>2} {s['total']:>6.3f} {comm:>6} {c.sales_count if c.sales_count is not None else '?':>7} "
              f"{c.price if c.price is not None else '?':>7} {len(c.image_urls):>3}  {'✓' if s['eligible'] else '✗'}  "
              f"{c.name[:48]}" + (f"   ({'; '.join(s['reasons'])})" if s["reasons"] else ""))
    if a.to_inbox:
        for c, _ in [x for x in ranked if x[1]["eligible"]][: a.top]:
            print(f"  → {write_inbox(c, getattr(src, 'extra', {}).get(c.source_ref, {}), Path(a.to_inbox))}")
    return 0


def _report(run: Run) -> None:
    st = run.state()
    print(f"\nrun {run.id}: {st['state']}")
    out = run.p("out")
    for f in ("final.mp4", "final_tt.mp4", "post.txt", "check.jpg", "qa_report.json"):
        if (out / f).exists():
            print(f"  {out / f}")
    if (out / "final.mp4").exists():
        print(f"\n  open {out / 'final.mp4'}")
    if (out / "qa_report.json").exists():
        rep = read_json(out / "qa_report.json")
        for c in rep["checks"]:
            if not c["ok"]:
                print(f"  {'BLOCK' if c['blocking'] else 'warn '} {c['name']}: {c['detail']}")


def _execute(run: Run, cfg, folder: Path | None, plan_file: Path | None) -> int:
    try:
        Pipeline(run, cfg, plan_file).execute(folder)
    except StepError as e:
        print(f"!! {e}", file=sys.stderr)
        _report(run)
        return 2
    _report(run)
    return 0


TEMPLATE = """ชื่อสินค้า: 
หมวดสินค้า: 
จุดขาย:
- 
- 
- 
ราคา/โปร: 
ห้ามพูด: 
ลิงก์: 
ลิงก์ affiliate: 
โค้ด Shopee: 
สิทธิ์รูป: listing
แฮชแท็ก: 
"""


def cmd_new(a) -> int:
    d = Path(a.folder)
    (d / "images").mkdir(parents=True, exist_ok=True)
    pt = d / "product.txt"
    if pt.exists():
        print(f"{pt} already exists — not overwritten")
    else:
        pt.write_text(TEMPLATE, encoding="utf-8")
        print(f"created {pt}")
    print(f"next: fill in {pt}, put 4-5 product images in {d / 'images'}/, then\n"
          f"  python -m agent make {d} --director claude_cli")
    return 0


def check_folder(folder: Path) -> str | None:
    if not (folder / "product.txt").exists():
        return f"no product.txt in {folder} — run: python -m agent new {folder}"
    from .sources.manual import parse_product_txt
    info = parse_product_txt((folder / "product.txt").read_text(encoding="utf-8"))
    if not info.get("name"):
        return f"'ชื่อสินค้า:' is empty in {folder / 'product.txt'}"
    if not [x for x in info["points"] if x]:
        return f"'จุดขาย:' has no items in {folder / 'product.txt'} — the script may only use facts listed there"
    imgs = [p for p in (folder / "images").glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")] \
        if (folder / "images").exists() else []
    if len(imgs) + len(info["images"]) < 3:
        return f"need at least 3 images in {folder / 'images'}/ (found {len(imgs)})"
    return None


def cmd_make(a) -> int:
    cfg = _cfg(a)
    folder = Path(a.folder)
    problem = check_folder(folder)
    if problem:
        print(f"!! {problem}", file=sys.stderr)
        return 2
    run = Run.create(cfg.runs_dir, folder.name)
    return _execute(run, cfg, folder, Path(a.plan) if a.plan else None)


def cmd_resume(a) -> int:
    run = Run(Path(a.run))
    return _execute(run, _cfg(a), Path(read_json(run.p("source_info.json"))["folder"]), None)


def cmd_regen(a) -> int:
    run = Run(Path(a.run))
    if run.state()["state"] in ("READY_FOR_APPROVAL", "APPROVED", "REJECTED"):
        print("cannot regen a reviewable package: use revise to preserve the previous version", file=sys.stderr)
        return 2
    if run.p("review_feedback.json").exists() and a.frm == "plan":
        run.p("review_feedback.json").unlink()
    run.invalidate_from(STEPS, a.frm)
    run.set_state("REGENERATE", from_step=a.frm)
    return _execute(run, _cfg(a), None, Path(a.plan) if a.plan else None)


def revision_ready(run: Run) -> bool:
    """A render revision needs a clip and current media/voice rights, even when other QA failed."""
    if run.state()["state"] not in ("READY_FOR_APPROVAL", "QA_DONE"):
        return False
    if not all(run.p(name).is_file() for name in ("product.json", "plan.json")):
        return False
    if not run.p("out", "final.mp4").is_file():
        return False
    qa_path = run.p("out", "qa_report.json")
    if not qa_path.is_file():
        return False
    checks = {c.get("name"): c for c in read_json(qa_path).get("checks", [])}
    return all(checks.get(name, {}).get("ok") for name in ("rights.documented_assets", "tts.license"))


def cmd_revise(a) -> int:
    """Human revision request: preserve the old package and give feedback to the director."""
    run = Run(Path(a.run))
    if not revision_ready(run):
        print("cannot revise: need a rendered clip and passing image/voice rights checks", file=sys.stderr)
        return 2
    if not a.instruction.strip():
        print("cannot revise: instruction is empty", file=sys.stderr)
        return 2
    cfg = _cfg(a)
    if cfg.director.provider == "file":
        print("cannot revise: select ollama or claude_cli director", file=sys.stderr)
        return 2
    try:
        run.snapshot_version()
    except ValueError as e:
        print(f"cannot revise: {e}", file=sys.stderr)
        return 2
    new_version = run.version() + 1
    write_json(run.p("version.json"), {"version": new_version})
    write_json(run.p("review_feedback.json"), {"version": new_version,
                                               "instruction": a.instruction.strip(),
                                               "avoid_phrases": a.avoid_phrase, "at": now_iso()})
    if a.avoid_phrase:
        product = read_json(run.p("product.json"))
        product["avoid_claims"] = sorted(set(product.get("avoid_claims", []) + a.avoid_phrase))
        write_json(run.p("product.json"), product)
    shutil.rmtree(run.p("out"), ignore_errors=True)
    run.p("out").mkdir(parents=True)
    run.invalidate_from(STEPS, "plan")
    run.set_state("REGENERATE", from_step="plan", version=new_version)
    run.event("revision_requested", version=new_version, instruction=a.instruction.strip())
    return _execute(run, cfg, None, None)


def cmd_decide(a) -> int:
    run = Run(Path(a.run))
    st = run.state()["state"]
    artifacts = {}
    if run.p("out", "decision.json").exists():
        print("cannot decide: decision already recorded for this version", file=sys.stderr)
        return 2
    if a.decision == "approve":
        if st != "READY_FOR_APPROVAL" or not a.reviewed:
            print(f"cannot approve: state={st}; human review acknowledgement required", file=sys.stderr)
            return 2
        qa_path = run.p("out", "qa_report.json")
        if not qa_path.is_file():
            print("cannot approve: QA report missing", file=sys.stderr)
            return 2
        rep = read_json(qa_path)
        checks = {c["name"]: c for c in rep.get("checks", [])}
        required = ("rights.documented_assets", "tts.license")
        if not rep.get("publishable") or any(not checks.get(k, {}).get("ok") or
                                                   not checks.get(k, {}).get("blocking") for k in required):
            print("cannot approve: documented media and voice rights are not QA-passing", file=sys.stderr)
            return 2
        for name in ("final.mp4", "final.srt", "post.txt", "qa_report.json", "manifest.json"):
            path = run.p("out", name)
            if not path.is_file():
                print(f"cannot approve: {name} missing", file=sys.stderr)
                return 2
            artifacts[name] = sha256(path)
    elif st != "READY_FOR_APPROVAL":
        print(f"cannot reject: state={st}", file=sys.stderr)
        return 2
    write_json(run.p("out", "decision.json"), {"decision": a.decision, "note": a.note, "at": now_iso(),
                                               "version": run.version(), "reviewed": bool(a.reviewed),
                                               "artifact_sha256": artifacts})
    run.set_state({"approve": "APPROVED", "reject": "REJECTED"}[a.decision], note=a.note)
    print(f"{run.id}: {a.decision}")
    return 0


def cmd_auto(a) -> int:
    """Sourced candidates -> documented media -> bounded attempts -> human review package."""
    cfg = _cfg(a)
    report_path = cfg.runs_dir / f"auto-{now_iso().replace(':', '')}.json"
    report = {"status": "RUNNING", "source": a.source, "target_packages": a.count,
              "candidates": [], "attempts": [], "created_at": now_iso()}
    def finish(reason: str | None = None) -> int:
        ready = sum(x["state"] == "READY_FOR_APPROVAL" for x in report["attempts"])
        report.update(status="COMPLETED" if ready >= a.count else "BLOCKED",
                      ready_packages=ready, reason=reason)
        write_json(report_path, report)
        print(f"auto: {report['status']} ({ready}/{a.count} ready) → {report_path}")
        if reason:
            print(f"  {reason}", file=sys.stderr)
        return 0 if report["status"] == "COMPLETED" else 2

    if a.count < 1 or a.max_candidates < 1:
        return finish("count and max-candidates must be positive")
    voice_doc = cfg.tts.rights_evidence
    if cfg.tts.provider == "silent" or not voice_doc or not Path(voice_doc).is_file() or Path(voice_doc).stat().st_size == 0:
        return finish(f"TTS rights evidence missing for {cfg.tts.provider}; configure [tts].rights_evidence")
    if a.source == "csv":
        evidence = Path(a.source_evidence) if a.source_evidence else None
        if not evidence or not evidence.is_file() or evidence.stat().st_size == 0:
            return finish("CSV source needs --source-evidence with a nonempty authorization/provenance document")
        copied_evidence = report_path.with_name(report_path.stem + "-source-evidence" + evidence.suffix)
        copied_evidence.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(evidence, copied_evidence)
        report["source_evidence"] = {"path": str(copied_evidence), "sha256": sha256(copied_evidence),
                                     "original_path": str(evidence.resolve())}
        source_csv = Path(a.csv) if a.csv else None
        if not source_csv or not source_csv.is_file():
            return finish("CSV source file missing")
        copied_csv = report_path.with_name(report_path.stem + "-source.csv")
        shutil.copy2(source_csv, copied_csv)
        report["source_file"] = {"path": str(copied_csv), "sha256": sha256(copied_csv),
                                 "original_path": str(source_csv.resolve())}
    try:
        src = _make_source(a)
        candidates = src.search(cfg)
    except Exception as e:
        return finish(f"source unavailable: {e}")
    unique = {c.source_ref: c for c in candidates}
    sourced = [c for c in unique.values() if not any("observation time unknown" in x for x in c.limitations)]
    report["source_count"] = len(unique)
    report["sourced_count"] = len(sourced)
    if len(sourced) < 3:
        return finish(f"only {len(sourced)} candidates have source observation time; need at least 3")
    try:
        registry = RightsRegistry(Path(a.rights_registry) if a.rights_registry else cfg.rights_registry)
    except StepError as e:
        return finish(str(e))
    scored = []
    for c in sourced:
        grants, reasons = registry.for_candidate(c, minimum=cfg.score.min_images)
        scored_candidate = c.model_copy(update={"image_urls": [str(g.media_path) for g in grants]})
        sc = rank([scored_candidate], cfg.score)[0][1]
        report["candidates"].append({"candidate": c.model_dump(mode="json"), "score": sc,
                                     "rights_reasons": reasons, "documented_media": len(grants)})
        scored.append((c, sc, grants, reasons))
    scored.sort(key=lambda x: (not x[1]["eligible"], -x[1]["total"], x[0].name))
    ledger_p = cfg.runs_dir / "made.json"
    ledger = read_json(ledger_p) if ledger_p.exists() else {}
    ready = 0
    examined = 0
    for c, sc, grants, reasons in scored:
        if ready >= a.count or examined >= a.max_candidates:
            break
        examined += 1
        if c.source_ref in ledger:
            report["attempts"].append({"source_ref": c.source_ref, "state": "ALREADY_MADE"})
            continue
        if not grants or not sc["eligible"]:
            report["attempts"].append({"source_ref": c.source_ref, "state": "SKIPPED",
                                       "reason": "; ".join(reasons or sc["reasons"])})
            continue
        folder = write_inbox(c, getattr(src, "extra", {}).get(c.source_ref, {}), Path(a.inbox),
                             media_grants=grants, score=sc)
        print(f"\n=== {sc['total']:.3f} {c.name[:60]}")
        run = Run.create(cfg.runs_dir, folder.name)
        run.event("source_batch", report=str(report_path), source_ref=c.source_ref)
        _execute(run, cfg, folder, None)
        state = run.state()["state"]
        if state == "READY_FOR_APPROVAL":
            qa_path = run.p("out", "qa_report.json")
            mp4_path = run.p("out", "final.mp4")
            if not mp4_path.is_file() or not qa_path.is_file() or not read_json(qa_path).get("publishable"):
                run.set_state("FAILED", error="READY_FOR_APPROVAL without MP4 and passing QA report")
                state = "FAILED"
            else:
                ready += 1
                ledger[c.source_ref] = {"run": run.id, "state": state, "at": now_iso()}
                write_json(ledger_p, ledger)
        report["attempts"].append({"source_ref": c.source_ref, "state": state, "run": run.id})
    print("\n== summary ==")
    for item in report["attempts"]:
        print(f"{item['state']:<20} {item['source_ref']} {item.get('run', '')}")
    return finish(None if ready >= a.count else "not enough documented, QA-passing packages")


def cmd_bookmarklet(a) -> int:
    import re as _re
    from .config import ROOT
    js = (ROOT / "tools" / "bookmarklet.js").read_text(encoding="utf-8")
    js = "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))
    print("javascript:" + _re.sub(r"\s*\n\s*", " ", js).strip())
    return 0


def cmd_status(a) -> int:
    cfg = _cfg(a)
    for d in sorted(p for p in cfg.runs_dir.glob("*") if (p / "state.json").exists()):
        st = read_json(d / "state.json")
        print(f"{st['state']:<20} {d.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent")
    ap.add_argument("--config")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover")
    d.add_argument("--source", default="dashboard", choices=["dashboard", "csv", "manual", "shopee_openapi"])
    d.add_argument("--file", default=str(Path.home() / "Downloads" / "stp-offers-*.json"))
    d.add_argument("--csv")
    d.add_argument("--inbox", default="inbox")
    d.add_argument("--keyword")
    d.add_argument("--top", type=int, default=10)
    d.add_argument("--to-inbox")
    d.set_defaults(fn=cmd_discover)

    nw = sub.add_parser("new")
    nw.add_argument("folder")
    nw.set_defaults(fn=cmd_new)

    m = sub.add_parser("make")
    m.add_argument("folder")
    for p in (m,):
        p.add_argument("--plan")
        p.add_argument("--tts", choices=["edge", "azure", "silent"])
        p.add_argument("--director", choices=["ollama", "claude_cli", "file"])
    m.set_defaults(fn=cmd_make)

    r = sub.add_parser("resume")
    r.add_argument("run")
    r.add_argument("--tts", choices=["edge", "azure", "silent"])
    r.set_defaults(fn=cmd_resume)

    g = sub.add_parser("regen")
    g.add_argument("run")
    g.add_argument("--from", dest="frm", default="plan", choices=STEPS[1:])
    g.add_argument("--plan")
    g.add_argument("--tts", choices=["edge", "azure", "silent"])
    g.set_defaults(fn=cmd_regen)

    rv = sub.add_parser("revise")
    rv.add_argument("run")
    rv.add_argument("--instruction", required=True, help="reviewer's requested change")
    rv.add_argument("--avoid-phrase", action="append", default=[], help="phrase forbidden in future versions")
    rv.add_argument("--director", choices=["ollama", "claude_cli"])
    rv.set_defaults(fn=cmd_revise)

    c = sub.add_parser("decide")
    c.add_argument("run")
    c.add_argument("decision", choices=["approve", "reject"])
    c.add_argument("--note", default="")
    c.add_argument("--reviewed", action="store_true", help="acknowledge watching/listening and checking evidence")
    c.set_defaults(fn=cmd_decide)

    au = sub.add_parser("auto")
    au.add_argument("--source", default="shopee_openapi", choices=["csv", "shopee_openapi"])
    au.add_argument("--file", default=str(Path.home() / "Downloads" / "stp-offers-*.json"))
    au.add_argument("--csv")
    au.add_argument("--keyword")
    au.add_argument("--inbox", default="inbox")
    au.add_argument("--count", type=int, default=3)
    au.add_argument("--max-candidates", type=int, default=10)
    au.add_argument("--rights-registry")
    au.add_argument("--source-evidence", help="documented authorization/provenance for a CSV feed")
    au.add_argument("--tts", choices=["edge", "azure", "silent"])
    au.add_argument("--director", choices=["ollama", "claude_cli", "file"])
    au.set_defaults(fn=cmd_auto, plan=None)

    bm = sub.add_parser("bookmarklet")
    bm.set_defaults(fn=cmd_bookmarklet)

    s = sub.add_parser("status")
    s.set_defaults(fn=cmd_status)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    try:
        return a.fn(a)
    except FileNotFoundError as e:
        print(f"!! {e}", file=sys.stderr)
        return 2
