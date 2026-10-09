"""Crash-safe director journal/outbox, NOT a second render queue.

Backend job claims remain authoritative. This store validates their fenced mirror.
Every mutation is transactional, append-only where review history matters.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .models import (Ack, Approval, Binding, Claim, ContinuityReview, Control, Identity, QC, Result,
                     Selection, ShotRequest, canonical, data, digest, identity)


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.db() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, body TEXT NOT NULL,
              hash TEXT NOT NULL, shot_key TEXT NOT NULL, revision INTEGER NOT NULL,
              UNIQUE(shot_key,revision));
            CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
              request_id TEXT NOT NULL, body TEXT NOT NULL, actor TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS selections(shot_key TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS flags(id TEXT PRIMARY KEY, reason TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(path TEXT PRIMARY KEY, body TEXT NOT NULL,
              delivered INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
              kind TEXT NOT NULL, request_id TEXT NOT NULL, body TEXT NOT NULL,
              created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, role TEXT NOT NULL,
              csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(request_id TEXT PRIMARY KEY, owner TEXT,
              fence INTEGER NOT NULL DEFAULT 0, lease REAL NOT NULL DEFAULT 0,
              acked INTEGER NOT NULL DEFAULT 0);
            """)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA synchronous=FULL")
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def key(r):
        d = data(r)
        return "/".join(d[k] for k in ("project", "chapter", "scene", "shot"))

    @staticmethod
    def event(c, kind, rid, body):
        c.execute("INSERT INTO events(kind,request_id,body,created) VALUES(?,?,?,?)",
                  (kind, str(rid), canonical(body), time.time()))

    @staticmethod
    def outbound(c, directory, identifier, body):
        c.execute("INSERT INTO outbox(path,body) VALUES(?,?)",
                  (f"dskai-bridge/{directory}/{identifier}.json", canonical(body)))

    def request(self, rid, c):
        row = c.execute("SELECT body FROM requests WHERE id=?", (str(rid),)).fetchone()
        if not row:
            raise Conflict("unknown request")
        return ShotRequest.model_validate_json(row[0])

    def bound(self, b, c):
        r = self.request(b.request_id, c)
        if identity(b) != identity(r) or b.request_sha256 != digest(r):
            raise Conflict("request identity or prompt digest mismatch")
        return r

    def reviewed(self, b, c):
        r = self.bound(b, c)
        row = c.execute("SELECT body FROM results WHERE id=?", (str(b.request_id),)).fetchone()
        if not row:
            raise Conflict("no result")
        result = Result.model_validate_json(row[0])
        if result.status != "DONE" or not any(
                m.sha256 == b.media_sha256 and m.mime == "video/mp4" for m in result.media):
            raise Conflict("review must bind completed video")
        return r

    def add_request(self, r: ShotRequest):
        rid, body = str(r.request_id), canonical(r)
        with self.db() as c:
            existing = c.execute("SELECT body FROM requests WHERE id=?", (rid,)).fetchone()
            if existing:
                if existing[0] != body:
                    raise Conflict("request ID already used for different payload")
                return False
            key = self.key(r)
            old = c.execute("SELECT MAX(revision) FROM requests WHERE shot_key=?", (key,)).fetchone()[0]
            if old and r.prompt_revision <= old:
                raise Conflict("prompt revision must increase")
            if c.execute("SELECT 1 FROM requests WHERE json_extract(body,'$.take_id')=?",
                         (str(r.take_id),)).fetchone():
                raise Conflict("take ID must be unique")
            versions = [json.loads(x[0])["take_version"] for x in
                        c.execute("SELECT body FROM requests WHERE shot_key=?", (key,))]
            if versions and r.take_version <= max(versions):
                raise Conflict("take version must increase across all shot revisions")
            if old and not r.supersedes:
                raise Conflict("existing shot needs explicit supersedes and strategy change")
            if r.supersedes:
                predecessor = self.request(r.supersedes, c)
                if self.key(predecessor) != key or r.take_version <= predecessor.take_version:
                    raise Conflict("correction must version the same shot")
                # There is no proven backend mapping for a second take after DONE.
                done = c.execute("SELECT body FROM results WHERE id=?", (str(r.supersedes),)).fetchone()
                if done and json.loads(done[0])["status"] == "DONE":
                    c.execute("INSERT INTO flags VALUES(?,?)",
                              (rid, "NEW_TAKE_MAPPING_REQUIRED: Kai must map a new backend shot; DONE is immutable"))
            for dep in r.dependencies:
                pred = self.request(dep.predecessor.request_id, c)
                if identity(pred) != identity(dep.predecessor) or pred.project != r.project:
                    raise Conflict("unknown/cross-project predecessor version")
                selected = c.execute("SELECT body FROM selections WHERE shot_key=?",
                                     (self.key(pred),)).fetchone()
                if not selected:
                    raise Conflict("predecessor must have an explicit retained take selection")
                s = Selection.model_validate_json(selected[0])
                if not self.matches_dependency(s, dep):
                    raise Conflict("dependency does not match selected take and retained frame")
            c.execute("INSERT INTO requests VALUES(?,?,?,?,?)",
                      (rid, body, digest(r), key, r.prompt_revision))
            self.outbound(c, "requests", rid, r)
            self.event(c, "REQUEST_READY", rid, {"request_sha256": digest(r)})
        return True

    @staticmethod
    def matches_dependency(s, dep):
        return (identity(s) == identity(dep.predecessor)
                and s.selection_revision == dep.selection_revision
                and s.media_sha256 == dep.media_sha256
                and s.last_retained_frame == dep.retained_frame_index
                and s.timebase_num == dep.timebase_num and s.timebase_den == dep.timebase_den)

    def ingest_claim(self, claim: Claim):
        with self.db() as c:
            request = self.bound(claim, c)
            if request.supersedes:
                prior = c.execute("SELECT body FROM results WHERE id=?",
                                  (str(request.supersedes),)).fetchone()
                if prior and json.loads(prior[0])["backend_job_id"] == claim.backend_job_id:
                    raise Conflict("new take must not reuse predecessor backend job")
            if claim.lease_until <= claim.heartbeat_at:
                raise Conflict("invalid lease")
            row = c.execute("SELECT body FROM claims WHERE id=?", (str(claim.request_id),)).fetchone()
            if row:
                old = Claim.model_validate_json(row[0])
                if canonical(old) == canonical(claim):
                    return False
                if claim.backend_job_id != old.backend_job_id:
                    raise Conflict("backend job changed: explicit reconciliation required")
                if claim.fence < old.fence or claim.heartbeat_at < old.heartbeat_at:
                    raise Conflict("stale claim")
                if claim.fence > old.fence and old.lease_until > claim.heartbeat_at:
                    raise Conflict("cannot steal an active backend lease")
            c.execute("DELETE FROM flags WHERE id=? AND reason LIKE 'NEW_TAKE_MAPPING_REQUIRED:%'",
                      (str(claim.request_id),))
            c.execute("INSERT OR REPLACE INTO claims VALUES(?,?)",
                      (str(claim.request_id), canonical(claim)))
        return True

    def ingest_result(self, result: Result):
        with self.db() as c:
            self.bound(result, c)
            rid = str(result.request_id)
            old = c.execute("SELECT body FROM history WHERE id=?", (str(result.event_id),)).fetchone()
            if old:
                if old[0] != canonical(result):
                    raise Conflict("event ID reused")
                return False
            row = c.execute("SELECT body FROM claims WHERE id=?", (rid,)).fetchone()
            if not row:
                raise Conflict("result requires reconciled backend claim")
            claim = Claim.model_validate_json(row[0])
            if result.fence != claim.fence or result.backend_job_id != claim.backend_job_id:
                raise Conflict("stale worker fence or backend job mismatch")
            # Events can be delivered after a lease expires, but must have been produced within it.
            stamp = result.observed_at.timestamp()
            if stamp > claim.lease_until or stamp < claim.heartbeat_at - 1800:
                raise Conflict("result outside recorded lease")
            prev = c.execute("SELECT body FROM results WHERE id=?", (rid,)).fetchone()
            if prev:
                p = Result.model_validate_json(prev[0])
                if p.status == "DONE":
                    raise Conflict("DONE take is immutable")
                if result.sequence <= p.sequence:
                    raise Conflict("stale result sequence")
                if p.status in {"FAILED", "BLOCKED", "DEFERRED"}:
                    raise Conflict("held result requires new versioned request")
            for m in result.media:
                # Same immutable asset/version cannot silently identify different bytes or paths.
                for h in c.execute("SELECT body FROM history WHERE kind='RESULT'"):
                    for previous_media in json.loads(h[0]).get("media", []):
                        if (previous_media["asset_id"] == str(m.asset_id)
                                and previous_media["version"] == m.version
                                and previous_media != data(m)):
                            raise Conflict("immutable media version changed")
            c.execute("INSERT INTO history VALUES(?,?,?,?,?)",
                      (str(result.event_id), "RESULT", rid, canonical(result), "kai-muse"))
            c.execute("INSERT OR REPLACE INTO results VALUES(?,?)", (rid, canonical(result)))
            self.event(c, "RESULT_" + result.status, rid, result)
            if result.status == "DONE":
                c.execute("INSERT OR IGNORE INTO tasks(request_id) VALUES(?)", (rid,))
                self.event(c, "DIRECTOR_QC_REQUIRED", rid, {"result_event_id": str(result.event_id)})
        return True

    def decide(self, command, actor):
        kind = type(command).__name__
        roles = {QC: "director", Selection: "director", Control: "director", Approval: "client", ContinuityReview: "director"}
        if actor != roles.get(type(command)):
            raise PermissionError("role cannot issue this decision")
        with self.db() as c:
            existing = c.execute("SELECT body,actor FROM history WHERE id=?",
                                 (str(command.decision_id),)).fetchone()
            if existing:
                if existing[0] != canonical(command) or existing[1] != actor:
                    raise Conflict("decision ID reused")
                return False
            r = self.bound(command, c) if isinstance(command, Control) else self.reviewed(command, c)
            rid = str(command.request_id)
            if isinstance(command, ContinuityReview):
                if not command.full_motion_reviewed or not command.cut_boundaries_reviewed:
                    raise Conflict("continuity override needs actual motion and cut review")
                expected = set()
                for dep in r.dependencies:
                    key = self.key(dep.predecessor)
                    current = c.execute("SELECT body FROM selections WHERE shot_key=?", (key,)).fetchone()
                    if not current:
                        raise Conflict("missing predecessor selection")
                    expected.add(current[0])
                if {canonical(s) for s in command.current_selections} != expected or not expected:
                    raise Conflict("continuity review must bind every current predecessor selection")
                c.execute("DELETE FROM flags WHERE id=? AND reason LIKE 'CONTINUITY_REVIEW_REQUIRED:%'", (rid,))
            if isinstance(command, QC) and command.verdict == "ACCEPT":
                if not (command.full_motion_reviewed and command.audio_listened
                        and command.cut_boundaries_reviewed) or command.limitations:
                    raise Conflict("acceptance needs actual playback, listening and cut review without unresolved limitations")
                if c.execute("SELECT 1 FROM flags WHERE id=?", (rid,)).fetchone():
                    raise Conflict("continuity/backend mapping needs review before acceptance")
            if isinstance(command, Selection):
                row = c.execute("SELECT body FROM selections WHERE shot_key=?", (self.key(r),)).fetchone()
                if row and command.selection_revision <= json.loads(row[0])["selection_revision"]:
                    raise Conflict("selection revision must increase")
                c.execute("INSERT OR REPLACE INTO selections VALUES(?,?)",
                          (self.key(r), canonical(command)))
                for row in c.execute("SELECT id,body FROM requests"):
                    for dep in ShotRequest.model_validate_json(row["body"]).dependencies:
                        if self.key(dep.predecessor) == self.key(r) and not self.matches_dependency(command, dep):
                            c.execute("INSERT OR REPLACE INTO flags VALUES(?,?)",
                                      (row["id"], "CONTINUITY_REVIEW_REQUIRED: selected predecessor or cut changed; no automatic regeneration"))
            if isinstance(command, Approval):
                selection = c.execute("SELECT body FROM selections WHERE shot_key=?", (self.key(r),)).fetchone()
                if not selection:
                    raise Conflict("client approval requires selected take")
                s = Selection.model_validate_json(selection[0])
                if (identity(s) != identity(command) or s.media_sha256 != command.media_sha256
                        or s.selection_revision != command.selection_revision):
                    raise Conflict("client verdict targets stale selection")
                qc = c.execute("SELECT body FROM history WHERE kind='QC' AND request_id=? ORDER BY rowid DESC LIMIT 1",
                               (rid,)).fetchone()
                if command.verdict == "CLIENT_APPROVED" and (
                        not qc or json.loads(qc[0])["verdict"] != "ACCEPT"
                        or json.loads(qc[0])["media_sha256"] != command.media_sha256
                        or c.execute("SELECT 1 FROM flags WHERE id=?", (rid,)).fetchone()):
                    raise Conflict("client approval needs current director acceptance and continuity")
            c.execute("INSERT INTO history VALUES(?,?,?,?,?)",
                      (str(command.decision_id), kind, rid, canonical(command), actor))
            self.outbound(c, "decisions", command.decision_id,
                          {"kind": kind, "actor": actor, "command": data(command)})
            self.event(c, kind.upper() + "_RECORDED", rid, command)
        return True

    def ingest_ack(self, ack: Ack):
        with self.db() as c:
            row = c.execute("SELECT body FROM history WHERE id=?",
                            (str(ack.command_id),)).fetchone()
            if not row or digest(json.loads(row[0])) != ack.command_sha256:
                raise Conflict("ack does not bind exact command")
            if json.loads(row[0])["request_id"] != str(ack.request_id):
                raise Conflict("ack request mismatch")
            old = c.execute("SELECT body FROM history WHERE id=?", (str(ack.event_id),)).fetchone()
            if old:
                if old[0] != canonical(ack):
                    raise Conflict("ack ID reused")
                return False
            c.execute("INSERT INTO history VALUES(?,?,?,?,?)",
                      (str(ack.event_id), "Ack", str(ack.request_id), canonical(ack), "kai-muse"))
            self.event(c, "BACKEND_DECISION_" + ack.outcome, ack.request_id, ack)
        return True

    def pending(self):
        with self.db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM outbox WHERE delivered=0 ORDER BY rowid")]

    def delivered(self, path):
        with self.db() as c:
            c.execute("UPDATE outbox SET delivered=1 WHERE path=?", (path,))

    def set_state(self, key, body):
        with self.db() as c:
            c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, canonical(body)))

    def state(self, key):
        with self.db() as c:
            r = c.execute("SELECT body FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(r[0]) if r else None

    def events(self, after=0):
        with self.db() as c:
            return [{**dict(r), "body": json.loads(r["body"])}
                    for r in c.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 100", (after,))]

    def claim_qc(self, owner, seconds=120):
        # This leases director inspection work only. It never leases generation.
        now = time.time()
        with self.db() as c:
            row = c.execute("SELECT * FROM tasks WHERE acked=0 AND lease<=? ORDER BY rowid LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            fence = row["fence"] + 1
            c.execute("UPDATE tasks SET owner=?,fence=?,lease=? WHERE request_id=?",
                      (owner, fence, now + seconds, row["request_id"]))
            return {"request_id": row["request_id"], "owner": owner, "fence": fence, "lease_until": now + seconds}

    def finish_qc_task(self, rid, owner, fence, renew=False):
        with self.db() as c:
            row = c.execute("SELECT * FROM tasks WHERE request_id=?", (str(rid),)).fetchone()
            if not row or row["owner"] != owner or row["fence"] != fence or row["lease"] <= time.time() or row["acked"]:
                raise Conflict("expired/stale QC task lease")
            if not renew and not c.execute("SELECT 1 FROM history WHERE kind='QC' AND request_id=?", (str(rid),)).fetchone():
                raise Conflict("persist a QC verdict before acknowledging task")
            c.execute("UPDATE tasks SET lease=?,acked=? WHERE request_id=?",
                      (time.time() + 120 if renew else 0, 0 if renew else 1, str(rid)))

    def snapshot(self):
        with self.db() as c:
            result = {}
            for table in ("requests", "results", "claims", "history", "selections"):
                result[table] = [json.loads(r[0]) for r in c.execute(f"SELECT body FROM {table}")]
            result["request_digests"] = {row["id"]: row["hash"] for row in c.execute("SELECT id,hash FROM requests")}
            result["flags"] = [dict(r) for r in c.execute("SELECT * FROM flags")]
            result["pending_delivery"] = c.execute("SELECT COUNT(*) FROM outbox WHERE delivered=0").fetchone()[0]
            result["sync"] = self_state = c.execute("SELECT body FROM kv WHERE key='sync'").fetchone()
            result["sync"] = json.loads(self_state[0]) if self_state else {"state": "NOT_CONFIGURED", "last_success": None}
            result["director_tasks"] = [dict(r) for r in c.execute("SELECT * FROM tasks")]
            return result

    def media(self, asset_id, version):
        with self.db() as c:
            for r in c.execute("SELECT body FROM results"):
                for m in json.loads(r[0]).get("media", []):
                    if m["asset_id"] == str(asset_id) and m["version"] == version:
                        return m
            for r in c.execute("SELECT body FROM requests"):
                body = json.loads(r[0])
                for m in body["references"] + body["plan"]["storyboard"]:
                    if m["asset_id"] == str(asset_id) and m["version"] == version:
                        return m
        raise Conflict("unknown asset")
