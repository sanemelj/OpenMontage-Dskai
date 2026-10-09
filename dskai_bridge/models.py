"""Protocol v2. No implicit upgrade of Kai's v1 draft; adapter handshake required."""
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

Slug = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Positive = Annotated[int, Field(strict=True, ge=1)]
Text = Annotated[str, StringConstraints(min_length=1, max_length=32000)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["2.0"] = "2.0"


class Identity(Record):
    request_id: UUID
    project: Slug
    chapter: Slug
    scene: Slug
    shot: Slug
    prompt_revision: Positive
    take_id: UUID
    take_version: Positive


class Media(Record):
    asset_id: UUID
    version: Positive
    sha256: Digest
    relpath: str
    mime: Literal["video/mp4", "audio/wav", "audio/mpeg", "audio/mp4", "image/png", "image/jpeg"]
    size_bytes: Annotated[int, Field(strict=True, gt=0)]

    @model_validator(mode="after")
    def safe_path(self):
        parts = self.relpath.split("/")
        if (parts[0] not in {"projects", "e2e", "tests"} or len(parts) < 2
                or any(p in {"", ".", ".."} for p in parts)
                or any(c in self.relpath for c in "\\%?#:\r\n")):
            raise ValueError("media must use an allowlisted relative /files/ path")
        allowed = {"video/mp4": (".mp4",), "audio/wav": (".wav",),
                   "audio/mpeg": (".mp3",), "audio/mp4": (".m4a",),
                   "image/png": (".png",), "image/jpeg": (".jpg", ".jpeg")}
        if not self.relpath.lower().endswith(allowed[self.mime]):
            raise ValueError("media extension does not match MIME")
        return self


class Dependency(Record):
    predecessor: Identity
    media_sha256: Digest
    selection_revision: Positive
    # Last INCLUDED frame, not an exclusive end timestamp or an approximate seek.
    retained_frame_index: Annotated[int, Field(strict=True, ge=0)]
    timebase_num: Positive
    timebase_den: Positive
    reference_sha256: Digest
    relation: Literal["continuous_action"] = "continuous_action"
    conditioning: Literal["image_reference_guidance"] = "image_reference_guidance"


class ScenePlan(Record):
    script: str
    primary_action: Text
    identity: Text
    wardrobe: Text
    location: Text
    lighting: Text
    props: Text
    screen_direction: Text
    start_state: Text
    end_state: Text
    camera: Text
    editorial_plan: Text
    storyboard: Annotated[list[Media], Field(min_length=1)]


class ShotRequest(Identity):
    director: Literal["codex", "claude-code"]
    prompt: Text
    dialogue: str = ""
    duration_sec: Annotated[float, Field(gt=0, le=10)]
    native_geometry: Literal["1152x768"] = "1152x768"
    # Delivery framing is editorial intent, never sent as a generation parameter.
    delivery_framing: Text
    relation: Literal["independent", "continuous_action", "scene_reset"]
    plan: ScenePlan
    references: list[Media] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    qc_criteria: Annotated[list[Text], Field(min_length=1)]
    created_at: datetime
    supersedes: UUID | None = None
    strategy_change: str | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.created_at.tzinfo is None:
            raise ValueError("created_at needs timezone")
        if (self.relation == "continuous_action") != bool(self.dependencies):
            raise ValueError("continuous action requires exact predecessor dependencies")
        if any(d.predecessor.request_id == self.request_id for d in self.dependencies):
            raise ValueError("self dependency")
        if any(m.mime not in {"image/png", "image/jpeg"}
               for m in self.references + self.plan.storyboard):
            raise ValueError("references and storyboard must be still images")
        if self.supersedes and not (self.strategy_change or "").strip():
            raise ValueError("corrections require a strategy change")
        return self


class Binding(Identity):
    request_sha256: Digest


class Claim(Binding):
    worker_id: Literal["kai-muse"] = "kai-muse"
    fence: Positive
    backend_job_id: Text
    lease_until: Annotated[float, Field(gt=0)]
    heartbeat_at: Annotated[float, Field(gt=0)]


class Result(Binding):
    event_id: UUID
    sequence: Positive
    backend_job_id: Text
    fence: Positive
    status: Literal["QUEUED", "WAITING_ON_DEPENDENCY", "ON_HOLD", "CLAIMED",
                    "RENDERING", "DONE", "FAILED", "DEFERRED", "BLOCKED"]
    media: list[Media] = Field(default_factory=list)
    blockers: list[Text] = Field(default_factory=list)
    generations_used: Annotated[int, Field(strict=True, ge=0)] | None = None
    cost_usd: None = None  # no billing API; unknown is not zero
    observed_at: datetime

    @model_validator(mode="after")
    def completed_media(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at needs timezone")
        if self.status == "DONE" and not any(m.mime == "video/mp4" for m in self.media):
            raise ValueError("DONE requires immutable playable video identity")
        if self.status in {"FAILED", "DEFERRED", "BLOCKED"} and not self.blockers:
            raise ValueError("blocked/failed/deferred needs precise reason")
        if len({str(m.asset_id) for m in self.media}) != len(self.media):
            raise ValueError("duplicate media asset")
        return self


class Reviewed(Binding):
    media_sha256: Digest


class QC(Reviewed):
    decision_id: UUID
    verdict: Literal["ACCEPT", "REJECT", "NEEDS_REVIEW"]
    full_motion_reviewed: StrictBool
    audio_listened: StrictBool
    cut_boundaries_reviewed: StrictBool
    findings: Annotated[list[Text], Field(min_length=1)]
    limitations: list[Text] = Field(default_factory=list)


class Selection(Reviewed):
    decision_id: UUID
    selection_revision: Positive
    in_frame: Annotated[int, Field(strict=True, ge=0)]
    last_retained_frame: Annotated[int, Field(strict=True, ge=0)]
    timebase_num: Positive
    timebase_den: Positive

    @model_validator(mode="after")
    def valid_cut(self):
        if self.last_retained_frame < self.in_frame:
            raise ValueError("invalid retained frame interval")
        return self


class Approval(Reviewed):
    decision_id: UUID
    selection_revision: Positive
    verdict: Literal["CLIENT_APPROVED", "CLIENT_REJECTED"]


class Control(Binding):
    decision_id: UUID
    action: Literal["HOLD", "RESUME"]
    reason: Text


class Ack(Record):
    event_id: UUID
    command_id: UUID
    request_id: UUID
    command_sha256: Digest
    outcome: Literal["APPLIED", "BLOCKED"]
    backend_record_id: Text
    reason: Text


def data(model):
    return model.model_dump(mode="json") if isinstance(model, BaseModel) else model


def canonical(model):
    return json.dumps(data(model), sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(model):
    return hashlib.sha256(canonical(model).encode()).hexdigest()


def identity(model):
    return {k: data(model)[k] for k in Identity.model_fields}


class ContinuityReview(Reviewed):
    decision_id: UUID
    current_selections: Annotated[list[Selection], Field(min_length=1)]
    full_motion_reviewed: StrictBool
    cut_boundaries_reviewed: StrictBool
    findings: Annotated[list[Text], Field(min_length=1)]
