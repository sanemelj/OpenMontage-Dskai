"""Bounded GitHub delivery. No rendering, model API calls or credential logging."""
import base64
import json
import re
import time
from urllib.parse import quote

import httpx

from .models import Ack, Claim, Result, canonical
from .store import Conflict


class TransportError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class GitHub:
    def __init__(self, repo, branch, token, client=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("invalid GitHub repository")
        if not branch or len(branch) > 200:
            raise ValueError("explicit operational branch required")
        self.root = "https://api.github.com/repos/" + repo
        self.branch = branch
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self.headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"}

    def call(self, method, path="", **kwargs):
        try:
            r = self.client.request(method, self.root + path, headers=self.headers, **kwargs)
        except httpx.TransportError:
            raise TransportError("NETWORK_UNAVAILABLE") from None
        if r.status_code in (401, 403):
            # Never retry credentials as though this were a network error.
            raise TransportError("AUTH_REQUIRED")
        if r.status_code == 429:
            raise TransportError("RATE_LIMITED")
        if r.status_code >= 500:
            raise TransportError("SERVER_UNAVAILABLE")
        if r.status_code not in (200, 201, 404, 409, 422):
            raise TransportError("UNEXPECTED_HTTP_STATUS")
        return r

    def private(self):
        r = self.call("GET")
        if r.status_code != 200 or r.json().get("private") is not True:
            raise TransportError("PRIVATE_OPERATIONAL_REPOSITORY_REQUIRED")

    def read(self, path):
        r = self.call("GET", "/contents/" + quote(path, safe="/"),
                      params={"ref": self.branch})
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise TransportError("GITHUB_READ_CONFLICT")
        obj = r.json()
        if not isinstance(obj, dict) or obj.get("encoding") != "base64":
            raise TransportError("INVALID_RECORD_ENCODING")
        try:
            decoded = base64.b64decode(obj["content"], validate=False)
            if len(decoded) > 2_000_000:
                raise ValueError()
            return json.loads(decoded)
        except (ValueError, KeyError):
            raise TransportError("INVALID_RECORD") from None

    def put_immutable(self, path, body):
        # A timeout from PUT can mean it committed. Re-read by ID on EVERY attempt.
        previous = self.read(path)
        if previous is not None:
            if canonical(previous) != canonical(body):
                raise Conflict("remote immutable ID conflicts")
            return
        response = self.call("PUT", "/contents/" + quote(path, safe="/"),
                             json={"branch": self.branch, "message": "bridge: versioned record",
                                   "content": base64.b64encode(canonical(body).encode()).decode()})
        if response.status_code not in (200, 201):
            previous = self.read(path)
            if previous is None or canonical(previous) != canonical(body):
                raise Conflict("concurrent remote immutable write")

    def paths(self, directory):
        # Git tree enumeration avoids the contents endpoint's 1000-file truncation.
        r = self.call("GET", "/git/trees/" + quote(self.branch, safe=""),
                      params={"recursive": "1"})
        if r.status_code != 200 or r.json().get("truncated"):
            raise TransportError("INCOMPLETE_REPOSITORY_TREE")
        return sorted(e["path"] for e in r.json()["tree"]
                      if e["type"] == "blob" and e["path"].startswith(directory + "/")
                      and e["path"].endswith(".json"))

    def handshake(self):
        p = self.read("dskai-bridge/runtime/protocol.json")
        if not p or p.get("schema_version") != "2.0":
            raise TransportError("KAI_V2_ADAPTER_REQUIRED")
        for flag in ("backend_reconciliation", "fenced_claims", "qc_ingestion",
                     "immutable_takes", "standing_order_resolved"):
            if p.get(flag) is not True:
                raise TransportError("KAI_CAPABILITY_NOT_CONFIRMED_" + flag.upper())


class Sync:
    def __init__(self, store, remote):
        self.store, self.remote = store, remote

    def once(self):
        previous = self.store.state("sync") or {}
        started = time.time()
        try:
            self.remote.private()
            self.remote.handshake()
            # Mirrors arrive before results; live heartbeat changes should use backend reads,
            # not a commit for every tick. This channel stores durable snapshots.
            for path in self.remote.paths("dskai-bridge/claims"):
                self.store.ingest_claim(Claim.model_validate(self.remote.read(path)))
            results = [Result.model_validate(self.remote.read(p))
                       for p in self.remote.paths("dskai-bridge/results")]
            for result in sorted(results, key=lambda r: (str(r.request_id), r.sequence)):
                self.store.ingest_result(result)
            for path in self.remote.paths("dskai-bridge/acks"):
                self.store.ingest_ack(Ack.model_validate(self.remote.read(path)))
            for row in self.store.pending():
                self.remote.put_immutable(row["path"], json.loads(row["body"]))
                self.store.delivered(row["path"])
            self.store.set_state("sync", {"state": "CONNECTED", "last_attempt": started,
                                         "last_success": time.time(), "error": None})
            return True
        except (TransportError, Conflict, ValueError) as exc:
            code = exc.code if isinstance(exc, TransportError) else "CONTRACT_CONFLICT"
            self.store.set_state("sync", {"state": "BLOCKED", "last_attempt": started,
                                         "last_success": previous.get("last_success"), "error": code})
            return False
