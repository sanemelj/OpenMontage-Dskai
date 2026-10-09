"""All fixtures below are SYNTHETIC. No Muse generation or creative QC occurs."""
import hashlib
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from dskai_bridge.app import create_app
from dskai_bridge.media import MediaCache
from dskai_bridge.models import (Ack, Approval, Claim, Control, Dependency, QC, Result,
                                Selection, ShotRequest, canonical, data, digest, identity)
from dskai_bridge.store import Conflict, Store
from dskai_bridge.transport import GitHub, Sync, TransportError


def media(payload=b"synthetic video bytes", mime="video/mp4", suffix="mp4"):
    return {"asset_id": str(uuid4()), "version": 1, "sha256": hashlib.sha256(payload).hexdigest(),
            "relpath": "e2e/synthetic." + suffix, "mime": mime, "size_bytes": len(payload)}


def shot(**changes):
    still = media(b"synthetic storyboard", "image/png", "png")
    plan = {k: "Synthetic fixture only" for k in (
        "script", "primary_action", "identity", "wardrobe", "location", "lighting",
        "props", "screen_direction", "start_state", "end_state", "camera", "editorial_plan")}
    plan["storyboard"] = [still]
    body = {"request_id": str(uuid4()), "project": "synthetic", "chapter": "c1",
            "scene": "s1", "shot": "shot1", "prompt_revision": 1, "take_id": str(uuid4()),
            "take_version": 1, "director": "codex", "prompt": "Synthetic integration fixture",
            "duration_sec": 1, "delivery_framing": "Test fixture only",
            "relation": "independent", "plan": plan, "qc_criteria": ["Synthetic contract checks"],
            "created_at": datetime.now(timezone.utc).isoformat()}
    body.update(changes)
    return ShotRequest.model_validate(body)


