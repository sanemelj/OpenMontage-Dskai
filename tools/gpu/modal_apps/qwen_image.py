"""Qwen-Image (Apache-2.0) on Modal: character/location/prop assets and keyframes.

- `QwenT2I`  — Qwen/Qwen-Image-2512: text -> image (new character sheets, sets, props).
- `QwenEdit` — Qwen/Qwen-Image-Edit-2511: 1–3 reference images + text -> image
               (same face in a new shot/set = continuity keyframes).

Weights live in the shared `openmontage-hf-cache` Volume.

    modal run tools/gpu/modal_apps/qwen_image.py::prefetch
    modal run tools/gpu/modal_apps/qwen_image.py --prompt "..." --out a.png [--refs face.png,set.png]
"""

import os
from pathlib import Path

import modal

APP_NAME = "openmontage-qwen-image"
T2I_MODEL = "Qwen/Qwen-Image-2512"
EDIT_MODEL = "Qwen/Qwen-Image-Edit-2511"
GPU = os.environ.get("QWEN_IMAGE_MODAL_GPU", "H100")

hf_cache = modal.Volume.from_name("openmontage-hf-cache", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.8.0",
        "torchvision==0.23.0",
        "transformers>=4.57",
        "accelerate",
        "sentencepiece",
        "pillow",
        "hf_transfer",
    )
    .pip_install("git+https://github.com/huggingface/diffusers.git")
    .env({"HF_HOME": "/cache/hf", "HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App(APP_NAME, image=image)

NEGATIVE = (
    "cartoon, illustration, 3d render, plastic skin, airbrushed, deformed hands, extra fingers, "
    "blurry, low quality, watermark, text, logo"
)


def _png(img) -> bytes:
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@app.cls(gpu=GPU, volumes={"/cache": hf_cache}, timeout=60 * 30, scaledown_window=120)
class QwenT2I:
    @modal.enter()
    def load(self) -> None:
        import torch
        from diffusers import QwenImagePipeline

        self.pipe = QwenImagePipeline.from_pretrained(T2I_MODEL, torch_dtype=torch.bfloat16).to("cuda")
        hf_cache.commit()

    @modal.method()
    def generate(self, prompt: str, width: int = 1328, height: int = 1328, seed: int = 42,
                 steps: int = 50, true_cfg_scale: float = 4.0, negative_prompt: str = NEGATIVE) -> dict:
        import time

        import torch

        t0 = time.time()
        img = self.pipe(
            prompt=prompt, negative_prompt=negative_prompt, width=width, height=height,
            num_inference_steps=steps, true_cfg_scale=true_cfg_scale,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        return {"image": _png(img), "seconds": round(time.time() - t0, 1), "seed": seed, "model": T2I_MODEL}


@app.cls(gpu=GPU, volumes={"/cache": hf_cache}, timeout=60 * 30, scaledown_window=120)
class QwenEdit:
    @modal.enter()
    def load(self) -> None:
        import torch
        from diffusers import QwenImageEditPlusPipeline

        self.pipe = QwenImageEditPlusPipeline.from_pretrained(EDIT_MODEL, torch_dtype=torch.bfloat16).to("cuda")
        hf_cache.commit()

    @modal.method()
    def generate(self, prompt: str, refs: list[bytes], seed: int = 42, steps: int = 40,
                 true_cfg_scale: float = 4.0, negative_prompt: str = NEGATIVE,
                 width: int | None = None, height: int | None = None) -> dict:
        import io
        import time

        import torch
        from PIL import Image

        images = [Image.open(io.BytesIO(b)).convert("RGB") for b in refs]
        t0 = time.time()
        img = self.pipe(
            image=images, prompt=prompt, negative_prompt=negative_prompt,
            num_inference_steps=steps, true_cfg_scale=true_cfg_scale, guidance_scale=1.0,
            width=width, height=height,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        return {"image": _png(img), "seconds": round(time.time() - t0, 1), "seed": seed, "model": EDIT_MODEL}


@app.function(volumes={"/cache": hf_cache}, timeout=60 * 60, cpu=4, memory=8192)
def prefetch() -> dict:
    from huggingface_hub import snapshot_download

    for repo in (T2I_MODEL, EDIT_MODEL):
        snapshot_download(repo)
    hf_cache.commit()
    return {"ok": True}


@app.local_entrypoint()
def main(prompt: str, out: str, refs: str = "", seed: int = 42, width: int = 1328, height: int = 1328,
         gpu: str = GPU):
    import json

    ref_paths = [r for r in refs.split(",") if r]
    if ref_paths:
        res = QwenEdit.with_options(gpu=gpu)().generate.remote(prompt, [Path(r).read_bytes() for r in ref_paths], seed)
    else:
        res = QwenT2I.with_options(gpu=gpu)().generate.remote(prompt, width, height, seed)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(res.pop("image"))
    print(json.dumps({"output_path": out, **res}))
