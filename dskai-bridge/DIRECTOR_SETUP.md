# Director bridge — setup and limits

Director-side implementation of protocol v2; Kai's compatible Muse adapter is still required.
The original v1 handoff is preserved unchanged. No generation provider, persistent model runtime,
public deployment or paid service is introduced.

## Installation

Use Python 3.11+ and a virtual environment. From the repository root:

    python -m pip install -r dskai_bridge/requirements.txt
    python -m pip install pyyaml watchfiles Pillow
    python -m unittest dskai_bridge.test_bridge -v

The bridge does not import production providers or run registry discovery. General discovery
recursively imports dependencies; its reported PostHog source and installed-version opt-out
remain unverified because this session's local process launcher fails before execution.

Configure these server-side environment variables using private secret/service configuration,
never committed files or public logs:

| Variable | Purpose |
|---|---|
| DSKAI_STATE_DIR | Absolute private directory outside repo for SQLite and media cache |
| DSKAI_DIRECTOR_CREDENTIAL | Random unique 24+ character director credential |
| DSKAI_CLIENT_CREDENTIAL | Separate random client credential, held by the user |
| DSKAI_WORKER_CREDENTIAL | Separate ingestion credential for Kai |
| DSKAI_STUDIO_ORIGIN | Exact origin; local development http://127.0.0.1:4751 |
| DSKAI_GITHUB_REPO | Approved private operational repository owner/name |
| DSKAI_GITHUB_BRANCH | Explicit operational branch, no implicit main |
| DSKAI_GITHUB_TOKEN | Scoped server-only contents read/write credential |
| DSKAI_ALLOWED_MEDIA_ORIGINS | Comma-separated exact authorized HTTPS origins |

This code repository is public. The transport rejects a public operational repository to avoid
publishing private prompts/dialogue/notes. No repository was created or visibility changed.
A public fork may require a separate private operational repository; do not assume it can be
made private in place. The user must authorize that channel.

Privately create STATE_DIR/connection.json with keys "origin" and "token" (Muse Bearer).
Origin must be HTTPS, contain no path/query/userinfo, and match the configured allowlist.
Protect directory, credentials and backups with restrictive OS permissions.
When the tunnel changes, securely update this file and allowed origins; the connection file is
reread on uncached retrieval. Do not trust arbitrary result URLs or forward credentials to them.

    python -m dskai_bridge serve

Open /studio/login at the local origin. Existing Backlot boards remain at / and /p/... under
the same authentication boundary; new studio controls live at /studio. The CLI binds loopback.
For phone/remote use, an operator must configure an authorized HTTPS reverse proxy and matching
origin. No tunnel/public deployment is performed. Do not also expose the original unauthenticated
Backlot server externally.

    python -m dskai_bridge sync-once
    python -m dskai_bridge sync-watch

The explicit sync process polls at 15 seconds, backing off network/server/rate-limit errors to
120 seconds. Authentication, contract and configuration failures halt it with a durable blocker.
No service/supervisor is installed. Post-chat/reboot operation needs a supervised process and
the same state directory. No API model is started; an inspection inbox is not an active director.

## Contracts and controls

dskai_bridge/models.py is the executable strict protocol. Export JSON schemas:

    python -m dskai_bridge schema

Version 2 is a director-side proposal awaiting Kai agreement; no automatic v1 translation.
Unknown fields fail validation. Duration is >0 and <=10 seconds; no exact start/end-frame,
audio-reference or generation aspect parameter is accepted. delivery_framing is editorial intent.

Requests pin UUID request/take, project/chapter/scene/shot, monotonic prompt/take versions,
unchanged prompt/dialogue, full scene locks, visual storyboard, references, relationship and QC
criteria. Corrections use new IDs plus supersedes and strategy_change. Canonical digest is
SHA-256 of validated model JSON, with defaults, sorted keys and compact separators.

Claims/results/decisions bind full identity and request digest. Backend job and fence must
match. DONE is immutable. Media has UUID/version/checksum/size/MIME/relative path. QC additionally
pins video hash; client verdict pins selection revision. Director ACCEPT and client approval
are separate records. GitHub delivery is not backend application: a matching worker Ack is required.

- POST /studio/api/requests — director, ShotRequest.
- POST /studio/api/decisions/qc|selection|control|continuity — director.
- POST /studio/api/decisions/approval — client only.
- POST /studio/api/worker/claims|results|acks — worker only.
- GET /studio/api/state — state/history/flags/synchronization.
- GET /studio/api/events?after=N — durable ordered events, 100 per page; persist last seq.
- POST /studio/api/qc-tasks/claim?owner=NAME — atomic director inspection lease.
- POST /studio/api/qc-tasks/renew or /ack — request_id, owner, fence; renew before 120s expiry.
  Ack requires a persisted QC verdict. These leases never lease rendering.
- GET/HEAD /studio/media/{asset_id}/{version} — authenticated playback and seeking.

Browser sessions use HttpOnly SameSite=Strict cookies, expiry and CSRF tokens. API callers use
role-specific Bearer credentials. Worker credentials cannot browse or approve. Upstream Muse
and GitHub credentials never enter frontend bundles. This is single-owner role separation,
not multi-tenant per-project ACLs.

## Media, continuity and storage

Use upstream /files/<allowlisted-relpath>, as the audited handoff specifies; /media in its diagram
is inconsistent. There is no silent endpoint fallback. /studio/media is the browser-facing route.
Kai must verify /files live in the acceptance test.

The first playback downloads the entire asset, verifies size/hash, then serves byte ranges from
private local cache. Range works even if Muse lacks it, but first playback waits for full retrieval.
Redirects are not followed; 401/403 is authentication failure, not transient network retry.
Cached hashes are rechecked. A single asset is capped at 1 GB; aggregate cache quota/retention
is not automated. Cache is not replicated backup and does not prove independent durability.

Continuous dependencies identify selected predecessor take/media/selection revision, last
INCLUDED frame with rational timebase, and extracted reference checksum. Conditioning is still
image guidance, never exact frame control. A changed selection/cut flags dependent work.
ContinuityReview records actual viewing against current selections and can resolve a flag
without regeneration. Unresolved flags block acceptance/client approval.

DSKAI remains the render queue and claim authority. The SQLite journal/outbox is director intent
and delivery state, not a second generation scheduler. New takes after DONE require distinct
physical backend jobs; a reused predecessor backend_job_id is rejected. Kai must implement that
non-destructive mapping and backend generation-count budget reservation.

## Automation reality

| Function | Implemented | Still required |
|---|---|---|
| Browser live state | 10s bounded polling; original Backlot SSE preserved | Live backend feed |
| Versioned request delivery | GitHub immutable write + uncertain-write reconciliation | Private channel + compatible worker |
| Worker pickup/render | No replacement scheduler introduced | Kai adapter and standing-order resolution |
| Frequent status | Authenticated worker HTTP ingestion | Protected worker-to-director connectivity |
| Completion delivery | Results create durable director QC task | Actual model/agent wake runtime |
| QC return | Durable versioned command + bound Ack | Kai ingestion/application |
| Restart recovery | SQLite/outbox/task lease tests | Supervisor and backend crash test |
| Phone/remote access | Responsive authenticated UI | Authorized HTTPS access setup |

No cost or account coverage is assumed for unattended model execution. Identify runtime,
credentials, actual media/listening capability and any separately billed model cost before use.
Actual live generation, listening QC and duplicate-free backend recovery remain unverified.
Remote editing/export projection still needs Kai records; existing local Backlot artifacts,
editing state and exports remain available without invented progress.
