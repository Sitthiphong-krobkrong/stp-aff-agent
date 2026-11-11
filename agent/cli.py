"""stp-aff-agent CLI.

  python -m agent discover --source csv --csv offers.csv [--top 5] [--to-inbox inbox/]
  python -m agent new inbox/<product>
  python -m agent make inbox/<product> [--plan plan.json] [--tts edge|azure|silent] [--director ollama|claude_cli|file]
  python -m agent resume runs/<run_id>
  python -m agent regen runs/<run_id> --from plan
  python -m agent decide runs/<run_id> approve|reject [--note ...]
  python -m agent status
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import config as config_mod
from .pipeline import STEPS, Pipeline
from .runs import Run
from .schemas import now_iso
from .scoring import rank
from .sources import get_source
from .util import StepError, read_json, write_json


def _cfg(a) -> config_mod.Config:
    cfg = config_mod.load(Path(a.config) if a.config else None)
    if getattr(a, "tts", None):
        cfg.tts.provider = a.tts
    if getattr(a, "director", None):
        cfg.director.provider = a.director
    if getattr(a, "plan", None):
        cfg.director.provider = "file"
    if getattr(a, "allow_listing_images", False):
        cfg.allow_listing_images = True
    return cfg


def cmd_discover(a) -> int:
    cfg = _cfg(a)
    kw = {"csv": {"path": a.csv}, "manual": {"inbox": a.inbox}, "shopee_openapi": {"keyword": a.keyword}}[a.source]
    cands = get_source(a.source, **kw).search(cfg)
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
        for c, s in [x for x in ranked if x[1]["eligible"]][: a.top]:
            d = Path(a.to_inbox) / (c.source_ref.split("#")[-1] + "-" + "".join(ch for ch in c.name if ch.isalnum())[:30])
            d.mkdir(parents=True, exist_ok=True)
            imgs = "\n".join(f"- {u}" for u in c.image_urls)
            (d / "product.txt").write_text(
                f"ชื่อสินค้า: {c.name}\nหมวดสินค้า: {c.category or ''}\nจุดขาย:\n- \nราคา/โปร: "
                f"{c.price if c.price is not None else ''}\nห้ามพูด:\nลิงก์: {c.listing_url}\n"
                f"ลิงก์ affiliate: {c.affiliate_link or ''}\nค่าคอม: "
                f"{c.commission_rate * 100 if c.commission_rate is not None else ''}\nขายแล้ว: "
                f"{c.sales_count if c.sales_count is not None else ''}\nสิทธิ์รูป: listing\nรูป:\n{imgs}\n",
                encoding="utf-8")
            print(f"  → {d}")
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
    run.invalidate_from(STEPS, a.frm)
    run.set_state("REGENERATE", from_step=a.frm)
    return _execute(run, _cfg(a), None, Path(a.plan) if a.plan else None)


def cmd_decide(a) -> int:
    run = Run(Path(a.run))
    st = run.state()["state"]
    if a.decision == "approve" and st != "READY_FOR_APPROVAL":
        print(f"cannot approve: state is {st} (QA not publishable)", file=sys.stderr)
        return 2
    write_json(run.p("out", "decision.json"), {"decision": a.decision, "note": a.note, "at": now_iso()})
    run.set_state({"approve": "APPROVED", "reject": "REJECTED"}[a.decision], note=a.note)
    print(f"{run.id}: {a.decision}")
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
    d.add_argument("--source", default="csv", choices=["csv", "manual", "shopee_openapi"])
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
        p.add_argument("--allow-listing-images", action="store_true")
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
    g.add_argument("--allow-listing-images", action="store_true")
    g.set_defaults(fn=cmd_regen)

    c = sub.add_parser("decide")
    c.add_argument("run")
    c.add_argument("decision", choices=["approve", "reject"])
    c.add_argument("--note", default="")
    c.set_defaults(fn=cmd_decide)

    s = sub.add_parser("status")
    s.set_defaults(fn=cmd_status)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    return a.fn(a)
