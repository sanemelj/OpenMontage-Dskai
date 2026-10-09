#!/usr/bin/env bash
# dskai-bridge-poll.sh — reference worker loop for the DSKAI bridge.
# The Muse-side worker (Kai) runs this on a ~2 minute cadence (cron).
# It polls sanemelj/OpenMontage-Dskai/dskai-bridge/requests/ for new
# versioned shot requests, claims them, executes via the DSKAI backend,
# and writes results to dskai-bridge/results/.
#
# This script documents the exact loop. The live worker performs the same
# steps through its own tool calls (GitHub API + DSKAI backend).
set -u
REPO="sanemelj/OpenMontage-Dskai"
BRIDGE="dskai-bridge"
WORKDIR="/home/hatch/workspace/dskai-bridge/state"

echo "=== bridge poll $(date -Is) ==="

# 1. List request files
REQUESTS=$(curl -s -m 20 "https://api.github.com/repos/$REPO/contents/$BRIDGE/requests" \
  | python3 -c "import json,sys; print('\n'.join(x['name'] for x in json.load(sys.stdin) if x['name'].endswith('.json')))" 2>/dev/null)

# 2. For each request: skip if a claim or result already exists (idempotency)
for r in $REQUESTS; do
  id="${r%.json}"
  has_claim=$(curl -s -m 20 -o /dev/null -w "%{http_code}" "https://api.github.com/repos/$REPO/contents/$BRIDGE/claims/$id.json")
  has_result=$(curl -s -m 20 -o /dev/null -w "%{http_code}" "https://api.github.com/repos/$REPO/contents/$BRIDGE/results/$id.json")
  if [ "$has_claim" = "200" ] || [ "$has_result" = "200" ]; then
    echo "SKIP $id (already claimed/decided)"
    continue
  fi
  echo "NEW $id -> worker validates against contract, writes claim, executes, writes result"
done

echo "=== poll done ==="
