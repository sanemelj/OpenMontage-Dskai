"""Batch-produce a storyboard segment: keyframes (Qwen-Image-Edit) -> clips (Kandinsky 6 I2V).

Reads a shots JSON (see series/lyen-san/episodes/*_shots.json). Already-rendered
outputs are skipped, so a run can be resumed or re-run for missing shots only.

    python tools/gpu/series_batch.py series/lyen-san/episodes/ep01_sc01-04_shots.json \
        --assets series/lyen-san/assets --out projects/lyen-san/ep01 --stage all --seeds 1,2
"""

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "modal_apps"))

import modal  # noqa: E402

KF_W, KF_H = 1664, 928
K6_MODEL = "kandinskylab/Kandinsky-6.0-Lite-distill-5s-Diffusers"


def set_text(shot: dict, spec: dict) -> str:
    return spec.get("sets", {}).get(shot.get("set", ""), "")


def keyframe_prompt(shot: dict, look: str, setting: str = "") -> str:
    return (
        f"Cinematic film still from a premium drama series. {shot['frame']}. {setting} "
        "Keep the exact faces, hairstyles, skin tones and clothing of the people in the reference images; "
        "keep the architecture and props of the location reference. "
        f"{look}"
    )


def video_prompt(shot: dict, look: str, setting: str = "") -> str:
    parts = [f"{shot['frame']}.", setting, f"{shot['motion']}."]
    if shot.get("line"):
        who = shot.get("who", "She")
        pron = "her" if who == "She" else "his"
        parts.append(
            f'{who} speaks Haitian Creole with a Haitian accent, slowly, every syllable clear: "{shot["line"]}" '
            f"Audio: only {pron} clear voice, quiet room tone."
        )
    parts.append(look)
    return " ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("shots")
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage", choices=["keyframes", "video", "all"], default="all")
    ap.add_argument("--seeds", default="1,2")
    ap.add_argument("--only", default="", help="comma-separated shot ids")
    ap.add_argument("--kf-gpu", default="H100")
    ap.add_argument("--video-gpu", default="L40S")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    spec = json.loads(Path(args.shots).read_text())
    assets, out = Path(args.assets), Path(args.out)
    kf_dir, clip_dir = out / "keyframes", out / "clips"
    kf_dir.mkdir(parents=True, exist_ok=True)
    clip_dir.mkdir(parents=True, exist_ok=True)
    only = {s for s in args.only.split(",") if s}
    shots = [s for s in spec["shots"] if not only or s["id"] in only]
    seeds = [int(s) for s in args.seeds.split(",")]
    look = spec["look"]
    log = out / "batch_log.jsonl"

    from kandinsky6 import Kandinsky6  # noqa: E402
    from kandinsky6 import app as k6_app  # noqa: E402
    from qwen_image import QwenEdit, QwenT2I  # noqa: E402
    from qwen_image import app as qwen_app  # noqa: E402

    def record(row: dict) -> None:
        print(json.dumps(row), flush=True)
        with log.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def safe(fn, stage):
        # One failed shot must not abort the rest of the batch; it is logged and can be re-run.
        def run(job):
            try:
                return fn(job)
            except Exception as exc:
                shot = job[0] if isinstance(job, tuple) else job
                return {"stage": stage, "shot": shot["id"], "error": repr(exc)[:500], "ts": time.time()}
        return run

    if args.stage in ("keyframes", "all"):
        todo = [s for s in shots if not (kf_dir / f"{s['id']}.png").exists()]
        with modal.enable_output(), qwen_app.run():
            ed = QwenEdit.with_options(gpu=args.kf_gpu)()
            t2i = QwenT2I.with_options(gpu=args.kf_gpu)()

            def kf(shot):
                refs = [(assets / spec["refs"][r]).read_bytes() for r in shot["refs"]]
                p = keyframe_prompt(shot, look, set_text(shot, spec))
                if refs:
                    r = ed.generate.remote(p, refs, 1, 40, 4.0, width=KF_W, height=KF_H)
                else:  # empty set / insert shot: no reference to keep
                    r = t2i.generate.remote(p, KF_W, KF_H, 1)
                (kf_dir / f"{shot['id']}.png").write_bytes(r.pop("image"))
                return {"stage": "keyframe", "shot": shot["id"], "prompt": p, **r, "ts": time.time()}

            with cf.ThreadPoolExecutor(args.workers) as ex:
                for row in ex.map(safe(kf, "keyframe"), todo):
                    record(row)

    if args.stage in ("video", "all"):
        jobs = [
            (s, seed) for s in shots for seed in seeds
            if not (clip_dir / f"{s['id']}_s{seed}.mp4").exists() and (kf_dir / f"{s['id']}.png").exists()
        ]
        with modal.enable_output(), k6_app.run():
            k6 = Kandinsky6.with_options(gpu=args.video_gpu)(model_id=K6_MODEL)

            def vid(job):
                shot, seed = job
                p = video_prompt(shot, look, set_text(shot, spec))
                r = k6.generate.remote(prompt=p, image_bytes=(kf_dir / f"{shot['id']}.png").read_bytes(), seed=seed)
                (clip_dir / f"{shot['id']}_s{seed}.mp4").write_bytes(r.pop("video"))
                return {"stage": "video", "shot": shot["id"], "prompt": p, **r, "ts": time.time()}

            with cf.ThreadPoolExecutor(args.workers) as ex:
                for row in ex.map(safe(vid, "video"), jobs):
                    record(row)


if __name__ == "__main__":
    main()