def bound(r):
    return {**identity(r), "request_sha256": digest(r)}


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state.db")
        self.r = shot()
        self.store.add_request(self.r)

    def done(self, r=None):
        r = r or self.r
        now = time.time()
        claim = Claim(**bound(r), fence=1, backend_job_id="backend-" + str(r.request_id),
                      heartbeat_at=now, lease_until=now + 1800)
        self.store.ingest_claim(claim)
        result = Result(**bound(r), event_id=uuid4(), sequence=1, backend_job_id=claim.backend_job_id,
                        fence=1, status="DONE", media=[media()], observed_at=datetime.now(timezone.utc))
        self.store.ingest_result(result)
        return result

    def qc(self, result, **kw):
        body = dict(**bound(self.r), media_sha256=result.media[0].sha256, decision_id=uuid4(),
                    verdict="ACCEPT", full_motion_reviewed=True, audio_listened=True,
                    cut_boundaries_reviewed=True, findings=["Synthetic assertions, not real media QC"])
        body.update(kw)
        return QC(**body)

    def select(self, result, revision=1, frame=20):
        return Selection(**bound(self.r), media_sha256=result.media[0].sha256, decision_id=uuid4(),
                         selection_revision=revision, in_frame=0, last_retained_frame=frame,
                         timebase_num=1, timebase_den=24)

    def test_request_duplicate_and_restart(self):
        self.assertFalse(self.store.add_request(self.r))
        changed = self.r.model_copy(update={"prompt": "different intent"})
        with self.assertRaises(Conflict):
            self.store.add_request(changed)
        reopened = Store(Path(self.temp.name) / "state.db")
        self.assertEqual(len(reopened.snapshot()["requests"]), 1)
        self.assertEqual(len(reopened.pending()), 1)

    def test_concurrent_submission_exactly_one(self):
        other = shot(shot="other")
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda _: self.store.add_request(other), range(8)))
        self.assertEqual(sum(results), 1)

    def test_constraint_validation(self):
        for update in ({"duration_sec": 11}, {"duration_sec": float("nan")},
                       {"prompt_revision": True}, {"relation": "continuous_action"},
                       {"end_frame": "unsupported"}, {"audio_input": "unsupported"}):
            with self.assertRaises(ValidationError):
                shot(**update)

    def test_result_binding_and_terminal(self):
        done = self.done()
        self.assertFalse(self.store.ingest_result(done))
        with self.assertRaises(Conflict):
            self.store.ingest_result(done.model_copy(update={"event_id": uuid4(), "sequence": 2}))
        self.assertEqual(len(self.store.snapshot()["director_tasks"]), 1)

    def test_wrong_digest_fence_and_lease(self):
        now = time.time()
        c = Claim(**bound(self.r), fence=1, backend_job_id="b", heartbeat_at=now, lease_until=now+100)
        self.store.ingest_claim(c)
        r = Result(**bound(self.r), event_id=uuid4(), sequence=1, backend_job_id="b",
                   fence=2, status="RENDERING", observed_at=datetime.now(timezone.utc))
        with self.assertRaises(Conflict):
            self.store.ingest_result(r)
        with self.assertRaises(Conflict):
            self.store.ingest_claim(c.model_copy(update={"fence": 2}))
        with self.assertRaises(Conflict):
            self.store.ingest_claim(c.model_copy(update={"request_sha256": "0"*64}))

    def test_audio_and_client_authority(self):
        result = self.done()
        with self.assertRaises(Conflict):
            self.store.decide(self.qc(result, audio_listened=False), "director")
        with self.assertRaises(PermissionError):
            self.store.decide(self.qc(result), "worker")
        self.store.decide(self.qc(result), "director")
        self.store.decide(self.select(result), "director")
        approval = Approval(**bound(self.r), decision_id=uuid4(), media_sha256=result.media[0].sha256,
                            selection_revision=1, verdict="CLIENT_APPROVED")
        with self.assertRaises(PermissionError):
            self.store.decide(approval, "director")
        self.store.decide(approval, "client")
        self.assertFalse(self.store.decide(approval, "client"))
        self.assertTrue(self.store.pending())

    def test_ack_requires_exact_command(self):
        result = self.done()
        q = self.qc(result)
        self.store.decide(q, "director")
        ack = Ack(event_id=uuid4(), command_id=q.decision_id, request_id=self.r.request_id,
                  command_sha256=digest(q), outcome="APPLIED", backend_record_id="qc-1",
                  reason="Synthetic adapter acknowledgement")
        self.assertTrue(self.store.ingest_ack(ack))
        self.assertFalse(self.store.ingest_ack(ack))
        with self.assertRaises(Conflict):
            self.store.ingest_ack(ack.model_copy(update={"event_id":uuid4(), "command_sha256":"0"*64}))

    def test_selection_invalidates_descendants_without_regeneration(self):
        result = self.done()
        selection = self.select(result)
        self.store.decide(selection, "director")
        dep = Dependency(predecessor=identity(self.r), media_sha256=result.media[0].sha256,
                         selection_revision=1, retained_frame_index=20, timebase_num=1,
                         timebase_den=24, reference_sha256="1"*64)
        dependent = shot(shot="shot2", relation="continuous_action", dependencies=[data(dep)])
        self.store.add_request(dependent)
        before = len(self.store.snapshot()["requests"])
        self.store.decide(self.select(result, 2, 19), "director")
        self.assertEqual(len(self.store.snapshot()["requests"]), before)
        self.assertEqual(self.store.snapshot()["flags"][0]["id"], str(dependent.request_id))

    def test_qc_task_atomic_claim_and_stale_ack(self):
        result = self.done()
        with ThreadPoolExecutor(5) as pool:
            claimed = list(pool.map(lambda n: self.store.claim_qc(str(n)), range(5)))
        self.assertEqual(sum(x is not None for x in claimed), 1)
        lease = next(x for x in claimed if x)
        with self.assertRaises(Conflict):
            self.store.finish_qc_task(self.r.request_id, lease["owner"], lease["fence"])
        self.store.decide(self.qc(result), "director")
        self.store.finish_qc_task(self.r.request_id, lease["owner"], lease["fence"])
        self.assertIsNone(self.store.claim_qc("again"))

    def test_correction_preserves_done(self):
        result = self.done()
        r = shot(prompt_revision=2, take_version=2, supersedes=str(self.r.request_id),
                 strategy_change="Synthetic changed direction")
        self.store.add_request(r)
        self.assertEqual(self.store.snapshot()["results"][0]["event_id"], str(result.event_id))
        self.assertIn("NEW_TAKE_MAPPING_REQUIRED", self.store.snapshot()["flags"][0]["reason"])


class TransportTests(unittest.TestCase):
    def test_unknown_put_outcome_reconciles_without_duplicate(self):
        records, puts = {}, []
        def handler(req):
            path = req.url.path
            if req.method == "GET":
                if path not in records:
                    return httpx.Response(404)
                import base64
                return httpx.Response(200, json={"encoding":"base64", "content":base64.b64encode(records[path]).decode()})
            puts.append(path)
            import base64
            records[path] = base64.b64decode(json.loads(req.content)["content"])
            raise httpx.ReadTimeout("ambiguous commit")
        remote = GitHub("owner/private", "work", "never-log", httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(TransportError):
            remote.put_immutable("dskai-bridge/requests/id.json", {"id":1})
        remote.put_immutable("dskai-bridge/requests/id.json", {"id":1})
        self.assertEqual(len(puts), 1)

    def test_auth_not_retried(self):
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(401)
        remote = GitHub("owner/repo", "work", "secret", httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaisesRegex(TransportError, "AUTH_REQUIRED"):
            remote.private()
        self.assertEqual(len(calls), 1)

    def test_public_repo_refused(self):
        remote = GitHub("owner/repo", "work", "secret",
                        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200,json={"private":False}))))
        with self.assertRaisesRegex(TransportError, "PRIVATE_OPERATIONAL_REPOSITORY_REQUIRED"):
            remote.private()

    def test_missing_handshake(self):
        remote = GitHub("owner/repo", "work", "secret",
                        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))))
        with self.assertRaisesRegex(TransportError, "KAI_V2_ADAPTER_REQUIRED"):
            remote.handshake()


class AppMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "store.db")
        self.passwords = {k: k * 32 for k in ("director","client","worker")}

    def client(self, cache=None):
        app = create_app(self.store, self.passwords, "http://testserver", cache, backlot=False)
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def test_auth_csrf_and_roles(self):
        c = self.client()
        self.assertEqual(c.get("/studio/api/state").status_code, 401)
        login = c.post("/studio/login", headers={"Origin":"http://testserver"},
                       json={"role":"director","password":self.passwords["director"]})
        self.assertEqual(login.status_code, 200)
        self.assertIn("HttpOnly", login.headers["set-cookie"])
        self.assertEqual(c.get("/studio/api/state").status_code, 200)
        self.assertEqual(c.post("/studio/api/requests",json=data(shot())).status_code,403)
        good = c.post("/studio/api/requests", json=data(shot()),
                      headers={"Origin":"http://testserver","X-CSRF-Token":login.json()["csrf"]})
        self.assertEqual(good.status_code,200)
        worker = {"Authorization":"Bearer "+self.passwords["worker"]}
        self.assertEqual(c.get("/studio/api/state",headers=worker).status_code,403)
        client = {"Authorization":"Bearer "+self.passwords["client"]}
        self.assertEqual(c.post("/studio/api/requests",headers=client,json=data(shot())).status_code,403)

    def test_media_auth_hash_range_and_head(self):
        payload = b"0123456789synthetic"
        asset = media(payload)
        r = shot()
        self.store.add_request(r)
        now = time.time()
        self.store.ingest_claim(Claim(**bound(r), fence=1, backend_job_id="b", heartbeat_at=now,lease_until=now+100))
        self.store.ingest_result(Result(**bound(r), event_id=uuid4(),sequence=1,backend_job_id="b",
            fence=1,status="DONE",media=[asset],observed_at=datetime.now(timezone.utc)))
        cfg = self.root/"connection.json"
        cfg.write_text(json.dumps({"origin":"https://approved.example","token":"private-token"*3}))
        seen = []
        def handler(req):
            seen.append(req)
            return httpx.Response(200,content=payload)
        cache = MediaCache(self.root/"cache",cfg,{"https://approved.example"},
                           httpx.Client(transport=httpx.MockTransport(handler)))
        c = self.client(cache)
        url = "/studio/media/"+asset["asset_id"]+"/1"
        self.assertEqual(c.get(url).status_code,401)
        headers={"Authorization":"Bearer "+self.passwords["director"],"Range":"bytes=2-5"}
        response=c.get(url,headers=headers)
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.content,b"2345")
        self.assertEqual(seen[0].url.path,"/files/e2e/synthetic.mp4")
        self.assertTrue(seen[0].headers["Authorization"].startswith("Bearer "))
        self.assertNotIn("private-token",response.text)
        self.assertEqual(c.head(url,headers=headers).content,b"")
        self.assertEqual(len(seen),1)

    def test_media_rejects_redirect_auth_bad_hash_and_origin(self):
        cfg = self.root/"connection.json"
        cfg.write_text(json.dumps({"origin":"https://approved.example","token":"private-token"*3}))
        for status in (302,401,500):
            seen=[]
            def handler(req):
                seen.append(req)
                return httpx.Response(status,headers={"Location":"https://evil.example"})
            cache=MediaCache(self.root/str(status),cfg,{"https://approved.example"},
                             httpx.Client(transport=httpx.MockTransport(handler)))
            with self.assertRaises(TransportError):
                cache.fetch(media())
            self.assertEqual(len(seen),1)
        cache=MediaCache(self.root/"bad",cfg,{"https://approved.example"},
                         httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b"wrong"))))
        with self.assertRaises(TransportError):
            cache.fetch(media())
        cfg.write_text(json.dumps({"origin":"https://evil.example","token":"private-token"*3}))
        with self.assertRaisesRegex(TransportError,"CONFIGURATION_REQUIRED"):
            cache.fetch(media())

    def test_paths_and_immutable_version(self):
        from dskai_bridge.models import Media
        for path in ("../secret","projects/../secret.mp4","projects/%2e%2e/x.mp4",
                     "/home/private.mp4","projects/x?token=s.mp4","projects\\x.mp4"):
            with self.assertRaises(ValidationError):
                Media.model_validate({**media(),"relpath":path})


if __name__ == "__main__":
    unittest.main()
