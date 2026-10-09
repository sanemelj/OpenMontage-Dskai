# Kai implementation request — v2, pending agreement

Prepared for Kai. Not proof of delivery, implementation or deployment.
Reuse existing DSKAI queue, atomic backend locks, job-renew and media-pipeline.

## Standing orders

INTEGRATION.md at f88e279 says:
"pollers exist but auto-poller/runner/dashboard-sync are disabled by standing order;
rendering happens only inside a Muse session."

OPEN_ISSUES.md instead claims cron is verified and chat closed is fine. The shell script only
lists requests and prints NEW; it does not claim/execute. Report actual process, supervisor,
enabled state and behavior after chat closure/restart. Quote the original disabling order.
Do not enable workers until the user resolves it. The director asked the user specifically;
a general "continue" does not explicitly authorize reversing the standing order.
RESUME.md separately defers Cloudflare under "Ok kanpe"; preserve that.

## Handshake and channels

Agree strict models in dskai_bridge/models.py before enabling v2.
Use a user-authorized private operational repository/explicit branch.
After implementing/verifying all capabilities publish dskai-bridge/runtime/protocol.json:
schema_version "2.0"; true booleans backend_reconciliation, fenced_claims, qc_ingestion,
immutable_takes, standing_order_resolved. Keep it absent/false until verified.
These are compatibility assertions, not switches that start an engine.

## Request execution

1. Strictly validate immutable requests/<request_id>.json. Preserve prompt/dialogue. Hash the
   shared normalized model, including defaults. Reject ID reuse with a different payload.
2. Under the existing backend lock, durably map request ID to project/chapter/physical shot/job/take.
   Write submission intent BEFORE generation. Reconcile real backend state before recovery.
   An ambiguous timeout is not permission to generate again: hold until located/reconciled.
3. Use existing atomic backend claims, 30-minute leases, renewals and monotonic fence. Stale
   workers cannot register media. Expiry alone does not prove a render failed.
4. Capacity is unknown: one active render until measured. Budget reservations use existing
   generation-count ledger; report counts and cost_usd=null.
5. DONE correction gets a NEW physical backend job/shot, preserving original accepted media.
   Do not call submit_revision on DONE. Director rejects predecessor backend-job reuse.
6. Pin predecessor selected take/media/cut/timebase/reference checksum. Extract actual last
   retained frame; attach as still guidance only. Selection changes require review, not cascaded
   regeneration. Reject unsupported engine inputs with a precise blocker.

## State delivery

Frequent claim heartbeats/status go to authenticated /studio/api/worker/claims and /results.
Do not commit each progress tick. Protected connectivity must be provisioned, not public exposure.
GitHub stores recovery snapshots: claims/<request_id>.json, then immutable
results/<request_id>-<event_id>.json for final/held events under the matching fence/lease.
Replay exact event IDs/payloads and increase per-request sequence. Never reopen DONE or a held
revision. No server-local absolute paths, credentials or expiring media URLs in records.

## QC, controls and decisions — missing in v1

Consume decisions/<decision_id>.json: {kind,actor,command}. Authenticate the writer, not merely
its actor string. Shared GitHub write access is a trust boundary: restrict credentials; an
untrusted multi-writer setup requires signed/separate client-authority records.

Validate full identity/digest/media/selection binding, apply once under backend storage:
- QC: director verdict separate from client. Transcript/measurement is not listening evidence.
- Selection: exact take and retained frame interval, preserve history.
- ContinuityReview: append current-selection review; do not rewrite original request.
- Control: HOLD means queued deferral; no active-render cancellation. RESUME cannot erase held
  failure history or reopen a DONE revision.
- Approval: authenticated user/client authority only. Director ACCEPT must not set CLIENT_APPROVED.

Return Ack via acks/<event_id>.json or POST /studio/api/worker/acks, including command_sha256
(hash of command, not envelope), request_id, backend_record_id, APPLIED/BLOCKED and reason.
A GitHub write or local director verdict is not proof of backend application.

## Media and auth

Confirm authenticated GET /files/<relpath> live; resolve the handoff's /media discrepancy.
Return immutable asset UUID/version/SHA256/size/MIME and relative path under projects/, e2e/,
tests/. Preserve canonical versions. Supply credentials privately, never in repo.
Director uses a private connection.json and exact origin allowlist; securely refresh on tunnel
rotation. No arbitrary URL discovery from public result records.
401/403 must trigger auth diagnosis. Distinguish network, rate limits and server failures.
Health reports ok=true, auth_valid=false and no worker_alive: explain actual flag semantics.
Local disk is not replicated storage; provide backup/restore evidence before durability claims.

## Real validation still required

In an authorized isolated project with authorized test content and budget:
request -> backend atomic mapping/claim -> generation -> external /files bytes -> size/hash ->
actual playback/listening/cut QC -> versioned verdict -> backend Ack. Leave client approval alone.
Interrupt after submission and after completion-before-ack; prove one generation/immutable take
and idempotent QC replay. Record redacted IDs/timestamps/checksums/counts, no private assets or tokens.
