# DSKAI Bridge — Resume State (2026-10-09)

## What this is
Muse-side integration for Saneme's automated video studio. External director
(Codex/Claude Code, OpenMontage skills) directs; Kai executes via DSKAI
STUDIO/media-pipeline inside Muse. GitHub repo `sanemelj/OpenMontage-Dskai`
is the versioned instruction/result bridge.

## Completed (2026-10-09)
- Read-only audit of the DSKAI backend (46 tools, job lifecycle, auth, media
  inputs measured, storage, scheduler, restart behavior). Nothing modified,
  no videos generated, canonical projects untouched.
- `contract/dskai-contract.json` v1.0.0 (VERIFIED) — request/claim/result
  schemas, engine constraints, rules.
- `INTEGRATION.md` — human companion doc.
- `scripts/dskai-bridge-poll.sh` — reference worker poll loop.
- Published as branch `dskai-bridge-contract` + PR on
  sanemelj/OpenMontage-Dskai (see PR link in chat).

## Current backend access
- dskai-https: RUNNING (keepalive: dskai-endpoint-keepalive, 2m)
- OpenAI tunnel (ChatGPT path): RUNNING (keepalive: dskai-tunnel-keepalive, 2m)
- SSH tunnel (Claude/generic MCP path): RUNNING, URL rotates —
  current value always in ~/workspace/tunnel/current-public-url.txt
  (keepalive: dskai-ssh-tunnel-keepalive, 5m; notifies on URL change)
- Cloudflare named tunnel (stable URL): DEFERRED per Saneme ("Ok kanpe").
  Revisit when he wants it; needs his one-time Cloudflare login.

## Next steps (when Saneme names the production project)
1. Director writes versioned shot requests to dskai-bridge/requests/.
2. Worker poll cron claims + executes (2-min cadence).
3. Coordinate ONE real end-to-end test: request → claim → generation →
   accessible media → external QC → decision → recovery check (no duplicates).
4. Record evidence under dskai-bridge/tests/.

## Standing prohibitions
No prompt/dialogue rewriting. No regenerating accepted takes. No purchases,
no publishing, no deleting canonical work, no CLIENT_APPROVED marking.
Credentials never in the repo. Brief 401 windows are expected — retry.
