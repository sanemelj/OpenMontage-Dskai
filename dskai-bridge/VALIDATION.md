# Validation evidence — 2026-10-09

## Verified implementation

Code commit: e7a70b91cef84dbc4e99a9514e2d06a8dcd000ec
Successful final code CI:
https://github.com/sanemelj/OpenMontage-Dskai/actions/runs/38000283470

24 deterministic tests plus 1 real Chromium browser test passed. Python compilation,
JavaScript syntax checks and JSON Schema export also passed.
The browser test covers desktop (1440x1000), mobile (390x844), login/logout, client/director
role presentation, authenticated original Backlot routes and duplicate request submission.
Artifacts named synthetic-studio-browser-evidence contain screenshots and exported schemas.

Tests verify:
- Immutable request IDs, monotonic prompt/take identities, concurrent duplicate insertion and restart.
- Exact request digest, backend job/fence matching and immutable DONE results.
- Director inspection lease contention, stale acknowledgement and persistence.
- Ambiguous GitHub PUT reconciliation without duplicate writes, public-channel refusal,
  missing worker handshake and no blind 401 retry.
- Synthetic request/result/QC delivery round trip with durable replay.
- Exact command acknowledgements, distinct director/client authority and actual-inspection flags.
- Selected-cut revisions invalidate old accepting QC for client approval.
- Changed predecessors flag direct and transitive descendants without auto-generation.
- Explicit continuity review can preserve usable existing media; upstream flags must resolve first.
- Queued local HOLD suppresses unpublished request dispatch; RESUME restores eligibility.
- Authenticated media retrieval, SHA/size checks, path checks, redirect refusal, origin allowlist,
  browser Range/HEAD and cache reuse.
- CSRF/session/worker scope, responsive UI and no registry import in browser integration.

All test records and byte payloads are SYNTHETIC. No test assertion represents actual video
motion quality, listening, pronunciation, identity consistency or a real render.
The in-memory GitHub fixture is explicitly labeled; it is not a mock presented as live production.

## Live read-only check

DSKAI health returned connector/backend/storage/poller/endpoint alive=true and auth_valid=false,
worker_alive absent, timestamp 1791569914.130904.
This proves a response was received, not authorized external media access or persistent rendering.

## Not verified / not implemented in Muse

- v2 Muse adapter agreement/deployment, actual canonical queue mapping and QC ingestion.
- Resolution of disabled-worker standing order; chat-closed/reboot rendering.
- Persistent external model/agent activation and any associated account/billing.
- Private operational repository configuration and authenticated rotating media origin.
- Real generation -> external media -> listening/motion QC -> persisted Muse Ack.
- Backend crash recovery with exactly one generation.
- Measured parallel engine capacity, production continuity chain, final assembly.
- Independent replicated media durability or backup restore.
- Local Windows runtime: process helper fails before PowerShell starts.
- General provider discovery telemetry origin/opt-out; discovery was not executed.

No merge, deployment, purchase, production generation, canonical asset change or client approval.
See DIRECTOR_SETUP.md, KAI_IMPLEMENTATION_REQUEST.md and IMPLEMENTATION_RESUME.md.
