"""Run explicitly; installs no background service and never starts a model runtime."""
import argparse
import json
import os
import time
from pathlib import Path

from .store import Store
from .transport import GitHub, Sync


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "sync-once", "sync-watch", "events", "schema"])
    parser.add_argument("--after", type=int, default=0)
    args = parser.parse_args()
    if args.command == "schema":
        from . import models
        for name in ("ShotRequest", "Claim", "Result", "QC", "Selection", "Approval", "Control", "Ack"):
            print(json.dumps({"name": name, "schema": getattr(models, name).model_json_schema()}))
        return
    if args.command == "serve":
        import uvicorn
        uvicorn.run("dskai_bridge.app:configured_app", factory=True, host="127.0.0.1",
                    port=4751, access_log=False)
        return
    store = Store(Path(os.environ["DSKAI_STATE_DIR"]) / "director.sqlite3")
    if args.command == "events":
        print(json.dumps(store.events(args.after)))
        return
    remote = GitHub(os.environ["DSKAI_GITHUB_REPO"], os.environ["DSKAI_GITHUB_BRANCH"],
                    os.environ["DSKAI_GITHUB_TOKEN"])
    sync = Sync(store, remote)
    delay = 15
    while True:
        ok = sync.once()
        if args.command == "sync-once":
            raise SystemExit(0 if ok else 1)
        status = store.state("sync")
        # Authentication or incompatible deployment requires intervention, not blind polling.
        if not ok and status["error"] not in {"NETWORK_UNAVAILABLE", "SERVER_UNAVAILABLE", "RATE_LIMITED"}:
            print(status["error"])
            raise SystemExit(1)
        time.sleep(delay)
        delay = 15 if ok else min(delay * 2, 120)


if __name__ == "__main__":
    main()
