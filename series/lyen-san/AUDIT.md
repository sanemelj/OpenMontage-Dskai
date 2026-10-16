# LYEN SAN — Odit pwodiksyon (Sezon 1)

> **PLAN 2 (2026-10-14, aktif):** Kandinsky rejte pou dyalòg Kreyòl ak aksyon. Tout plan videyo yo fèt ak **Veo 3.1 Lite** (Gemini API), depi keyframe Qwen sou Modal.
> - **Ritm:** 4 epizòd/mwa. Nou pwodui 8 anvan, epi nou pibliye youn chak 4–5 jou.
> - **Pran:** 1 pran pa plan; nou refè sèlman plan ki pa bon (~20–30% plan, sa ki entegre nan pri a).
> - **Veo Lite 720p** ($0.05/s): ~$110–130/mwa. Upscale 1080p sou Modal. (1080p dirèk = $0.08/s ≈ $190/mwa.)
> - **Modal** (keyframe + upscale + stokaj): ~$25–32/mwa, kouvri pa $30 kredi gratis la.
> - **Apre sezon an:** konpilasyon fim konplè (~1h30) + Shorts/Reels/TikTok ak kwòk yo.
> - Seksyon 2–4 anba yo se **plan 1 (Kandinsky)**, kenbe kòm referans.


Dat: 2026-10-14. Chif ki **mezire** yo soti nan `docs/gpu-benchmarks/`. Chif ki make **estimasyon** poko teste.

## 1. Gwosè sezon an
| | Valè |
|---|---|
| Epizòd | **12** |
| Dire pa epizòd | ~8 min |
| Total sezon | ~96 min (menm longè ak yon fim long) |
| Plan pa epizòd | ~115 (plan 3–5 s, jan aksyon/dram koupe) |
| Plan total | ~1 380 |

**Poukisa 12:** 3 ak 4 epizòd chak, yon gwo vire nan mitan sezon an (Ep 6), epi yon final ki fèmen istwa manman an men ki louvri Sezon 2. Pi kout pase sa, rezo mafya a pa gen tan devlope. Pi long pase sa, pri a ak kontinite a vin twò lou.

## 2. Pri pa epizòd
| Etap | Kantite | Pri inite | Total | Estati |
|---|---|---|---|---|
| Klip videyo (Kandinsky Lite-distill, L40S) | 115 plan × **2.5 pran** = ~290 | $0.062 | **~$18.00** | pri **mezire**, kantite pran se estimasyon |
| Keyframe (Qwen-Image-Edit, kontinite) | ~230 imaj | ~$0.01 | ~$2.50 | estimasyon |
| Upscale 1080p (Kandinsky VSR) | 115 plan | ~$0.03 | ~$3.50 | estimasyon |
| **Total** | | | **~$24 / epizòd** | |

Yon sèl fwa: bib asset (8 pèsonaj, ~10 andwa, akseswa) + tès ≈ **$15**.

## 3. Bidjè $100–150/mwa → konbyen tan
| Senaryo | Kalkil (Modal) | Epizòd/mwa |
|---|---|---|
| $100 + $30 kredi gratis Modal = $130 | 130 ÷ 24 | **~5** |
| $150 + $30 kredi gratis Modal = $180 | 180 ÷ 24 | **~7** |

Kaggle (gratis, ~360 klip/mwa, men lan: ~21 min/klip) pran yon pati nan repran yo. Sa bay plis maj ankò.

**Kalandriye pwopoze:**
| Peryòd | Travay |
|---|---|
| Semèn 1–2 | Tès obligatwa (§4) + bib asset (pèsonaj, andwa, akseswa) |
| Mwa 1 | Ep 1–4 (nou pwodui 4 epizòd **anvan** nou pibliye premye a) |
| Mwa 2 | Ep 5–8 · piblikasyon Ep 1–4 (1 pa semèn) |
| Mwa 3 | Ep 9–12 · piblikasyon Ep 5–8 |
| Mwa 4 | Piblikasyon Ep 9–12 · ekriti Sezon 2 |

**Rezilta: sezon 1 = ~3 mwa pwodiksyon, ~4 mwa piblikasyon**, ak yon epizòd chak semèn.

> Mete **spend limit Modal** sou $150 (Settings → Usage & Billing) pou bidjè a pa janm depase.

## 4. Risk — tès obligatwa anvan pwodiksyon (~$5)
| # | Risk | Tès | Si l echwe |
|---|---|---|---|
| 1 | **Aksyon** (kout pwen, zam k ap tire) ka sanble fo ak Kandinsky Lite | 10 plan aksyon Ep 1, Sèn 2 | Plan pi kout, plis reyaksyon/detay; tès Kandinsky **Pro** sou H100 |
| 2 | **To siksè Kreyòl** pa seed (nou gen 1 sèl apwouve pou kounye a) | 10 replik Ep 1 × 2 seed, ou koute yo | Plis pran pa replik; bidjè a ka monte |
| 3 | **Menm figi** chak plan (image→video depi keyframe) | Sarah nan 5 plan diferan | Ajiste pwonmt / referans, oswa tès lòt modèl imaj |
| 4 | **Rezolisyon** 864×480 twò ba pou "premium" | Upscale 1080p sou 3 plan | Kandinsky Pro oswa plis rezolisyon (koute plis) |
| 5 | **Vrè andwa** (Sitadèl, Jakmèl) pa rekonèt | Image→video depi foto referans CC | Plis plan etabli ak foto, mwens plan jenere |

**Opinyon m:** risk #1 (aksyon) ak #4 (kalite 1080p) se de pi gwo yo pou yon nivo "Netflix". Nou dwe teste yo **anvan** nou jenere asset yo.

## 5. Kote medya yo sere
Videyo, keyframe ak montaj yo **pa nan git** (yo twò gwo). Yo sou Modal Volume **`lyen-san-media`** (workspace `dskovasas`):
- Gade/telechaje: modal.com → Storage → Volumes → `lyen-san-media`
- CLI: `modal volume get lyen-san-media /ep01 ./ep01`
