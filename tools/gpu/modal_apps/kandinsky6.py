"""Kandinsky 6.0 Video (text/image -> video + synchronized audio) on Modal.

Weights live in a persistent Modal Volume so they download once per workspace.

Smoke test (writes MP4s locally):
    modal run tools/gpu/modal_apps/kandinsky6.py --prompt "..." --out projects/x/assets/video/clip.mp4
"""

import os
from pathlib import Path

import modal

APP_NAME = "openmontage-kandinsky6"
DEFAULT_MODEL = "kandinskylab/Kandinsky-6.0-Lite-5s-Diffusers"
GPU = os.environ.get("KANDINSKY6_MODAL_GPU", "L40S")

hf_cache = modal.Volume.from_name("openmontage-hf-cache", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch==2.8.0",
        "transformers>=4.57",
        "accelerate",
        "sentencepiece",
        "av",
        "imageio[ffmpeg]",
        "pillow",
        "hf_transfer",
    )
    # Kandinsky6TI2VAPipeline currently ships only on diffusers main.
    .pip_install("git+https://github.com/huggingface/diffusers.git")
    .env({"HF_HOME": "/cache/hf", "HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App(APP_NAME, image=image)


@app.cls(gpu=GPU, volumes={"/cache": hf_cache}, timeout=60 * 30, scaledown_window=120)
class Kandinsky6:
    model_id: str = modal.parameter(default=DEFAULT_MODEL)

    @modal.enter()
    def load(self) -> None:
        import torch
        from diffusers import Kandinsky6TI2VAPipeline

        self.pipe = Kandinsky6TI2VAPipeline.from_pretrained(self.model_id, torch_dtype=torch.bfloat16)
        self.pipe.to("cuda")
        self.pipe.vae.enable_tiling()
        hf_cache.commit()

    @modal.method()
    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        image_bytes: bytes | None = None,
        width: int = 864,
        height: int = 480,
        num_frames: int = 121,
        fps: float = 24.0,
        num_inference_steps: int | None = None,
        guidance_scale: float | None = None,
        seed: int = 42,
        sample_audio: bool = True,
    ) -> dict:
        import io
        import tempfile
        import time

        import torch
        from diffusers.utils import encode_video
        from PIL import Image

        distilled = "distill" in self.model_id
        steps = num_inference_steps or (16 if distilled else 50)
        cfg = 1.0 if distilled else (guidance_scale if guidance_scale is not None else 5.0)

        kwargs = {}
        if image_bytes:
            kwargs["image"] = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        t0 = time.time()
        out = self.pipe(
            prompt=prompt,
            height=height,
            width=width,
            num_frames=num_frames,
            frame_rate=fps,
            num_inference_steps=steps,
            guidance_scale=cfg,
            sample_audio=sample_audio,
            generator=torch.Generator("cuda").manual_seed(seed),
            **kwargs,
        )
        gen_s = time.time() - t0

        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            audio_kw = {}
            if sample_audio and out.audio is not None:
                audio_kw = {"audio": out.audio[0][None], "audio_sample_rate": self.pipe.audio_sample_rate}
            encode_video(out.frames[0], fps=int(fps), output_path=f.name, **audio_kw)
            data = Path(f.name).read_bytes()

        return {
            "video": data,
            "model": self.model_id,
            "steps": steps,
            "guidance_scale": cfg,
            "seed": seed,
            "generation_seconds": round(gen_s, 1),
            "gpu": GPU,
        }


@app.local_entrypoint()
def main(
    prompt: str,
    out: str,
    model: str = DEFAULT_MODEL,
    image: str = "",
    seed: int = 42,
    steps: int = 0,
    width: int = 864,
    height: int = 480,
):
    import json

    image_bytes = Path(image).read_bytes() if image else None
    res = Kandinsky6(model_id=model).generate.remote(
        prompt=prompt,
        image_bytes=image_bytes,
        seed=seed,
        num_inference_steps=steps or None,
        width=width,
        height=height,
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(res.pop("video"))
    print(json.dumps({"output_path": out, **res}))
