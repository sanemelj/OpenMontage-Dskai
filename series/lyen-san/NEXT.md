# LYEN SAN — Kote nou ye / Pwochen etap (handoff ant sesyon)

**Dènye mizajou:** 2026-10-15

## NOUVO (2026-10-15): Google Flow sou laptop la
- **DESIZYON: pou kounye a SÈLMAN Google Flow.** Pa itilize Modal (GPU), Kaggle, ni rann 2D/3D sou CPU. Pa lanse okenn jenerasyon Qwen/Kandinsky.
- Videyo yo ap fèt nan **Google Flow** (Veo 3.1 Lite, 720p, apre sa upscale), pa nan API a: kredi Flow koute 2–4 fwa mwens.
  - Lite = 10 kredi/klip 8 s sou Pro (5 kredi sou Ultra). Imaj Nano Banana yo gratis → keyframe yo fèt nan Flow, pa sou Modal.
  - Plan: Pro + 50 kredi gratis chak jou + top-up 2,500 kredi ($25, valab 12 mwa). Ultra 5x sèlman si nou fè ~1 epizòd chak jou (~2,250 klip/mwa).
- **MCP Flow** enstale sou laptop HP (Windows) itilizatè a: `Documents\mcp-google-flow`, vèsyon `403639e` (kòd la revize: li pale sèlman ak flow.google.com ak Chrome lokal).
  - Non MCP a: `google-flow`. Bidjè tès: `FLOW_MCP_MAX_CREDITS=20`. Klip yo telechaje nan `FlowStudio\output`.
  - Chak jenerasyon peye: premye apèl la bay yon pri (quote), dezyèm apèl la ak `confirm: true` depanse kredi yo. Toujou montre pri a bay itilizatè a.
- **Kreyòl nan Flow/Veo:** ekri l nòmalman. Règ fonetik BIBLE §8 yo PA aplike ak Veo.
- Itilizatè a pa konn kòd: eksplike an Kreyòl senp, yon etap alafwa, epi fè travay teknik yo pou li.
- Piblikasyon: fini *Lanmou & Soupson* anvan, epi lanse LYEN SAN apre (teaser nan dènye epizòd la). Kenbe 8+ epizòd LYEN SAN pare anvan premye a soti.

## Desizyon ki deja pran
- **Plan 2:** tout plan videyo yo ap fèt ak **Veo 3.1 Lite** (Gemini API, 720p $0.05/s, upscale 1080p sou Modal). Gade `AUDIT.md`.
- **Kandinsky 6 rejte:** Kreyòl la pa bon (natif oswa ak LatentSync), epi aksyon an twò lan ak pa reyalis.
- **Dyalòg:** natif nan videyo a. Ak **Flow/Veo**: ekri Kreyòl nòmal (pa règ fonetik, kontraksyon yo pèmèt). Règ fonetik `BIBLE.md` §8 yo te pou Kandinsky sèlman.
- **Keyframe:** Qwen-Image-2512 / Edit-2511 sou Modal (`tools/gpu/modal_apps/qwen_image.py`).
  - Pa plis pase 1–2 GPU an menm tan: 8 GPU an paralèl te triple pri a (~$0.12/imaj).
  - Kenbe moman **anvan** aksyon an nan keyframe a.
  - Dekri andwa a an tèks (`sets` nan shots JSON), pa ak imaj referans.
- **Kasting:** pèsonaj yo bèl, po fonse pa janm eklèsi (`LOOKBOOK.md` §5b).
- **Andwa:** chwazi selon kontèks la (bèl Ayiti tou, pa sèlman kote ki pòv).
- **Ritm:** 4 epizòd/mwa; pwodui 8 anvan, pibliye youn chak 4–5 jou; konpilasyon apre.
- **Bidjè:** $100–150/mwa.
  - Modal: kenbe l anba $30 kredi gratis la.
  - Gemini: prepay minimòm $30 (kredi $300 Google Cloud la pa valab pou Gemini API).

## Asset ki apwouve
- Sarah: `assets/characters/sarah/sarah_ref_sheet.png` (seed 303) + `sarah_tactical_s1.png`
- Ep 1 Sèn 1–4: tout pèsonaj s1, `delmas_street_night_v2`, koridò/chanm (dekri an tèks), braslè N.V.
- Keyframe Ep 1 Sèn 1–4 (33): sou Modal Volume `lyen-san-media:/ep01/keyframes`. Grid la: `episodes/ep01_sc01-04_keyframes.jpg`.

## Opsyon kredi $300 Google Cloud (Vertex AI)
Kredi $300 la pa valab pou AI Studio, men li ka valab pou Veo sou **Vertex AI**. Sa poko konfime: fè 1 jenerasyon tès, epi tcheke Billing → Reports.
- Varyab anviwònman: `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=us-central1`, `GOOGLE_SERVICE_ACCOUNT_JSON` (kontni JSON kle service account la, wòl "Vertex AI User").
- `tools/google_credentials.py` ekri JSON sa a nan yon fichye prive, epi li mete `GOOGLE_APPLICATION_CREDENTIALS`.

## Pwochen etap (nouvo sesyon ak `GEMINI_API_KEY` oswa Vertex)
1. Verifye kle a: `GET https://generativelanguage.googleapis.com/v1beta/models`.
2. **Tès Veo 3.1 Lite (~$3–4):**
   - 4 plan aksyon (2.4, 2.5, 2.7, 2.11) ak 8 replik Kreyòl (1.4, 1.5, 2.14, 3.3, 3.4, 3.6, 4.4, 4.5), depi keyframe yo.
   - Keyframe aksyon yo dwe refè pou montre moman **anvan** aksyon an.
   - Teste tou **reference images** (san keyframe) pou kontinite pèsonaj.
   - Konpare 720p + upscale ak 1080p dirèk sou 1 plan.
   - Zouti ki la deja: `tools/video/veo_video.py` (li `GEMINI_API_KEY`).
3. Voye rezilta yo an **MP3 + MP4 48 kHz H.264 Main**. App telefòn itilizatè a pa jwe son kèk MP4.
4. Si tès la bon: storyboard Ep 1 konplè → keyframe → Veo → montaj → upscale.

## Kote bagay yo ye
- Kòd: branch `series/lyen-san` (PR #4); zouti GPU yo nan branch `feat/modal-kandinsky6` (PR #3), yo fusionnen nan `series/lyen-san`.
- Medya: Modal Volume `lyen-san-media` (`modal volume get lyen-san-media /ep01 ./ep01`).
- Pa janm mete medya nan git (twò gwo); se sèlman asset referans yo ki ladan l.
