# Kandinsky 6.0 Lite — GPU benchmark (2026-10-14)

One 5 s clip = 121 frames @ 24 fps, 864×480, with native 44.1 kHz audio, seed 42.
Measured with `tools/gpu/modal_apps/kandinsky6.py` (Modal) and
`tools/gpu/kaggle_jobs/kandinsky6.py` (Kaggle). "gen" is the denoise + decode +
encode time inside a warm container; "load" is the one-time weight load from the
`openmontage-hf-cache` Volume per container.

Modal prices from modal.com/pricing on 2026-10-14: H100 $0.001097/s,
A100-40GB $0.000583/s, L40S $0.000542/s.

| Backend | Model (steps, CFG) | gen / clip | load / container | peak VRAM | GPU $ / clip |
|---|---|---|---|---|---|
| Modal H100 80GB | Lite-distill (16, 1.0) | 62–64 s | 33 s | 27.0 GiB | $0.069 |
| Modal L40S 48GB | Lite-distill (16, 1.0) | 114–115 s | 16 s | 27.0 GiB | **$0.062** |
| Modal A100-40GB | Lite-distill (16, 1.0) | 118–120 s | 37 s | 28.1 GiB | $0.069 |
| Modal H100 80GB | Lite (50, 5.0) | 322–323 s | 30 s | 27.0 GiB | $0.354 |
| Modal A100-40GB | Lite (50, 5.0) | 605–606 s | 24 s | 28.0 GiB | $0.353 |
| Modal L40S 48GB | Lite (50, 5.0) | 651–653 s | 24 s | 27.0 GiB | $0.354 |
| Kaggle 2×T4 (fp16) | Lite-distill (16, 1.0) | 1289 s | 77 s text enc + 38 s load + 128 s download | 8.6 GiB | $0 (quota) |

GPU $ excludes Modal CPU/RAM charges and the per-container load (amortized
over a batch: at 20 clips/container it adds < 1 %).

## Storage

`openmontage-hf-cache` holds both Lite and Lite-distill: **31.83 GiB** (the
16.6 GB Qwen2.5-VL text encoder and the VAEs are shared blobs). At
$0.09/GiB-month that is $2.86/month, inside Modal's 1 TiB/month free Volume
allowance, so $0 billed.

## Speech check (faster-whisper large-v3)

| Clip | Target line | Transcript |
|---|---|---|
| distill H100, English | "I never meant to lie to you." | "I never meant to lie to you." (auto-detected en, p=0.91) |
| distill H100, Kreyòl | "Kote ou te ye yè swa?" | forced ht: "Yon se ou te kete ou tou yeye swa." / auto: sw |
| Lite H100, Kreyòl | "Kote ou te ye yè swa?" | forced ht: "Ke te ote yo yeswa." / auto: fr |
| distill Kaggle T4, Kreyòl | "Kote ou te ye yè swa?" | forced ht: "Kete ou te yenye swa." / auto: fr |

English dialogue is produced verbatim. Haitian Creole is not: the native audio
track is unusable for Kreyòl lines, which need recorded dialogue + RVC +
LatentSync instead.
