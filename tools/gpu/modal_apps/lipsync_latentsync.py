"""LatentSync 1.6 (ByteDance, Apache-2.0) lip-sync on Modal.

Re-drives the mouth of an existing clip to match a new dialogue track
(e.g. a recorded Kreyòl line). Checkpoints live in the shared HF cache Volume.

    modal run tools/gpu/modal_apps/lipsync_latentsync.py --video in.mp4 --audio line.wav --out out.mp4 --gpu L40S
"""

import os
from pathlib import Path

import modal

APP_NAME = "openmontage-latentsync"
REPO = "https://github.com/bytedance/LatentSync.git"
CKPT_REPO = "ByteDance/LatentSync-1.6"
GPU = os.environ.get("LATENTSYNC_MODAL_GPU", "L40S")

hf_cache = modal.Volume.from_name("openmontage-hf-cache", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
    .run_commands(f"git clone --depth 1 {REPO} /opt/LatentSync")
    .run_commands("pip install -r /opt/LatentSync/requirements.txt hf_transfer")
    .env({"HF_HOME": "/cache/hf", "HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .workdir("/opt/LatentSync")
)

app = modal.App(APP_NAME, image=image)


@app.function(gpu=GPU, volumes={"/cache": hf_cache}, timeout=60 * 30)
def lipsync(
    video: bytes,
    audio: bytes,
    inference_steps: int = 20,
    guidance_scale: float = 1.5,
    seed: int = 1247,
) -> dict:
    import subprocess
    import tempfile
    import time

    import torch
    from huggingface_hub import hf_hub_download

    ckpt = Path("/opt/LatentSync/checkpoints")
    ckpt.mkdir(exist_ok=True)
    for name in ("latentsync_unet.pt", "whisper/tiny.pt"):
        dst = ckpt / name
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(hf_hub_download(CKPT_REPO, name))
    hf_cache.commit()

    # temp_dir is relative to cwd (/opt/LatentSync); give each call its own.
    with tempfile.TemporaryDirectory() as td:
        v, a, o = Path(td, "in.mp4"), Path(td, "in.wav"), Path(td, "out.mp4")
        v.write_bytes(video)
        a.write_bytes(audio)
        t0 = time.time()
        subprocess.run(
            [
                "python", "-m", "scripts.inference",
                "--unet_config_path", "configs/unet/stage2_512.yaml",
                "--inference_ckpt_path", str(ckpt / "latentsync_unet.pt"),
                "--inference_steps", str(inference_steps),
                "--guidance_scale", str(guidance_scale),
                "--enable_deepcache",
                "--seed", str(seed),
                "--video_path", str(v),
                "--audio_path", str(a),
                "--video_out_path", str(o),
                "--temp_dir", str(Path(td, "tmp")),
            ],
            check=True,
            cwd="/opt/LatentSync",
            # This module must not be named `latentsync` (it would shadow the package);
            # pin the import root to the repo anyway.
            env={**os.environ, "PYTHONPATH": "/opt/LatentSync"},
        )
        return {
            "video": o.read_bytes(),
            "seconds": round(time.time() - t0, 1),
            "gpu": torch.cuda.get_device_name(0),
            "steps": inference_steps,
            "guidance_scale": guidance_scale,
        }


@app.local_entrypoint()
def main(video: str, audio: str, out: str, steps: int = 20, guidance: float = 1.5, gpu: str = GPU):
    import json

    res = lipsync.with_options(gpu=gpu).remote(Path(video).read_bytes(), Path(audio).read_bytes(), steps, guidance)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(res.pop("video"))
    print(json.dumps({"output_path": out, **res}))
