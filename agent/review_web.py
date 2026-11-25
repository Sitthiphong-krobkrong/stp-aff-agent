"""Local, single-operator Review UI. Bind to loopback only; never publish media publicly."""
from __future__ import annotations

import argparse
import html
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import cli
from .config import load
from .runs import Run
from .util import read_json


CSS = """
:root{font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1b2927;background:#f5f4ef}
*{box-sizing:border-box}body{margin:0}.shell{max-width:1380px;margin:auto;padding:26px 32px 64px}
a{color:#08796b;text-decoration:none}a:hover{text-decoration:underline}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #d9ded7;padding-bottom:19px;margin-bottom:26px}
.brand{font-size:21px;font-weight:800;letter-spacing:-.04em}.brand span{color:#ed6d43}.eyebrow{font-size:11px;letter-spacing:.13em;text-transform:uppercase;font-weight:800;color:#72827a}
h1{font-size:clamp(30px,4vw,48px);letter-spacing:-.055em;margin:8px 0 12px}h2{font-size:18px;letter-spacing:-.025em;margin:0 0 16px}p{line-height:1.55;color:#53635c}
.summary{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0 30px}.metric{background:#fff;border:1px solid #e0e5dc;border-radius:16px;padding:16px 20px;min-width:142px}.metric strong{display:block;font-size:25px}.metric small{color:#718079}
.grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(330px,.85fr);gap:20px}.stack{display:grid;gap:20px}.card{background:#fff;border:1px solid #e0e5dc;border-radius:18px;padding:22px;box-shadow:0 3px 20px #193c2b08}
.run{display:flex;justify-content:space-between;gap:18px;align-items:center;padding:18px 0;border-top:1px solid #edf0e9}.run:first-of-type{border-top:0}.run strong{display:block;font-size:17px}.muted{font-size:13px;color:#7b8982}.badge{display:inline-block;border-radius:999px;padding:7px 11px;font-size:11px;font-weight:800;letter-spacing:.04em;background:#e4ece8;color:#285b50;white-space:nowrap}.badge.ready{background:#e1f4e9;color:#237448}.badge.blocked{background:#fff0e3;color:#a85418}.badge.approved{background:#dcecf8;color:#245f89}
.video{background:#17231f;border-radius:18px;overflow:hidden;text-align:center}.video video{display:block;max-height:70vh;max-width:100%;width:auto;margin:auto}.video .empty{padding:90px 20px;color:#e5ebe6}
.checks{list-style:none;padding:0;margin:0}.checks li{display:flex;gap:10px;padding:11px 0;border-top:1px solid #edf0e9;font-size:13px}.checks li:first-child{border-top:0}.ok{color:#188453}.fail{color:#c04d27}.checktext{min-width:0;overflow-wrap:anywhere}.checktext b{display:block}.checktext small{color:#75837c}
textarea,input,select{font:inherit;width:100%;border:1px solid #cbd5ce;border-radius:10px;padding:11px;background:#fff;color:#1b2927}textarea{min-height:110px;resize:vertical}label{font-size:13px;font-weight:700;display:block;margin:14px 0 7px}button{border:0;border-radius:10px;padding:12px 16px;font:inherit;font-weight:750;cursor:pointer;background:#08796b;color:white}button.secondary{background:#edf2ed;color:#2b4b42}button.danger{background:#fff0e9;color:#ad4323}button:disabled{opacity:.5;cursor:not-allowed}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.note{background:#fff6e8;border:1px solid #f3dbb9;border-radius:12px;padding:12px 15px;color:#86561e;font-size:13px}.files{display:flex;gap:9px;flex-wrap:wrap}.files a{padding:8px 10px;background:#edf4f0;border-radius:8px;font-size:13px}.mono{font:12px ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere}.pre{white-space:pre-wrap;background:#f7f8f5;padding:14px;border-radius:10px;font-size:13px;max-height:270px;overflow:auto}
.assetgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px}.asset{border:1px solid #e3e9e2;border-radius:12px;padding:10px;overflow-wrap:anywhere}.asset img{width:100%;aspect-ratio:1;object-fit:contain;background:#f2f3ef;border-radius:7px}.asset small{display:block;color:#718079;margin-top:5px}.confirm{display:flex;gap:9px;align-items:flex-start;margin-top:18px}.confirm input{width:auto;margin-top:3px}
.grid{grid-template-columns:minmax(0,1fr) minmax(310px,390px);align-items:start}.grid>*{min-width:0}.stack{display:flex;flex-direction:column;min-width:0}.card{min-width:0}.pre,.checktext small,.run strong{overflow-wrap:anywhere;word-break:break-word}.pre{max-height:330px}.checktext{min-width:0}.detail-title{font-size:clamp(27px,3vw,39px);line-height:1.2;max-width:900px}.run-id{font:12px ui-monospace,SFMono-Regular,monospace;color:#849089;overflow-wrap:anywhere}.compact-card{padding:18px}.compact-card h2{margin-bottom:10px}.qa-all{margin-top:12px;border-top:1px solid #edf0e9;padding-top:12px}.qa-all summary,.fold summary{cursor:pointer;color:#08796b;font-weight:700;font-size:13px}.fold summary{padding:3px 0}.fold[open] summary{margin-bottom:16px}.status-warning{background:#fff0e3;color:#a85418}.small-note{font-size:13px;margin:0}.run-name{display:block;font-weight:750;font-size:16px;line-height:1.35;max-width:780px}.run-meta{display:block;margin-top:5px;font-size:11px;color:#87958d;overflow-wrap:anywhere}
.queue-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin:20px 0 28px}.queue-head h1{margin:7px 0 0}.queue-count{color:#718079;font-size:13px}.empty-state{border:1px dashed #b9d0c3;background:#f8fbf7;border-radius:20px;padding:40px 32px;margin:0 0 20px}.empty-state .mark{width:42px;height:42px;border-radius:12px;background:#dceee3;color:#237448;display:grid;place-items:center;font-size:24px;font-weight:800;margin-bottom:20px}.empty-state h2{font-size:23px;margin-bottom:8px}.empty-state p{max-width:580px;margin:0}.section-heading{display:flex;justify-content:space-between;align-items:center;gap:15px}.section-heading h2{margin:0}.queue-secondary{margin-top:22px}.queue-secondary summary{font-size:16px!important;color:#243630!important}.queue-secondary[open] summary{margin-bottom:8px}.queue-list .run{padding:15px 0}.queue-list .run:first-child{border-top:0}.queue-list .run>div{min-width:0}.queue-list .run-name{color:#263b34}.queue-list .run-name:hover{color:#08796b}.queue-list .run-meta{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.queue-list .badge{flex-shrink:0}
@media(max-width:900px){.grid{grid-template-columns:1fr}.shell{padding:18px}.card{padding:18px}}"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def badge(state: str) -> str:
    labels = {"READY_FOR_APPROVAL": "รอคนตรวจ", "APPROVED": "อนุมัติแล้ว", "REJECTED": "ปฏิเสธแล้ว",
              "EVIDENCE_NEEDED": "หลักฐานไม่ครบ", "QA_DONE": "QA ไม่ผ่าน", "FAILED": "ผลิตไม่สำเร็จ",
              "SKIPPED": "ข้ามสินค้า", "NEW": "ยังไม่เริ่ม", "REGENERATE": "กำลังแก้คลิป"}
    cls = "ready" if state == "READY_FOR_APPROVAL" else "approved" if state == "APPROVED" else "blocked" if state in ("EVIDENCE_NEEDED", "QA_DONE", "FAILED", "SKIPPED") else ""
    return f'<span class="badge {cls}">{esc(labels.get(state, state))}</span>'


def review_state(run: Run) -> str:
    """Legacy READY runs remain visible, but do not look approval ready without current rights gates."""
    state = run.state()["state"]
    if state != "READY_FOR_APPROVAL":
        return state
    path = run.p("out", "qa_report.json")
    if not path.is_file():
        return "EVIDENCE_NEEDED"
    qa = read_json(path)
    checks = {c.get("name"): c for c in qa.get("checks", [])}
    if not qa.get("publishable") or any(not checks.get(k, {}).get("ok") for k in ("rights.documented_assets", "tts.license")):
        return "EVIDENCE_NEEDED"
    return state


def run_name(run: Run) -> str:
    for path in (run.p("out", "manifest.json"), run.p("product.json")):
        if path.is_file():
            data = read_json(path)
            if data.get("product") or data.get("name"):
                return str(data.get("product") or data.get("name"))
    return run.id


def page(title: str, body: str) -> bytes:
    return (f'<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)} · STP Review</title><style>{CSS}</style></head><body><main class="shell">'
            '<header class="top"><a class="brand" href="/">STP <span>Review</span></a><span class="eyebrow">Local approval desk</span></header>'
            f'{body}</main></body></html>').encode("utf-8")


class ReviewServer(ThreadingHTTPServer):
    def __init__(self, runs_dir: Path, port: int):
        self.runs_dir = Path(runs_dir).resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.csrf = secrets.token_urlsafe(32)
        self.worker_lock = threading.Lock()
        self.db_path = self.runs_dir / "review.sqlite3"
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, at TEXT NOT NULL, run_id TEXT NOT NULL, version INTEGER NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL)")
        super().__init__(("127.0.0.1", port), ReviewHandler)

    def db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

    def get_run(self, rid: str) -> Run | None:
        if not rid or rid in (".", "..") or "/" in rid or "\\" in rid:
            return None
        path = (self.runs_dir / rid).resolve()
        if path.parent != self.runs_dir or not (path / "state.json").is_file():
            return None
        return Run(path)

    def audit(self, run: Run, action: str, detail: str, status: str) -> int:
        with self.db() as db:
            cur = db.execute("INSERT INTO actions(at,run_id,version,action,detail,status) VALUES(?,?,?,?,?,?)",
                             (datetime.now(timezone.utc).isoformat(), run.id, run.version(), action, detail, status))
            return int(cur.lastrowid)

    def finish_audit(self, aid: int, status: str) -> None:
        with self.db() as db:
            db.execute("UPDATE actions SET status=? WHERE id=?", (status, aid))


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer

    def log_message(self, format: str, *args) -> None:
        # Avoid logging revision text or paths from browser URLs.
        pass

    def send_html(self, status: int, title: str, body: str) -> None:
        data = page(title, body)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; media-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, path: str) -> None:
        self.send_response(303)
        self.send_header("Location", path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parts = [unquote(x) for x in urlsplit(self.path).path.strip("/").split("/")]
        if parts == [""]:
            return self.index()
        if len(parts) >= 2 and parts[0] == "run":
            run = self.server.get_run(parts[1])
            if not run:
                return self.send_html(404, "Not found", "<h1>ไม่พบงาน</h1>")
            if len(parts) == 2:
                return self.detail(run)
            if len(parts) == 4 and parts[2] == "file":
                return self.file(run, parts[3])
            if len(parts) == 4 and parts[2] == "asset":
                return self.asset(run, parts[3])
            if len(parts) == 5 and parts[2] == "version" and parts[4] in ("final.mp4", "final.srt", "post.txt", "qa_report.json"):
                if not parts[3].startswith("v") or not parts[3][1:].isdigit():
                    return self.send_error(404)
                return self.file(run, parts[4], version=parts[3])
        self.send_html(404, "Not found", "<h1>ไม่พบหน้า</h1>")

    def index(self) -> None:
        runs = [Run(p) for p in sorted(self.server.runs_dir.iterdir(), reverse=True) if p.is_dir() and (p / "state.json").is_file()]
        ready = [r for r in runs if review_state(r) == "READY_FOR_APPROVAL"]
        blocked = [r for r in runs if review_state(r) in ("EVIDENCE_NEEDED", "QA_DONE", "FAILED", "SKIPPED")]
        other = [r for r in runs if r not in ready and r not in blocked]

        def cards(items: list[Run]) -> str:
            return "".join(f'<div class="run"><div><a class="run-name" href="/run/{quote(r.id)}">{esc(run_name(r))}</a><span class="run-meta">v{r.version()} · {esc(r.id)}</span></div>{badge(review_state(r))}</div>' for r in items)

        ready_section = (f'<section class="card queue-list"><div class="section-heading"><h2>พร้อมให้ตรวจ</h2><span class="queue-count">{len(ready)} คลิป</span></div>{cards(ready)}</section>'
                         if ready else '<section class="empty-state"><div class="mark">✓</div><h2>ยังไม่มีคลิปพร้อม Review</h2><p>บอทยังไม่มีแพ็กเกจที่ผ่าน QA และมีหลักฐานสิทธิ์รูปกับเสียงครบ เมื่อผ่านแล้วคลิปจะปรากฏในคิวนี้เพื่อให้คุณดูและอนุมัติ</p></section>')
        blocked_section = (f'<section class="card queue-secondary"><details class="fold"><summary>งานที่บอทติดขัดหรือ QA ไม่ผ่าน ({len(blocked)})</summary><div class="queue-list">{cards(blocked)}</div></details></section>' if blocked else "")
        other_section = (f'<section class="card queue-secondary"><details class="fold"><summary>งานอื่นและประวัติ ({len(other)})</summary><div class="queue-list">{cards(other)}</div></details></section>' if other else "")
        body = (f'<div class="eyebrow">STP PICKS · REVIEW</div><div class="queue-head"><div><h1>ตรวจคลิปก่อนโพสต์</h1><p class="small-note">คนดูคลิป ตรวจหลักฐาน แล้วสั่งแก้หรืออนุมัติที่ท้ายงาน</p></div><span class="queue-count">พร้อมตรวจ {len(ready)} · ติดขัด {len(blocked)}</span></div>'
                f'{ready_section}{blocked_section}{other_section}')
        self.send_html(200, "Review queue", body)

    def detail(self, run: Run) -> None:
        state = run.state()["state"]
        out = run.p("out")
        qa = read_json(out / "qa_report.json") if (out / "qa_report.json").is_file() else {}
        def check_row(c: dict) -> str:
            detail = str(c.get("detail", ""))
            if len(detail) > 130:
                detail = detail[:127] + "…"
            return f'<li><span class="{"ok" if c.get("ok") else "fail"}">{"●" if c.get("ok") else "!"}</span><span class="checktext"><b>{esc(c.get("name", ""))}</b><small>{esc(detail)}</small></span></li>'
        checks = "".join(check_row(c) for c in qa.get("checks", []))
        media = f'<video controls preload="metadata" src="/run/{quote(run.id)}/file/final.mp4"></video>' if (out / "final.mp4").is_file() else '<div class="empty">ยังไม่มี MP4</div>'
        files = "".join(f'<a href="/run/{quote(run.id)}/file/{name}">{name}</a>' for name in ("final.mp4", "final_tt.mp4", "final.srt", "post.txt", "qa_report.json", "manifest.json", "check.jpg") if (out / name).is_file())
        post = (out / "post.txt").read_text(encoding="utf-8") if (out / "post.txt").is_file() else "ยังไม่มีข้อความโพสต์"
        asset_rows = read_json(run.p("assets", "assets.json")) if run.p("assets", "assets.json").is_file() else []
        asset_cards = ""
        for a in asset_rows:
            if not a.get("path"):
                continue
            name = Path(a["path"]).name
            evidence = a.get("rights_evidence_path")
            evidence_link = f'<a href="/run/{quote(run.id)}/asset/{quote(Path(evidence).name)}">หลักฐานสิทธิ์</a>' if evidence else "ไม่มีไฟล์หลักฐาน"
            asset_cards += f'<div class="asset"><a href="/run/{quote(run.id)}/asset/{quote(name)}"><img src="/run/{quote(run.id)}/asset/{quote(name)}" alt="{esc(a.get("id", "รูปสินค้า"))}"></a><b>{esc(a.get("id", ""))}</b><small>{esc(a.get("rights", "unknown"))} · {esc(a.get("rights_owner") or "ไม่ระบุเจ้าของ")}</small><small>{esc(a.get("rights_license") or "ไม่ระบุ license")}</small><small>{evidence_link}</small></div>'
        vo_info = read_json(run.p("work", "vo", "vo.json")) if run.p("work", "vo", "vo.json").is_file() else {}
        voice_evidence = vo_info.get("rights_evidence") or {}
        voice_link = f'<a href="/run/{quote(run.id)}/asset/{quote(Path(voice_evidence["path"]).name)}">เปิดหลักฐานสิทธิ์เสียง</a>' if voice_evidence.get("path") else "ไม่มีหลักฐานสิทธิ์เสียง"
        versions = "".join(f'<div class="run"><b>{esc(p.name)}</b><span class="files"><a href="/run/{quote(run.id)}/version/{p.name}/final.mp4">ดู MP4</a><a href="/run/{quote(run.id)}/version/{p.name}/qa_report.json">QA</a></span></div>' for p in sorted(run.p("versions").glob("v*")) if (p / "out" / "final.mp4").is_file()) if run.p("versions").is_dir() else ""
        with self.server.db() as db:
            actions = db.execute("SELECT at,action,detail,status FROM actions WHERE run_id=? ORDER BY id DESC LIMIT 20", (run.id,)).fetchall()
        history = "".join(f'<div class="run"><div><b>{esc(a)}</b><div class="muted">{esc(t)} · {esc(d)}</div></div>{badge(s)}</div>' for t, a, d, s in actions)
        visible_state = review_state(run)
        failed = [c for c in qa.get("checks", []) if not c.get("ok")]
        recorded_checks = {c.get("name") for c in qa.get("checks", [])}
        if visible_state == "EVIDENCE_NEEDED":
            for gate, message in (("rights.documented_assets", "ยังไม่มีผลตรวจหลักฐานสิทธิ์รูปตาม gate ปัจจุบัน"),
                                  ("tts.license", "ยังไม่มีผลตรวจสิทธิ์เสียงตาม gate ปัจจุบัน")):
                if gate not in recorded_checks:
                    failed.append({"name": gate, "detail": message, "ok": False})
        failed_html = "".join(check_row(c) for c in failed)
        qa_summary = f'<ul class="checks">{failed_html}</ul>' if failed else '<p class="small-note ok">✓ ผ่านรายการตรวจอัตโนมัติ</p>'
        can_review = visible_state == "READY_FOR_APPROVAL"
        can_revise = cli.revision_ready(run)
        token = f'<input type="hidden" name="csrf" value="{self.server.csrf}"><input type="hidden" name="version" value="{run.version()}">'
        revise_form = (f'<form method="post" action="/run/{quote(run.id)}/revise">{token}<label for="instruction">สั่งแก้คลิป</label><textarea id="instruction" name="instruction" required placeholder="เช่น เปลี่ยน hook ให้กระชับ และอย่าพูดว่าทดสอบเอง"></textarea><label for="avoid">คำที่ห้ามกลับมา (หนึ่งคำ/วลีต่อบรรทัด)</label><textarea id="avoid" name="avoid" style="min-height:70px"></textarea><label for="director">AI ที่เขียนบทใหม่</label><select id="director" name="director"><option value="ollama">Ollama / Qwen3</option><option value="claude_cli">Claude CLI</option></select><div class="actions"><button>ส่งให้บอทแก้</button></div></form>') if can_revise else '<p class="note">สั่งแก้คลิปได้เมื่อมี MP4 และหลักฐานสิทธิ์รูป/เสียงผ่าน QA แล้ว งานนี้ต้องเติมหลักฐานสิทธิ์ก่อน</p>'
        decision_form = (f'<form method="post" action="/run/{quote(run.id)}/decide">{token}<label for="note">หมายเหตุการตัดสินใจ</label><input id="note" name="note" placeholder="เหตุผลหรือสิ่งที่ตรวจ"><label class="confirm"><input type="checkbox" name="reviewed" value="yes">ฉันดู/ฟังคลิป ตรวจข้อเท็จจริง และอ่านหลักฐานสิทธิ์แล้ว</label><div class="actions"><button name="decision" value="approve">ตรวจแล้ว · อนุมัติ</button><button class="danger" name="decision" value="reject">ปฏิเสธ</button></div><p class="muted">การอนุมัติไม่โพสต์คลิปอัตโนมัติ</p></form>') if can_review else '<p class="note">อนุมัติได้เมื่อ QA ผ่านและหลักฐานสิทธิ์ครบเท่านั้น</p>'
        forms = revise_form + decision_form
        body = (f'<a href="/">← คิวงาน</a><div class="eyebrow" style="margin-top:22px">Review package · version {run.version()}</div>'
                f'<h1 class="detail-title">{esc(run_name(run))}</h1><div class="run-id">{esc(run.id)}</div>'
                f'<div class="summary">{badge(visible_state)}</div><div class="grid"><div class="stack">'
                f'<section class="video">{media}</section>'
                f'<section class="card compact-card"><h2>ไฟล์แพ็กเกจ</h2><div class="files">{files}</div></section>'
                f'<section class="card"><details class="fold"><summary>ภาพและหลักฐานสิทธิ์ ({len(asset_rows)} รูป)</summary><div class="assetgrid">{asset_cards or "<p>ยังไม่มีข้อมูลรูป</p>"}</div><p>{voice_link}</p></details></section>'
                f'<section class="card"><details class="fold"><summary>ข้อความโพสต์</summary><div class="pre">{esc(post)}</div></details></section>'
                f'<section class="card compact-card"><h2>เวอร์ชันก่อน</h2>{versions or "<p class=small-note>ยังไม่มี</p>"}</section></div>'
                f'<div class="stack"><section class="card"><h2>{"เหตุผลที่ยังไม่เข้าคิว" if failed else "ผล QA"}</h2>{qa_summary}'
                f'<details class="qa-all"><summary>ดูผลตรวจทั้งหมด ({len(qa.get("checks", []))} รายการ)</summary><ul class="checks">{checks or "<li>ยังไม่มีรายงาน QA</li>"}</ul></details></section>'
                f'<section class="card compact-card"><h2>ตรวจและตัดสินใจ</h2>{forms}</section>'
                f'<section class="card compact-card"><h2>ประวัติคำสั่ง</h2>{history or "<p class=small-note>ยังไม่มี</p>"}</section></div></div>')
        self.send_html(200, run.id, body)

    def asset(self, run: Run, name: str) -> None:
        if not name or Path(name).name != name or name in (".", ".."):
            return self.send_error(404)
        recorded = set()
        path = run.p("assets", "assets.json")
        if path.is_file():
            for a in read_json(path):
                for key in ("path", "rights_evidence_path"):
                    if a.get(key):
                        recorded.add(Path(a[key]).name)
        vo_path = run.p("work", "vo", "vo.json")
        if vo_path.is_file():
            rights = read_json(vo_path).get("rights_evidence") or {}
            if rights.get("path"):
                recorded.add(Path(rights["path"]).name)
        if name not in recorded:
            return self.send_error(404)
        base = run.p("assets", "evidence") if (run.p("assets", "evidence", name)).is_file() else run.p("assets")
        file = base / name
        if not file.is_file() or file.is_symlink() or file.resolve().parent != base.resolve():
            return self.send_error(404)
        kinds = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8"}
        self.send_response(200)
        self.send_header("Content-Type", kinds.get(file.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(file.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", "inline" if file.suffix.lower() in kinds else "attachment")
        self.end_headers()
        self.wfile.write(file.read_bytes())

    def file(self, run: Run, name: str, version: str | None = None) -> None:
        allowed = {"final.mp4": "video/mp4", "final_tt.mp4": "video/mp4", "final.srt": "text/plain; charset=utf-8", "post.txt": "text/plain; charset=utf-8", "qa_report.json": "application/json", "manifest.json": "application/json", "check.jpg": "image/jpeg"}
        if name not in allowed:
            return self.send_error(404)
        root = run.p("versions", version, "out") if version else run.p("out")
        path = root / name
        if not path.is_file() or path.is_symlink() or path.resolve().parent != root.resolve():
            return self.send_error(404)
        size = path.stat().st_size
        start, end = 0, size - 1
        raw_range = self.headers.get("Range", "")
        if raw_range and name.endswith(".mp4"):
            try:
                unit, span = raw_range.split("=", 1)
                left, right = span.split("-", 1)
                if unit != "bytes" or not left:
                    raise ValueError
                start = int(left)
                end = min(int(right), size - 1) if right else size - 1
                if start < 0 or start > end or start >= size:
                    raise ValueError
            except ValueError:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
        self.send_response(206 if raw_range and name.endswith(".mp4") else 200)
        self.send_header("Content-Type", allowed[name])
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        if raw_range and name.endswith(".mp4"):
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:
        parts = [unquote(x) for x in urlsplit(self.path).path.strip("/").split("/")]
        if len(parts) != 3 or parts[0] != "run" or parts[2] not in ("revise", "decide"):
            return self.send_error(404)
        run = self.server.get_run(parts[1])
        if not run:
            return self.send_error(404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send_error(400)
        if length < 1 or length > 16384:
            return self.send_error(413)
        form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        one = lambda key: form.get(key, [""])[0]
        if not secrets.compare_digest(one("csrf"), self.server.csrf) or one("version") != str(run.version()):
            return self.send_html(409, "Stale review", "<h1>หน้านี้เก่าแล้ว</h1><p>กลับไปโหลดงานใหม่ก่อนตัดสินใจ</p>")
        if parts[2] == "revise" and not cli.revision_ready(run):
            return self.send_html(409, "Not ready", "<h1>ยังสั่งแก้คลิปไม่ได้: ต้องมี MP4 และหลักฐานสิทธิ์รูป/เสียงผ่าน QA</h1>")
        if parts[2] == "decide" and run.state()["state"] != "READY_FOR_APPROVAL":
            return self.send_html(409, "Not ready", "<h1>งานยังไม่พร้อมให้ตัดสินใจ</h1>")
        qa_path = run.p("out", "qa_report.json")
        if parts[2] == "decide":
            if not qa_path.is_file() or not read_json(qa_path).get("publishable"):
                return self.send_html(409, "QA blocked", "<h1>QA ยังไม่ผ่าน</h1>")
            checks = {c.get("name"): c for c in read_json(qa_path).get("checks", [])}
            if any(not checks.get(k, {}).get("ok") for k in ("rights.documented_assets", "tts.license")):
                return self.send_html(409, "Rights blocked", "<h1>หลักฐานสิทธิ์ยังไม่ผ่าน</h1>")
        if parts[2] == "revise":
            instruction = one("instruction").strip()
            if not instruction or len(instruction) > 4000:
                return self.send_error(400)
            director = one("director")
            if director not in ("ollama", "claude_cli"):
                return self.send_error(400)
            avoid = [x.strip() for x in one("avoid").splitlines() if x.strip()]
            if len(avoid) > 30 or any(len(x) > 200 for x in avoid):
                return self.send_error(400)
            if not self.server.worker_lock.acquire(blocking=False):
                return self.send_html(409, "Busy", "<h1>บอทกำลังทำงานอื่น</h1><p>รอให้งานก่อนเสร็จแล้วลองใหม่</p>")
            aid = self.server.audit(run, "revise", instruction, "RUNNING")
            def work() -> None:
                try:
                    args = argparse.Namespace(run=str(run.path), instruction=instruction, avoid_phrase=avoid,
                                              director=director, config=None)
                    code = cli.cmd_revise(args)
                    self.server.finish_audit(aid, "DONE" if code == 0 and run.state()["state"] == "READY_FOR_APPROVAL" else "FAILED")
                except Exception:
                    self.server.finish_audit(aid, "FAILED")
                finally:
                    self.server.worker_lock.release()
            threading.Thread(target=work, daemon=True).start()
            return self.redirect(f"/run/{quote(run.id)}")
        decision = one("decision")
        if decision not in ("approve", "reject"):
            return self.send_error(400)
        if decision == "approve" and one("reviewed") != "yes":
            return self.send_html(400, "Review required", "<h1>กรุณายืนยันการตรวจคลิปและหลักฐานก่อนอนุมัติ</h1>")
        note = one("note").strip()
        if len(note) > 2000:
            return self.send_error(400)
        if not self.server.worker_lock.acquire(blocking=False):
            return self.send_html(409, "Busy", "<h1>บอทกำลังทำงานอื่น</h1>")
        try:
            args = argparse.Namespace(run=str(run.path), decision=decision, note=note,
                                      reviewed=one("reviewed") == "yes")
            code = cli.cmd_decide(args)
            self.server.audit(run, decision, note, "DONE" if code == 0 else "FAILED")
        finally:
            self.server.worker_lock.release()
        return self.redirect(f"/run/{quote(run.id)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Local STP Review web app")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--config")
    args = ap.parse_args(argv)
    cfg = load(Path(args.config) if args.config else None)
    server = ReviewServer(cfg.runs_dir, args.port)
    print(f"Review UI: http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
