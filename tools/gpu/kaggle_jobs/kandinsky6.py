"""Kandinsky 6.0 Video (video + synchronized audio) as a Kaggle batch job.

Runs inside a Kaggle kernel. Kaggle uploads only the code file, so the launcher
prepends a ``JOB_INLINE = {...}`` line with the job parameters. Outputs land in
/kaggle/working/.

Memory plan for 2x T4 (15 GB each, no bf16 tensor cores):
  stage A: Qwen2.5-VL text encoder (16.6 GB) sharded over both GPUs ->
           prompt embeddings + padding mask, then freed.
  stage B: transformer/VAEs with model CPU offload on cuda:0. Pre-Ampere GPUs
           run the transformer in fp16 so SDPA gets the memory-efficient
           kernel; bf16 there falls back to the O(N^2) math kernel and OOMs.
"""

import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("/kaggle/working")
JOB = globals().get("JOB_INLINE") or {}


def log(msg):
    print(f"[k6 {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd):
    log(f"$ {cmd}")
    subprocess.run(cmd, shell=True, check=True)


# Kaggle's preinstalled torchao is too old for diffusers main (FqnToConfig import);
# diffusers only needs it for torchao quantization, which this job does not use.
sh(f"{sys.executable} -m pip uninstall -y -q torchao")
sh(
    f"{sys.executable} -m pip install -q -U 'transformers>=4.57' accelerate sentencepiece av hf_transfer "
    "git+https://github.com/huggingface/diffusers.git"
)

os.environ.setdefault("HF_HOME", "/tmp/hf")
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

import torch  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402

MODEL = JOB.get("model", "kandinskylab/Kandinsky-6.0-Lite-distill-5s-Diffusers")
CLIPS = JOB.get("clips") or [{"name": "test", "prompt": "A cinematic shot of the ocean at dusk."}]
W, H = JOB.get("width", 864), JOB.get("height", 480)
FRAMES, FPS = JOB.get("num_frames", 121), JOB.get("fps", 24)
DISTILLED = "distill" in MODEL
STEPS = JOB.get("steps") or (16 if DISTILLED else 50)
CFG = 1.0 if DISTILLED else JOB.get("guidance_scale", 5.0)

n_gpu = torch.cuda.device_count()
cap = torch.cuda.get_device_capability(0)
DIT_DTYPE = torch.bfloat16 if cap[0] >= 8 else torch.float16
TE_DTYPE = torch.bfloat16
log(f"GPUs={n_gpu} {torch.cuda.get_device_name(0)} sm{cap[0]}{cap[1]} dit_dtype={DIT_DTYPE} model={MODEL}")

t0 = time.time()
path = snapshot_download(MODEL)
log(f"downloaded in {time.time() - t0:.0f}s")

from diffusers import Kandinsky6TI2VAPipeline  # noqa: E402
from transformers import AutoProcessor, CLIPTextModel, CLIPTokenizer, Qwen2_5_VLForConditionalGeneration  # noqa: E402

# ---------- stage A: prompt embeddings ----------
t0 = time.time()
max_mem = {i: "14GiB" for i in range(n_gpu)}
te = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    path, subfolder="text_encoder", torch_dtype=TE_DTYPE, device_map="auto", max_memory=max_mem
)
tok = AutoProcessor.from_pretrained(path, subfolder="tokenizer")
te2 = CLIPTextModel.from_pretrained(path, subfolder="text_encoder_2", torch_dtype=TE_DTYPE).to("cuda:0")
tok2 = CLIPTokenizer.from_pretrained(path, subfolder="tokenizer_2")

embeds = {}
with torch.no_grad():
    for clip in CLIPS:
        pe, pooled, mask = Kandinsky6TI2VAPipeline._get_prompt_embeds(
            [clip["prompt"]], tok, te, tok2, te2, 1024, torch.device("cuda:0")
        )
        if not torch.isfinite(pe).all():
            raise RuntimeError("non-finite prompt embeddings")
        embeds[clip["name"]] = (pe.cpu(), pooled.cpu(), None if mask is None else mask.cpu())
del te, te2
gc.collect()
torch.cuda.empty_cache()
log(f"stage A (text encoding, {len(CLIPS)} prompts) {time.time() - t0:.0f}s")

# ---------- stage B: generation ----------
t0 = time.time()
pipe = Kandinsky6TI2VAPipeline.from_pretrained(
    path, text_encoder=None, tokenizer=None, text_encoder_2=None, tokenizer_2=None, torch_dtype=DIT_DTYPE
)
pipe.enable_model_cpu_offload(gpu_id=0)
pipe.vae.enable_tiling()
log(f"stage B load {time.time() - t0:.0f}s")

from diffusers.utils import encode_video  # noqa: E402

results = []
for clip in CLIPS:
    pe, pooled, mask = embeds[clip["name"]]
    cached = (
        pe.to("cuda:0", DIT_DTYPE),
        pooled.to("cuda:0", DIT_DTYPE),
        None if mask is None else mask.to("cuda:0"),
        None,
        None,
        None,
    )
    # __call__ has no prompt_attention_mask argument, so feed the cached
    # (embeds, pooled, mask) tuple through encode_prompt to keep the padding mask.
    pipe.encode_prompt = lambda *a, _c=cached, **k: _c

    kw = {}
    if clip.get("image"):
        from PIL import Image

        kw["image"] = Image.open(clip["image"]).convert("RGB")

    seed = clip.get("seed", 42)
    t1 = time.time()
    torch.cuda.reset_peak_memory_stats()
    out = pipe(
        prompt=clip["prompt"],
        height=clip.get("height", H),
        width=clip.get("width", W),
        num_frames=clip.get("num_frames", FRAMES),
        frame_rate=FPS,
        num_inference_steps=STEPS,
        guidance_scale=CFG,
        generator=torch.Generator("cpu").manual_seed(seed),
        **kw,
    )
    gen_s = time.time() - t1
    dst = WORK / f"{clip['name']}.mp4"
    audio_kw = {}
    if out.audio is not None:
        audio_kw = {"audio": out.audio[0][None], "audio_sample_rate": pipe.audio_sample_rate}
    encode_video(out.frames[0], fps=FPS, output_path=str(dst), **audio_kw)
    peak = torch.cuda.max_memory_allocated(0) / 2**30
    log(f"{clip['name']}: {gen_s:.0f}s, peak {peak:.1f} GiB -> {dst}")
    results.append(
        {
            "name": clip["name"],
            "file": dst.name,
            "seed": seed,
            "generation_seconds": round(gen_s, 1),
            "peak_vram_gib": round(peak, 2),
        }
    )

(WORK / "results.json").write_text(
    json.dumps(
        {
            "model": MODEL,
            "gpu": torch.cuda.get_device_name(0),
            "gpu_count": n_gpu,
            "dit_dtype": str(DIT_DTYPE),
            "steps": STEPS,
            "guidance_scale": CFG,
            "width": W,
            "height": H,
            "num_frames": FRAMES,
            "clips": results,
        },
        indent=2,
    )
)
log("done")
