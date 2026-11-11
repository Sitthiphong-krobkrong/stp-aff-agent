"""Deterministic orchestrator: product folder → run dir → MP4 package. Each step is idempotent (skipped when
already done) so `resume` continues after a crash; `regen --from <step>` invalidates later steps."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import assets as assets_mod
from . import director, qa, render
from .config import Config
from .runs import Run
from .schemas import Asset, Product, VideoPlan, now_iso
from .sources.manual import product_from_folder
from .tts import apply_pronounce, load_pronounce, synth_lines
from .util import StepError, duration, log, read_json, write_json

STEPS = ["research", "assets", "plan", "voice", "render", "qa", "package"]
MAX_RETRIES = 2
TT_CTA = {"head": "โค้ดในคอมเมนต์|ที่ปักหมุด", "sub": "คัดลอกไปค้นใน Shopee",
          "vo": "โค้ดค้นหาอยู่ในคอมเมนต์ที่ปักหมุด กดดูได้เลย"}


class Pipeline:
    def __init__(self, run: Run, cfg: Config, plan_file: Path | None = None):
        self.run, self.cfg, self.plan_file = run, cfg, plan_file

    # ---------------------------------------------------------------- helpers
    def product(self) -> Product:
        return Product.model_validate(read_json(self.run.p("product.json")))

    def assets(self) -> list[Asset]:
        return [Asset.model_validate(a) for a in read_json(self.run.p("assets", "assets.json"))]

    def plan(self) -> VideoPlan:
        return VideoPlan.model_validate(read_json(self.run.p("plan.json")))

    def tiktok(self) -> bool:
        return bool(self.product().tiktok_code)

    # ---------------------------------------------------------------- steps
    def step_research(self, folder: Path) -> None:
        prod, info = product_from_folder(folder)
        write_json(self.run.p("product.json"), prod)
        write_json(self.run.p("source_info.json"), {**info, "folder": str(folder), "copied_at": now_iso()})
        self.run.set_state("RESEARCHED")

    def step_assets(self) -> None:
        info = read_json(self.run.p("source_info.json"))
        folder = Path(info["folder"])
        local = sorted(str(p) for p in (folder / "images").glob("*")
                       if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if (folder / "images").exists() else []
        got = assets_mod.ingest(local + info.get("images", []), self.run.path, self.cfg, info.get("rights"))
        ok = [a for a in got if assets_mod.usable(a)]
        if len(ok) < 3:
            reasons = sorted({a.rejected or a.rights_note for a in got if not assets_mod.usable(a)})
            self.run.set_state("SKIPPED", reason=f"only {len(ok)} usable images", details=reasons)
            raise StepError(f"SKIPPED: only {len(ok)} usable images ({'; '.join(reasons)[:300]})")
        self.run.set_state("ASSETS_READY", usable_images=len(ok))

    def step_plan(self) -> None:
        usable = [a for a in self.assets() if assets_mod.usable(a)]
        vp, attempts = director.plan(self.product(), usable, self.cfg, self.plan_file)
        write_json(self.run.p("plan.json"), vp)
        write_json(self.run.p("work", "director_attempts.json"), attempts)
        self.run.set_state("PLANNED", director=vp.director)

    def _vo_lines(self) -> list[str]:
        lines = [s.vo for s in self.plan().shots]
        if self.tiktok():
            lines.append(TT_CTA["vo"])
        return lines

    def step_voice(self) -> None:
        pron = load_pronounce(self.cfg.pronounce)
        prod_pron = Path(read_json(self.run.p("source_info.json"))["folder"]) / "pronounce.json"
        pron.update(load_pronounce(prod_pron))
        spoken = [apply_pronounce(t.replace("|", " "), pron) for t in self._vo_lines()]
        paths = synth_lines(spoken, self.run.p("work", "vo"), self.cfg)
        write_json(self.run.p("work", "vo", "vo.json"), {"provider": self.cfg.tts.provider, "voice": self.cfg.tts.voice,
                                                       "spoken": spoken, "files": [p.name for p in paths],
                                                       "durations": [duration(p) for p in paths]})
        self.run.set_state("VOICED", tts=self.cfg.tts.provider)

    def _render_variant(self, platform: str) -> tuple[Path, render.Timing]:
        vp, cfg = self.plan(), self.cfg
        shots = list(vp.shots)
        vo_meta = read_json(self.run.p("work", "vo", "vo.json"))
        vo_files = [self.run.p("work", "vo", f) for f in vo_meta["files"]]
        durs = list(vo_meta["durations"])
        n = len(shots)
        if platform == "tiktok":
            shots[-1] = shots[-1].model_copy(update={k: TT_CTA[k] for k in ("head", "sub", "vo")})
            vo_files = vo_files[:n - 1] + [vo_files[n]]
            durs = durs[:n - 1] + [durs[n]]
        else:
            vo_files, durs = vo_files[:n], durs[:n]
        timing = render.plan_timing(durs, [s.style for s in shots], cfg)
        work = self.run.p("work", platform)
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        by_id = {a.id: a for a in self.assets()}
        segs = []
        for i, s in enumerate(shots):
            card = work / f"card_{i}.png"
            top = render.make_card(s, card, cfg)
            fp = work / f"frame_{i}.jpg"
            anchor = render.compose_frame(self.run.p(by_id[s.asset_id].path), fp, cfg, top)
            seg = work / f"seg_{i}.mp4"
            render.render_segment(fp, card, timing.slots[i], anchor, seg, cfg, zoom_in=i % 2 == 0)
            log.info("%s shot %d/%d %s %.2fs", platform, i + 1, n, s.style, timing.slots[i])
            segs.append(seg)
        audio = work / "vo_track.wav"
        render.build_audio(vo_files, timing, audio, cfg, normalize=cfg.tts.provider != "silent")
        name = "final" if platform == "shopee" else "final_tt"
        out = self.run.p("out", f"{name}.mp4")
        render.concat_and_mux(segs, audio, out, work)
        render.srt([s.vo for s in shots], timing, cfg.video.lead, self.run.p("out", f"{name}.srt"))
        write_json(work / "timing.json", timing.__dict__)
        return out, timing

    def step_render(self) -> None:
        self._render_variant("shopee")
        if self.tiktok():
            self._render_variant("tiktok")
        self.run.set_state("RENDERED")

    def step_qa(self) -> None:
        outs = {"shopee": self.run.p("out", "final.mp4")}
        if self.tiktok():
            outs["tiktok"] = self.run.p("out", "final_tt.mp4")
        t = read_json(self.run.p("work", "shopee", "timing.json"))
        rep = qa.run_qa(plan=self.plan(), product=self.product(), assets=self.assets(), outputs=outs,
                        tts_provider=read_json(self.run.p("work", "vo", "vo.json"))["provider"],
                        timing_warning=t.get("warning", ""), cfg=self.cfg)
        qa.contact_sheet(outs["shopee"], t["starts"], t["slots"], self.run.p("out", "check.jpg"),
                         self.run.p("work", "shopee"))
        write_json(self.run.p("out", "qa_report.json"), rep)
        self.run.set_state("QA_DONE", publishable=rep.publishable)

    def step_package(self) -> None:
        vp, prod = self.plan(), self.product()
        rep = read_json(self.run.p("out", "qa_report.json"))
        parts = [
            "== SHOPEE (≤150, ปักตะกร้าสินค้านี้) ==", f"{vp.shopee_caption} {' '.join(vp.hashtags)}".strip(), "",
            "== TIKTOK CAPTION ==", vp.tiktok_caption, "",
        ]
        if prod.tiktok_code:
            parts += ["== TIKTOK COMMENT แรก (ปักหมุด) ==", prod.tiktok_code, ""]
        parts += ["== สินค้า ==", prod.name, f"listing: {prod.listing_url or '-'}",
                  f"affiliate: {prod.affiliate_link or '-'}", ""]
        warn = [f"- {c['name']}: {c['detail']}" for c in rep["checks"] if not c["ok"]]
        if warn:
            parts += ["== ต้องดูก่อนโพสต์ ==", *warn, ""]
        parts += ["== เช็คก่อนกด approve ==", "- ฟังการออกเสียงคำอังกฤษ/ชื่อรุ่น",
                  "- สินค้ายังขายอยู่ ราคา/ค่าคอมยังตรง", "- รูปที่ใช้ตรงรุ่น/สีที่ปักตะกร้า"]
        self.run.p("out", "post.txt").write_text("\n".join(parts) + "\n", encoding="utf-8")
        write_json(self.run.p("out", "manifest.json"), {
            "run_id": self.run.id, "product": prod.name, "listing_url": prod.listing_url,
            "affiliate_link": prod.affiliate_link, "videos": sorted(p.name for p in self.run.p("out").glob("*.mp4")),
            "publishable": rep["publishable"], "approval_state": "pending" if rep["publishable"] else "blocked",
            "assets_used": sorted({s.asset_id for s in vp.shots}), "created_at": now_iso()})
        if rep["publishable"]:
            self.run.set_state("READY_FOR_APPROVAL")
        else:
            blocking = [c["name"] for c in rep["checks"] if c["blocking"] and not c["ok"]]
            self.run.set_state("QA_DONE", publishable=False, blocked_by=blocking)

    # ---------------------------------------------------------------- driver
    def execute(self, folder: Path | None = None) -> str:
        for step in STEPS:
            if self.run.step_done(step):
                continue
            fn = getattr(self, f"step_{step}")
            while True:
                try:
                    fn(folder) if step == "research" else fn()
                    self.run.mark_step(step, True)
                    break
                except StepError as e:
                    self.run.mark_step(step, False, error=str(e)[:1000])
                    if str(e).startswith("SKIPPED") or self.run.retries(step) > MAX_RETRIES or step in ("plan",):
                        if not str(e).startswith("SKIPPED"):
                            self.run.set_state("FAILED", failed_step=step, error=str(e)[:500])
                        raise
                    log.warning("step %s failed (retry %d): %s", step, self.run.retries(step), e)
        return self.run.state()["state"]
