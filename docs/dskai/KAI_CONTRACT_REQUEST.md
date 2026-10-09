# Kai backend contract request

Purpose: integrate OpenMontage direction with the existing DSKAI/Muse worker and adapt Backlot.
This is a request prepared for Kai, NOT a response from Kai and NOT evidence of delivery.
Do not generate media, change canonical projects, approve assets, buy services or deploy publicly for this audit.

Return a dated, versioned contract with source revision and redacted evidence. Never include secrets,
private media bytes or signed media URLs in Git. Explicitly distinguish implemented/tested from proposed.

1. Source and inventory: bridge repository/path/revision; current tool names and exact request/result
   schemas; project/chapter/scene/shot/take mapping; canonical state paths; sanitized example manifests.
2. Existing queue: how requests arrive, who stages/claims them, atomic primitive, idempotency keys,
   provider submission IDs, lease/heartbeat/fencing, concurrency limits, holds and cancellation.
   Explain crash windows before/after submission and recovery after a timeout without duplicate generation.
3. Worker runtime: actual process/service and supervisor, restart behavior, poll interval, last heartbeat,
   whether it survives closing Muse/chat, measured generation capacity and contention constraints.
   Supply one redacted evidence trace, not just a tool count or a health boolean.
4. Both trigger directions: mechanism waking Muse on a ready request; mechanism delivering completion
   to Codex/Claude; event schema, authentication, delivery retries, acknowledgements, durable replay cursor.
   Identify absent director runtime, account connections and separately billed execution/model costs.
5. Health: explain why current health reports ok=true and auth_valid=false; document what each flag
   tests, whether worker_alive exists, and which operations require which authenticated principal.
6. Media/storage: current durable storage, immutable IDs/checksums, retention, take revisions, retrieval
   and URL renewal contracts; external director/browser accessibility, audio/video ranges, authorization,
   CORS if applicable, and behavior after signed URL expiration. Provide a test fixture identity through
   a private channel; do not migrate storage or place secrets/signed URLs in the repo.
7. State/authority: distinct generation completion, director acceptance and CLIENT_APPROVED;
   exact actor authorization and version binding, append-only history and revocation/stale-QC behavior.
   Describe how current gate2 maps to these concepts without granting client authority to the director.
8. Editing/continuity: selected take and trim versions, rational timebase/frame index, extraction of
   actual last retained frame, dependency invalidation, and exact supported input parameters.
   Confirm whether start-frame remains image guidance only. Do not claim exact control from SSIM.
9. Controls: existing submission, hold/resume, correction and approval APIs, expected revision checks,
   audit trail, errors and idempotency. List missing operations explicitly.
10. Usage: count ledger, concurrent budget reservation/reconciliation, engine-reported charges if any;
    distinguish unknown monetary cost from zero.
11. QC: accessible playback/audio, measurement versus listening/motion evidence, exact version pinning,
    selective repair and strategy-change requirements after repeated equivalent failures.
12. Test: identify an isolated noncanonical job/fixture suitable for a real integration check, including
    generation budget and how to verify request -> claim -> media -> director QC returned to Muse.
    No client approval or actual production content should be inferred.

Preferred response: docs/dskai/backend-contract.json plus docs/dskai/backend-contract.md on a
review branch, with secret-free schema examples and links to the existing implementation.
The final wire contract must be derived from this implementation, not an invented replacement queue.
