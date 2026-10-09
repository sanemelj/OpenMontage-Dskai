# DSKAI STUDIO — Director/Worker Integration

> **Status (2026-10-09):** Contract v1.0.0 is VERIFIED against the live backend.
> **Implementation: PENDING** — bridge dirs, poll worker, and media endpoint
> wiring are specified but not yet deployed.
> **End-to-end validation: PENDING** — one real GitHub-request → claim →
> generation → media → QC → decision → recovery test, not yet run.

How an external director (Codex / Claude Code, using OpenMontage skills) drives video production through the Muse-side worker (Kai) and the existing DSKAI STUDIO / media-pipeline backend.

The machine-readable source of truth is `contract/dskai-contract.json`. This document is the human companion.

## Architecture

```
Director (Codex/Claude Code)          GitHub bridge                     Worker (Kai, inside Muse)
  OpenMontage skills                    sanemelj/OpenMontage-Dskai
  shot plan                       -->   dskai-bridge/requests/*.json  -->  poll (2 min) -> claim
  QC verdict                      <--   dskai-bridge/results/*.json  <--  execute via DSKAI backend
  watches media                   <--   https://<tunnel>/media/...  <--  upload/serve result
```

- **GitHub** carries versioned instructions and results. It is the system of record for what was asked and what was delivered.
- **The backend** (DSKAI MCP tools over the authenticated tunnel) carries frequent live status. The director may also query it directly with the Bearer token.
- **Media** is served by the worker over authenticated HTTPS (`GET /media/...`, same Bearer token). URLs are tunnel-bound: always re-read the result file for the current `media_base_url`; never cache it.

## Request lifecycle

1. Director writes `dskai-bridge/requests/<request_id>.json` (schema: contract `request_schema`), commits, pushes.
2. Worker polls every ~2 minutes, validates the request. Invalid requests get a `results/<id>.json` with `status: BLOCKED` and a precise error — never silently dropped.
3. Worker writes `dskai-bridge/claims/<request_id>.json` (worker_id, lease). One worker: claims are idempotent by `request_id`.
4. Worker executes through the DSKAI backend (submit → render → take), updating `results/<id>.json` through `QUEUED → CLAIMED → RENDERING → DONE/FAILED/BLOCKED`.
5. Director QCs the actual media and returns the verdict. A creative change = new `prompt_revision`, never a silent regeneration.

## Continuity

- `dependencies[].continuity: "independent"` → shots may render in parallel.
- `"continuous_action"` → the worker waits for the predecessor's `DONE`, extracts the real endframe of the selected take at `cut_point_sec`, and feeds it as `start_frame` **only if the backend supports it**; otherwise `BLOCKED` with the exact constraint.
- If a predecessor's selected take changes, the worker flags every dependent request instead of continuing silently.

## What the worker will NOT do

- Rewrite prompts or dialogue. Ever.
- Regenerate an accepted take. A new look needs a new `prompt_revision`.
- Claim concatenation guarantees continuity. It returns real media; continuity is the director's verdict.
- Purchase credits, publish content, delete canonical work, or mark anything CLIENT_APPROVED.
- Put credentials in the repo. The Bearer token travels out-of-band.

## Authentication

- MCP/backend + media: `Authorization: Bearer <token>`. Token lives outside the repo (Saneme → director operator).
- GitHub: the worker uses its own GitHub access to read requests and write claims/results.

## Current backend access (2026-10-09)

- ChatGPT connector: OpenAI tunnel (stable URL, ChatGPT-protocol only).
- Claude/generic MCP: `https://<current>.lhr.life/mcp` (rotates; current value tracked by the worker).
- A permanent Cloudflare named tunnel is planned to replace the rotating URL (needs Saneme's one-time Cloudflare login).

## Capability notes (verified by operation, 2026-10-09)

- **Tools:** 46 MCP tools. Director-facing include submit/prepare/launch/execute, revision (only legal resume path for FAILED/BLOCKED/DEFERRED, requires recorded strategy change), correction, export (1080p, −16 LUFS), fetch results/video/image, job status (rich states), manifest read/diff, timeline EDL (trim/split/concat via ffmpeg), QC auto + audio QC verdicts, voice registry (every voice change resets approval), character share/build, record decision (append-only approve/reject), health. (`REMOTE_AUTH.md`'s "17 tools" is stale.)
- **Job states:** PENDING → QUEUED → CLAIMED → RENDERING → DONE (terminal, never regenerated). HELD: FAILED/BLOCKED/DEFERRED. Extra: WAITING_ON_DEPENDENCY, ON_HOLD. Claims are atomic under file lock with 30-min stale-takeover and heartbeats (`job-renew`).
- **No cancellation op exists.** To stop a queued job: mark DEFERRED/BLOCKED or supersede with a new `prompt_revision`.
- **Generation inputs (measured):** start frame PARTIAL (image reference guides first frame, no true param); end frame UNSUPPORTED; multi-reference YES (stills only); dialogue/audio YES native (AAC); duration ≤10s per generation (chain for longer); aspect ratio NO param (native 1152×768); no billing API (count ledger only).
- **Post ops:** take selection = exactly-one registered take; frame extraction via ffmpeg (no dedicated tool); trimming via timeline EDL; no dedicated audio-edit tool; export assembles approved shots.
- **Storage:** local disk only (~477 MB across 9 canonical projects), no expiry, no replication. External retrieval: `GET /files/<relpath>` (Bearer, allow-listed) or expiring fetch URLs (TTL unknown). Never expose `/home/hatch/...` paths.
- **Scheduler/workers:** pollers exist but auto-poller/runner/dashboard-sync are disabled by standing order; rendering happens only inside a Muse session. Concurrent-render capacity unknown — design serial. Keepalives (endpoint, OpenAI tunnel, SSH tunnel) auto-recover after VM restart; no manual restart needed for enabled paths.
- **Reliability:** expect brief 401/connection-refused windows (server dies silently ~every 2–3h, cause unproven, not OOM) — clients must retry with backoff. SSH tunnel URL rotates per reconnect (Cloudflare named tunnel planned for stability).

## Validation

One real end-to-end test before production: GitHub request → claim → generation → accessible media → external QC → decision back to DSKAI → recovery check without duplicate generation. Evidence is recorded under `dskai-bridge/tests/`.
