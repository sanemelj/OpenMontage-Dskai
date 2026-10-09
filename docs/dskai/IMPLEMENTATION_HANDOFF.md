# DSKAI integration handoff — 2026-10-09

Status: AUDIT INCOMPLETE / IMPLEMENTATION BLOCKED. No working automated studio is claimed.
Base inspected: 9327439db69021ab4b0e2776729bf3b58fdb5a87.
Review branch: codex/dskai-contract-audit.

## User's controlling architecture and scope

Codex/Claude directs using OpenMontage; Kai/DSKAI inside Muse executes generation.
Preserve canonical projects, integrations and approved media. Never set CLIENT_APPROVED for the user.
No production brief exists yet: do not invent characters, language, genre, duration or aspect ratio.
No external generation API, paid storage migration, purchases, public deployment, merge or content publication authorized.
Implementation should reuse the existing DSKAI bridge and adapt Backlot, not introduce a competing queue.
GitHub stores code and lightweight versioned requests/manifests/decisions; durable media stays in existing storage until inspected.
GitHub and interactive chat access do not establish a persistent director runtime.

## Evidence collected

Read AGENTS.md, AGENT_GUIDE.md and PROJECT_CONTEXT.md.
Read backlot/README.md and backlot/server.py, tools/tool_registry.py, tools/base_tool.py,
requirements.txt, .github/workflows/ci.yml, tools/video/clip_cache.py and lib/clip_embedder.py.

- Backlot currently has local filesystem-derived project state, media/thumbnails and watchfiles/SSE.
  Its inspected server has no authentication middleware or mutation endpoints.
  Its existing UI/state machinery is reusable; remote DSKAI integration is not verified.
- Registry discovery recursively imports tool modules; status checks can import dependencies.
  BaseTool events write local Backlot activity. These observations do not identify the earlier PostHog source.
  No registry discovery was run. Telemetry opt-out remains unverified; inspect installed dependency
  versions and import chain before running discovery. Do not bypass approval restrictions.
- GitHub returned a non-truncated main tree and only main in the branch listing before this review branch.
  No DSKAI-named or Muse bridge path was located. Code searches were empty; REST search
  reported incomplete_results=true, so this is NOT proof the integration is absent.
- Current connector declarations expose DSKAI execution manifests, revisions, job status, QC,
  continuity, timeline, references, budget and expiring media retrieval. Declarations are not
  runtime verification of these operations or a backend source audit.
- Three read-only DSKAI calls succeeded: health, get_capabilities and list_engines.
  Health at backend timestamp 1791568767.1549869 returned ok=true, connector_alive=true,
  backend_alive=true, storage_access=true, poller_alive=true, endpoint_alive=true,
  auth_valid=false, stateless=true, session_required=false.
  worker_alive was absent. Authentication inconsistency and worker liveness remain unresolved.
- Engines report media-pipeline built-in as default; google-flow-browser also registered.
  No switch was made. Registration does not establish engine availability.
- Capability report is dated 2026-10-03, returned live in this audit, not remeasured here:
  10-second single generation limit; text/image inputs; native audio; no true start-frame
  parameter (image guidance only); no end-frame targeting or real extension; no audio voice
  reference input; native size reported 1152x768; no monetary billing API.
  Generation counts are a usage proxy, not USD or proof of free operation.
  Do not inherit its universal chaining/cropping recommendations: the user requires selective
  short continuity chains and will choose format later.

## Execution blocker

Two local exec attempts failed before process creation:
helper_unknown_error: setup refresh had errors.
The second explicitly selected Windows PowerShell with login=false.
This is a local runner failure, not a reported automatic approval policy rejection.
Local checkout location, changes, GPU, Python, test runtime and media inspection remain unverified.
GitHub connector reads and branch writes work.

Kai's communication location/backend source was requested from the user using an asynchronous
question. No Kai response or source export was available when this document was written.
Do not claim that the backend contract was obtained.

## Next executable steps

1. Obtain Kai's source/contract response using docs/dskai/KAI_CONTRACT_REQUEST.md.
   Resolve auth_valid=false and identify a permitted isolated test project.
2. Restore local command execution and locate the prior checkout; inspect git status before edits.
   Fetch this review branch without overwriting local work. Re-read repository instructions.
3. Trace discovery telemetry statically, then use verified documented opt-out controls before execution.
4. Map the agreed shared contract to the existing queue; implement adapters and authenticated
   Backlot controls/media access. No invented endpoints or second generation queue.
5. Verify both wake paths, leases/heartbeats, atomic claims, durable event cursor and restart recovery.
   A timed-out submission is UNKNOWN until reconciled; never blindly repeat generation.
6. Run one real isolated job: request -> Muse claim -> generation -> accessible immutable media
   -> actual director QC -> version-pinned decision returned to Muse. Client approval stays separate.
7. After the user supplies content: measured parallel coverage, a short continuity chain and final assembly.

## Contract acceptance requirements

Unique request IDs, schema/prompt versions and payload digests; reject same ID/different payload.
Bind results/QC/approval to exact request, project/scene/shot/take/media versions.
Separate generation status, director acceptance and authenticated client approval.
Persist provider submission identity BEFORE allowing recovery to repeat work; reconcile ambiguous submissions.
Atomic claim plus fencing token, lease expiry and heartbeats; reject stale worker writes.
Expired leases must not imply generation did not happen.
Durable result delivery with deduplication, acknowledgements/replay and bounded polling or events.
Cost caps and usage reservations must be enforced across concurrent workers; unknown dollars remain unknown.
Independent coverage parallelism must follow measured engine capacity.
Continuous-action dependencies identify selected take version, exact retained cut point/timebase
and extracted last retained frame. Image-reference guidance must not be described as exact frame control.
Changing predecessor selection/trim flags downstream review rather than regenerating everything.
Scene plans lock identity, wardrobe, props, geography, lighting, screen direction, start/end states
and editorial intent before generation.
QC records identify full playback/audio listening versus sampled frames/automated measurements.
Never infer listening QC from transcripts/waveforms or full motion QC from stills.
Local repair first; strategy changes after equivalent repeated failures; budgets, no arbitrary artistic retry ceiling.
Frontend needs projects/scripts/storyboards/references/dependencies/status/takes/QC/playable media/editing/exports,
available usage/cost, synchronization timestamps/errors, authenticated submission/hold/resume/correction/approval.
Secrets stay server-side. Expiring URLs need renewal tied to immutable asset identity.
No commit per progress event; maintain runtime status through backend events or bounded polling.

## Validation performed and not performed

Performed: remote source inspection; GitHub tree/branch reads; three read-only DSKAI calls.
Not performed: tests, generation, scheduler/recovery tests, authentication tests, media retrieval,
playback/listening, frontend runtime validation, QC mutations, deployment or merge.
This branch contains audit/handoff records only, not a mock or implemented integration.
