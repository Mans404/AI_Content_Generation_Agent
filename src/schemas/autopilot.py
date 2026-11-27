from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AutopilotPreviewRequest(BaseModel):
    scheduled_for: list[datetime]


class AutopilotRunRequest(BaseModel):
    scheduled_for: list[datetime]
    idempotency_key: str


class AutopilotRescheduleRequest(BaseModel):
    scheduled_for: datetime


class AutopilotPreviewResponse(BaseModel):
    valid: bool
    errors: list[list[int | str | None]]
    planned_posts: int
    planned_images: int
    times_utc: list[str]
    budget: dict | None = None


class AutopilotRunResponse(BaseModel):
    run_id: UUID
    status: str
    created: bool
    planned_posts: int
    planned_images: int


class AutopilotPostStatus(BaseModel):
    position: int
    scheduled_for: datetime
    image_state: str
    post_state: str
    error: str | None = None
    generation_id: UUID | None = None
    schedule_id: UUID | None = None
    review_status: str | None = None
    image_url: str | None = None
    caption: str | None = None


class AutopilotRunStatus(BaseModel):
    run_id: UUID
    status: str
    stage: str
    planned_posts: int
    planned_images: int
    last_error: str | None = None
    created_at: datetime | None = None
    posts: list[AutopilotPostStatus]
    budget: dict

class AutopilotRunSummary(BaseModel):
    run_id: UUID
    status: str
    stage: str
    planned_posts: int
    planned_images: int
    last_error: str | None = None
    created_at: datetime | None = None