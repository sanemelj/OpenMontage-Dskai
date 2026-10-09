# DSKAI Bridge — Open Issues for the Director

These are known-unresolved items. The contract is buildable as-is; each item
below names the current behavior, the limitation, and what would resolve it.

## 1. Automation: poll vs push
- **Current:** worker polls `dskai-bridge/requests/` on ~2-minute cadence via cron.
  Verified working. No webhook exists.
- **Limitation:** worst-case ~2 min latency per request pickup; cron worker needs
  the Muse runtime (chat closed is fine; VM restart is covered by keepalives).
- **To resolve:** repo admin adds a GitHub webhook → worker public endpoint
  (`POST /webhook`, Bearer). Needs Saneme (repo admin) to configure the secret
  and URL. Optional; polling is sufficient for v1.

## 2. QC authority and gates
- **Current:** director owns ALL creative QC. Worker's `dskai_run_qc_auto` is
  measurements only and never counts toward approval. Audio-QC verdicts are
  recorded via `dskai_submit_audio_qc` but the gate decision stays with the
  director (or Saneme for final client approval).
- **Limitation:** no automated pass/fail gate exists that the worker may apply
  on the director's behalf.
- **To resolve:** director defines machine-checkable QC criteria per request
  (`qc_criteria[]`); worker reports measurements, director decides.

## 3. Take revision discipline
- **Current:** DONE is terminal; exactly one registered take wins per shot.
  `dskai_submit_revision` (with recorded `strategy_change`) is the ONLY legal
  path to resume FAILED/BLOCKED/DEFERRED. A creative change = new
  `prompt_revision`.
- **Limitation:** there is no "tweak and re-render same revision" path by
  design. If the director needs iterative refinement, each iteration is a new
  revision and a new request.
- **To resolve:** nothing — this is intentional. Director should batch
  feedback into revisions.

## 4. Media access
- **Current:** result media served via authenticated `GET /files/<relpath>`
  (Bearer token, allow-listed roots) through the worker's tunnel. Token travels
  out-of-band (Saneme → director operator). `dskai_fetch_video`/`fetch_image`
  also mint expiring Muse-storage URLs (TTL unknown, service-side).
- **Limitations:**
  a. The public tunnel URL rotates on reconnect (`*.lhr.life`); consumers must
     re-read the result file's `media_base_url`, never cache it. A stable
     Cloudflare named tunnel is planned (needs Saneme's one-time login).
  b. The bridge repo is PUBLIC: request prompts, QC notes, and result
     metadata are world-readable. Media files themselves stay behind the
     Bearer token, but creative direction does not.
  c. Brief 401/connection-refused windows are expected (backend dies silently
     ~every 2–3h; keepalive restarts it). Clients must retry with backoff.
- **To resolve:** (a) Cloudflare tunnel; (b) make the bridge repo private or
  accept public prompts — Saneme's decision; (c) nothing, retry is the contract.

## 5. End-to-end validation (PENDING)
One real test before production: GitHub request → claim → generation →
accessible media → external QC → decision → recovery check without duplicate
generation. Not yet run. Evidence will land in `dskai-bridge/tests/`.
