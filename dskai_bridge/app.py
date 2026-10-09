"""Authenticated studio extension of Backlot. Bind loopback by default; TLS for remote use."""
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .media import MediaCache
from .models import Approval, Claim, Control, QC, Result, Selection, ShotRequest, Ack
from .store import Conflict, Store
from .transport import TransportError

UI = Path(__file__).with_name("ui")


class Login(BaseModel):
    role: str
    password: str = Field(max_length=1024)


class TaskLease(BaseModel):
    request_id: UUID
    owner: str = Field(min_length=1, max_length=100)
    fence: int = Field(ge=1)


def create_app(store, passwords, origin, media_cache=None, backlot=True):
    if set(passwords) != {"director", "client", "worker"} or any(len(v) < 24 for v in passwords.values()):
        raise ValueError("three distinct server-side credentials (24+ characters) required")
    if len(set(passwords.values())) != 3:
        raise ValueError("roles must not share credentials")
    if not (origin.startswith("https://") or origin in {"http://127.0.0.1:4751", "http://localhost:4751", "http://testserver"}):
        raise ValueError("TLS origin required except loopback development")
    if backlot:
        from backlot.server import create_app as backlot_app
        app = backlot_app()  # preserve existing board URLs, assets, SSE and watcher lifespan
    else:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def role(request, expected):
        if request.state.role != expected:
            raise HTTPException(403, "role not authorized")

    @app.middleware("http")
    async def authenticate(request, call_next):
        path = request.url.path
        if path not in {"/studio/login", "/studio/login.js"}:
            principal = None
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                for name, credential in passwords.items():
                    if hmac.compare_digest(auth[7:], credential):
                        principal = name
                        break
            else:
                session = request.cookies.get("studio_session", "")
                with store.db() as c:
                    row = c.execute("SELECT * FROM sessions WHERE hash=? AND expires>?",
                                    (hashlib.sha256(session.encode()).hexdigest(), time.time())).fetchone()
                if row:
                    principal = row["role"]
                    if request.method not in {"GET", "HEAD", "OPTIONS"}:
                        if (request.headers.get("origin") != origin
                                or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), row["csrf"])):
                            return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
            if principal is None:
                return JSONResponse({"detail": "Authentication required. Open /studio/login."}, status_code=401)
            request.state.role = principal
            # Worker ingestion credentials cannot browse private creative material or approve.
            if principal == "worker" and not path.startswith("/studio/api/worker/"):
                return JSONResponse({"detail": "worker scope"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if path.startswith("/studio"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(PermissionError)
    async def permission_handler(request, exc):
        return JSONResponse({"detail": "role not authorized"}, status_code=403)

    @app.exception_handler(TransportError)
    async def transport_handler(request, exc):
        return JSONResponse({"detail": exc.code}, status_code=502)

    @app.get("/studio/login", response_class=HTMLResponse)
    def login_page():
        return (UI / "login.html").read_text()

    @app.get("/studio/login.js")
    def login_script():
        return FileResponse(UI / "login.js", media_type="text/javascript")

    @app.post("/studio/login")
    def login(body: Login, request: Request):
        # Browser-only login. API callers use scoped Bearer credentials.
        if request.headers.get("origin") != origin:
            raise HTTPException(403, "origin mismatch")
        if body.role not in {"director", "client"}:
            raise HTTPException(401, "invalid credentials")
        # A global limiter avoids trusting spoofable forwarded client addresses.
        limiter = store.state("login_attempts") or {"start": time.time(), "count": 0}
        if time.time() - limiter["start"] > 60:
            limiter = {"start": time.time(), "count": 0}
        limiter["count"] += 1
        store.set_state("login_attempts", limiter)
        if limiter["count"] > 15:
            raise HTTPException(429, "login rate limit")
        if not hmac.compare_digest(body.password, passwords[body.role]):
            raise HTTPException(401, "invalid credentials")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with store.db() as c:
            c.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
            c.execute("INSERT INTO sessions VALUES(?,?,?,?)",
                      (hashlib.sha256(token.encode()).hexdigest(), body.role, csrf, time.time() + 28800))
        response = JSONResponse({"csrf": csrf, "role": body.role})
        response.set_cookie("studio_session", token, httponly=True, secure=origin.startswith("https"),
                            samesite="strict", max_age=28800, path="/")
        return response

    @app.post("/studio/logout")
    def logout(request: Request):
        with store.db() as c:
            c.execute("DELETE FROM sessions WHERE hash=?",
                      (hashlib.sha256(request.cookies.get("studio_session", "").encode()).hexdigest(),))
        response = JSONResponse({"ok": True})
        response.delete_cookie("studio_session")
        return response

    @app.get("/studio")
    def studio():
        return FileResponse(UI / "index.html")

    @app.get("/studio/assets/{name}")
    def asset(name: str):
        if name not in {"studio.js", "studio.css"}:
            raise HTTPException(404)
        return FileResponse(UI / name)

    @app.get("/studio/api/session")
    def session(request: Request):
        csrf = ""
        with store.db() as c:
            row = c.execute("SELECT csrf FROM sessions WHERE hash=?",
                            (hashlib.sha256(request.cookies.get("studio_session", "").encode()).hexdigest(),)).fetchone()
            if row:
                csrf = row[0]
        return {"role": request.state.role, "csrf": csrf}

    @app.get("/studio/api/state")
    def state():
        return store.snapshot()

    @app.get("/studio/api/events")
    def events(after: int = 0):
        return store.events(max(0, after))

    @app.post("/studio/api/requests")
    def submit(body: ShotRequest, request: Request):
        role(request, "director")
        return {"created": store.add_request(body)}

    command_types = {"qc": QC, "selection": Selection, "approval": Approval, "control": Control}

    @app.post("/studio/api/decisions/{kind}")
    async def decision(kind: str, request: Request):
        from pydantic import ValidationError
        if kind not in command_types:
            raise HTTPException(404)
        try:
            command = command_types[kind].model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(422, "invalid decision contract") from None
        return {"created": store.decide(command, request.state.role),
                "backend_applied": False, "note": "Recorded locally; inspect worker acknowledgement"}

    @app.post("/studio/api/worker/claims")
    def claim(body: Claim, request: Request):
        role(request, "worker")
        return {"created": store.ingest_claim(body)}

    @app.post("/studio/api/worker/results")
    def result(body: Result, request: Request):
        role(request, "worker")
        return {"created": store.ingest_result(body)}

    @app.post("/studio/api/worker/acks")
    def ack(body: Ack, request: Request):
        role(request, "worker")
        return {"created": store.ingest_ack(body)}

    @app.post("/studio/api/qc-tasks/claim")
    def task_claim(request: Request, owner: str = "interactive-director"):
        role(request, "director")
        if not 1 <= len(owner) <= 100:
            raise HTTPException(422)
        return store.claim_qc(owner)

    @app.post("/studio/api/qc-tasks/{action}")
    def task_update(action: str, body: TaskLease, request: Request):
        role(request, "director")
        if action not in {"renew", "ack"}:
            raise HTTPException(404)
        store.finish_qc_task(body.request_id, body.owner, body.fence, renew=action == "renew")
        return {"ok": True}

    @app.api_route("/studio/media/{asset_id}/{version}", methods=["GET", "HEAD"])
    def media(asset_id: UUID, version: int):
        if media_cache is None:
            raise HTTPException(503, "MEDIA_CONNECTION_CONFIGURATION_REQUIRED")
        record = store.media(asset_id, version)
        path = media_cache.fetch(record)
        return FileResponse(path, media_type=record["mime"], content_disposition_type="inline",
                            headers={"ETag": '"' + record["sha256"] + '"'})
    return app


def configured_app():
    root = Path(os.environ["DSKAI_STATE_DIR"])
    store = Store(root / "director.sqlite3")
    passwords = {role: os.environ["DSKAI_" + role.upper() + "_CREDENTIAL"]
                 for role in ("director", "client", "worker")}
    media = MediaCache(root / "media", root / "connection.json",
                       os.environ.get("DSKAI_ALLOWED_MEDIA_ORIGINS", "").split(","))
    return create_app(store, passwords, os.environ["DSKAI_STUDIO_ORIGIN"], media)
