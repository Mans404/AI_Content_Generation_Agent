"""State layer for one-shot autopilot runs. Dormant: no routes, no worker,
no network and no paid calls live here.

create_run validates everything BEFORE anything is stored or paid for:
the client's times (aware, 12 min to 30 days ahead, 1 to 10, no
duplicates), the idea count of the profile, the idempotency key, the one
active run per owner, and the monthly image budget (reserved up front in
a ledger). Transitions are conditional UPDATEs so one worker wins each
step. Nothing here talks to Facebook or Telegram.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from src.database.companies import async_session_factory
from src.models.companies import (
    AutopilotImageLedgerModel as L,
    AutopilotRunModel as Run,
    AutopilotRunPostModel as Post,
    DoctorModel,
    UserModel,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment,misc]

MAX_POSTS = 10
MONTHLY_IMAGE_CAP = 10
MONTHLY_REGEN_CAP = 10  # one regeneration per image, outside the 10
MIN_LEAD = timedelta(minutes=12)
MAX_AHEAD = timedelta(days=30)
MONTH_TZ = "Africa/Cairo"
ACTIVE = ("queued", "running", "needs_attention")
TERMINAL = ("completed", "partial", "failed", "cancelled")
STAGES = ("created", "planned", "prompts", "captions", "images", "stored", "scheduled")


class AutopilotError(Exception):
    def __init__(self, code: str, detail, run_id: UUID | None = None):
        super().__init__(code)
        self.code, self.detail, self.run_id = code, detail, run_id


class CreateResult(NamedTuple):
    run_id: UUID
    created: bool
    planned_posts: int
    planned_images: int
    times_utc: list


def _rowcount(result: Any) -> int:
    """session.execute() is typed Result[...], but UPDATE/DELETE/INSERT
    return a CursorResult at runtime, which is where rowcount lives."""
    return cast(CursorResult, result).rowcount


def month_key(now: datetime) -> str:
    try:
        local = now.astimezone(ZoneInfo(MONTH_TZ))
    except Exception:  # tzdata missing (Windows): fall back to UTC
        local = now.astimezone(timezone.utc)
    return f"{local.year:04d}-{local.month:02d}"


def normalize_times(raw, now: datetime) -> list:
    """Validate and return the UTC times sorted ascending, or raise
    AutopilotError('invalid_times', [(index, reason), ...])."""
    if not isinstance(raw, (list, tuple)) or not 1 <= len(raw) <= MAX_POSTS:
        raise AutopilotError(
            "invalid_times", [(None, f"send between 1 and {MAX_POSTS} times")]
        )
    errors: list[tuple[int | None, str]] = []
    utc: list[tuple[int, datetime]] = []
    for i, value in enumerate(raw):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            errors.append((i, "time must include a timezone offset"))
            continue
        value = value.astimezone(timezone.utc)
        if value < now + MIN_LEAD:
            errors.append((i, "must be at least 12 minutes from now"))
        elif value > now + MAX_AHEAD:
            errors.append((i, "must be within 30 days"))
        utc.append((i, value))
    seen: dict[datetime, int] = {}
    for i, value in utc:
        if value in seen:
            errors.append((i, f"duplicate of item {seen[value]}"))
        else:
            seen[value] = i
    if errors:
        raise AutopilotError("invalid_times", sorted(errors, key=lambda e: e[0] or 0))
    return sorted(v for _, v in utc)


def request_hash(company_id: UUID, times_utc) -> str:
    text = str(company_id) + "|" + ",".join(t.isoformat() for t in times_utc)
    return hashlib.sha256(text.encode()).hexdigest()


async def _balance(session, owner_id: UUID, month: str) -> tuple[int, int]:
    """(used, reserved) for the month."""
    used = await session.scalar(
        select(func.coalesce(func.sum(L.units), 0)).where(
            L.owner_id == owner_id, L.month_key == month, L.kind == "spend"
        )
    )
    reserved = await session.scalar(
        select(func.coalesce(func.sum(L.units), 0)).where(
            L.owner_id == owner_id, L.month_key == month, L.kind.in_(("reserve", "release"))
        )
    )
    return int(used), int(reserved)


async def preview_run(owner_id: UUID, raw_times, now: datetime | None = None) -> dict:
    """Dry run: same checks as create_run, writes nothing, spends nothing."""
    now = now or datetime.now(timezone.utc)
    result = {"valid": False, "errors": [], "planned_posts": 0, "planned_images": 0,
              "times_utc": [], "budget": None}
    try:
        times = normalize_times(raw_times, now)
    except AutopilotError as exc:
        result["errors"] = [list(e) for e in exc.detail]
        return result
    async with async_session_factory() as session:
        doctor = await session.scalar(select(DoctorModel).where(DoctorModel.owner_id == owner_id))
        if doctor is None:
            result["errors"] = [[None, "create a company profile first"]]
            return result
        ideas = doctor.posts_per_week * 4
        month = month_key(now)
        used, reserved = await _balance(session, owner_id, month)
    result.update(planned_posts=len(times), planned_images=len(times),
                  times_utc=[t.isoformat() for t in times],
                  budget={"cap": MONTHLY_IMAGE_CAP, "used": used, "reserved": reserved,
                          "available": MONTHLY_IMAGE_CAP - used - reserved, "month": month})
    if len(times) > ideas:
        result["errors"] = [[None, f"profile produces only {ideas} ideas"]]
    elif len(times) > MONTHLY_IMAGE_CAP - used - reserved:
        result["errors"] = [[None, "monthly image budget exceeded"]]
    else:
        result["valid"] = True
    return result


async def create_run(owner_id: UUID, idempotency_key: str, raw_times,
                     now: datetime | None = None) -> CreateResult:
    now = now or datetime.now(timezone.utc)
    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 64:
        raise AutopilotError("invalid_key", "idempotency_key must be 8 to 64 characters")
    times = normalize_times(raw_times, now)
    month = month_key(now)
    try:
        async with async_session_factory() as session:
            # Serialise this owner's budget decisions (no-op on SQLite).
            await session.scalar(
                select(UserModel.id).where(UserModel.id == owner_id).with_for_update())
            doctor = await session.scalar(
                select(DoctorModel).where(DoctorModel.owner_id == owner_id))
            if doctor is None:
                raise AutopilotError("no_company", "Create a company profile first.")
            digest = request_hash(doctor.id, times)
            existing = await session.scalar(
                select(Run).where(Run.owner_id == owner_id, Run.idempotency_key == key))
            if existing is not None:
                if existing.request_hash != digest:
                    raise AutopilotError("key_reused",
                                         "idempotency_key was used with different times",
                                         existing.id)
                return CreateResult(existing.id, False, existing.planned_posts,
                                    existing.planned_images, times)
            active = await session.scalar(
                select(Run).where(Run.owner_id == owner_id, Run.status.in_(ACTIVE)))
            if active is not None:
                raise AutopilotError("active_run", "another run is still active", active.id)
            if len(times) > doctor.posts_per_week * 4:
                raise AutopilotError("too_many_posts",
                                     f"profile produces only {doctor.posts_per_week * 4} ideas")
            used, reserved = await _balance(session, owner_id, month)
            available = MONTHLY_IMAGE_CAP - used - reserved
            if len(times) > available:
                raise AutopilotError("budget", {"cap": MONTHLY_IMAGE_CAP, "used": used,
                                                "reserved": reserved, "requested": len(times)})
            run = Run(owner_id=owner_id, company_id=doctor.id, idempotency_key=key,
                      request_hash=digest, month_key=month, planned_posts=len(times),
                      planned_images=len(times))
            session.add(run)
            await session.flush()
            session.add_all(Post(run_id=run.id, position=i, scheduled_for=t)
                            for i, t in enumerate(times))
            session.add(L(owner_id=owner_id, month_key=month, kind="reserve",
                          units=len(times), run_id=run.id))
            run_id = run.id  # read before commit expires the instance
            await session.commit()
            return CreateResult(run_id, True, len(times), len(times), times)
    except IntegrityError:
        # Lost a race on (owner, key) or the one-active-run index.
        async with async_session_factory() as session:
            row = await session.scalar(select(Run).where(
                Run.owner_id == owner_id, Run.idempotency_key == key))
            if row is not None:
                if row.request_hash != request_hash(row.company_id, times):
                    raise AutopilotError("key_reused",
                                         "idempotency_key was used with different times",
                                         row.id)
                return CreateResult(row.id, False, row.planned_posts,
                                    row.planned_images, times)
            active = await session.scalar(
                select(Run).where(Run.owner_id == owner_id, Run.status.in_(ACTIVE)))
        raise AutopilotError("active_run", "another run is still active",
                             active.id if active else None)


async def claim_run() -> UUID | None:
    """queued -> running for the oldest queued run; one worker wins.

    FOR UPDATE SKIP LOCKED already guarantees exclusivity, so the row is
    simply updated in place.
    """
    async with async_session_factory() as session:
        run = (await session.execute(
            select(Run).where(Run.status == "queued").order_by(Run.created_at)
            .limit(1).with_for_update(skip_locked=True))).scalars().first()
        if run is None:
            return None
        run_id = run.id  # read before commit expires the instance
        run.status = "running"
        run.updated_at = func.now()
        await session.commit()
        return run_id


async def advance_stage(run_id: UUID, expected: str, new: str) -> bool:
    if expected not in STAGES or new not in STAGES or STAGES.index(new) != STAGES.index(expected) + 1:
        raise ValueError("stages advance one step at a time")
    async with async_session_factory() as session:
        res = await session.execute(
            update(Run).where(Run.id == run_id, Run.status == "running", Run.stage == expected)
            .values(stage=new, updated_at=func.now()))
        await session.commit()
        return _rowcount(res) == 1


async def set_ideas_id(run_id: UUID, ideas_id: UUID) -> bool:
    """Set once, right after planning. A later call with another id fails."""
    async with async_session_factory() as session:
        res = await session.execute(
            update(Run).where(Run.id == run_id, Run.status == "running", Run.ideas_id.is_(None))
            .values(ideas_id=ideas_id, updated_at=func.now()))
        await session.commit()
        return _rowcount(res) == 1


async def _release_rest(session, run: Run) -> None:
    reserved = await session.scalar(
        select(func.coalesce(func.sum(L.units), 0)).where(
            L.run_id == run.id, L.kind.in_(("reserve", "release"))))
    if reserved and reserved > 0:
        session.add(L(owner_id=run.owner_id, month_key=run.month_key, kind="release",
                      units=-int(reserved), run_id=run.id))


async def finish_run(run_id: UUID, status: str, error: str | None = None) -> bool:
    """running|needs_attention -> completed|partial|failed|cancelled. Unused
    reservation is released, except for needs_attention (a paid call may
    have happened) which keeps it."""
    if status not in TERMINAL and status != "needs_attention":
        raise ValueError("bad status")
    async with async_session_factory() as session:
        run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        allowed: tuple[str, ...]
        if status == "cancelled":
            allowed = ("queued", "running", "needs_attention")
        elif status == "needs_attention":
            allowed = ("running",)
        else:
            allowed = ("running", "needs_attention")
        if run is None or run.status not in allowed:
            return False
        run.status = status
        run.last_error = error[:1024] if error else None
        run.updated_at = datetime.now(timezone.utc)
        if status != "needs_attention":
            await _release_rest(session, run)
        await session.commit()
        return True


async def record_image_generated(run_id: UUID, position: int, generation_id: UUID) -> bool:
    """pending|generating -> done for one post; moves one unit from reserved
    to used. Idempotent: a second call changes nothing."""
    async with async_session_factory() as session:
        run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if run is None or run.status not in ("running", "needs_attention"):
            return False
        res = await session.execute(
            update(Post).where(Post.run_id == run_id, Post.position == position,
                               Post.image_state.in_(("pending", "generating")))
            .values(image_state="done", generation_id=generation_id))
        if _rowcount(res) != 1:
            await session.rollback()
            return False
        session.add(L(owner_id=run.owner_id, month_key=run.month_key, kind="spend",
                      units=1, run_id=run_id, post_position=position))
        session.add(L(owner_id=run.owner_id, month_key=run.month_key, kind="release",
                      units=-1, run_id=run_id, post_position=position))
        await session.commit()
        return True


async def mark_post(run_id: UUID, position: int, expected: str, new: str,
                    error: str | None = None, schedule_id: UUID | None = None) -> bool:
    """Conditional post_state change (pending -> scheduled | failed | slot_expired ...)."""
    values: dict[str, Any] = {"post_state": new, "error": error[:1024] if error else None}
    if schedule_id is not None:
        values["schedule_id"] = schedule_id
    async with async_session_factory() as session:
        res = await session.execute(
            update(Post).where(Post.run_id == run_id, Post.position == position,
                               Post.post_state == expected).values(**values))
        await session.commit()
        return _rowcount(res) == 1

async def mark_image_failed(run_id: UUID, position: int, error: str) -> bool:
    """pending|generating -> failed for one post (image and post together)."""
    async with async_session_factory() as session:
        res = await session.execute(
            update(Post).where(Post.run_id == run_id, Post.position == position,
                               Post.image_state.in_(("pending", "generating")))
            .values(image_state="failed", post_state="failed", error=error[:1024]))
        await session.commit()
        return _rowcount(res) == 1


async def month_balance(owner_id: UUID, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    month = month_key(now)
    async with async_session_factory() as session:
        used, reserved = await _balance(session, owner_id, month)
        regens = int(await session.scalar(
            select(func.coalesce(func.sum(L.units), 0)).where(
                L.owner_id == owner_id, L.month_key == month, L.kind == "regen")) or 0)
    return {"month": month, "cap": MONTHLY_IMAGE_CAP, "used": used, "reserved": reserved,
            "available": MONTHLY_IMAGE_CAP - used - reserved,
            "regen_cap": MONTHLY_REGEN_CAP, "regens": regens}


async def reserve_regen(owner_id: UUID, generation_id: UUID,
                        now: datetime | None = None) -> str:
    """Record one paid regeneration BEFORE it is made. Returns 'ok',
    'already_regenerated' (one per image) or 'budget' (monthly regen cap).
    Counted from the first call, so a crash after paying never gives a free
    second try; use refund_regen only when the provider returned nothing."""
    now = now or datetime.now(timezone.utc)
    month = month_key(now)
    async with async_session_factory() as session:
        # Serialise this owner's regen decisions (no-op on SQLite).
        await session.scalar(
            select(UserModel.id).where(UserModel.id == owner_id).with_for_update())
        had = await session.scalar(select(func.count()).select_from(L).where(
            L.owner_id == owner_id, L.kind == "regen", L.generation_id == generation_id))
        if had:
            return "already_regenerated"
        used = int(await session.scalar(
            select(func.coalesce(func.sum(L.units), 0)).where(
                L.owner_id == owner_id, L.month_key == month, L.kind == "regen")) or 0)
        if used >= MONTHLY_REGEN_CAP:
            return "budget"
        session.add(L(owner_id=owner_id, month_key=month, kind="regen", units=1,
                      generation_id=generation_id))
        await session.commit()
        return "ok"


async def refund_regen(owner_id: UUID, generation_id: UUID) -> bool:
    """Undo a regen record when the provider returned no image."""
    async with async_session_factory() as session:
        row = await session.scalar(select(L).where(
            L.owner_id == owner_id, L.kind == "regen", L.generation_id == generation_id
        ).limit(1).with_for_update())
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True

async def cancel_idle_run(run_id: UUID) -> bool:
    """Cancel a run that is queued or parked (needs_attention). A running run
    is never cancelled here: its images may already be paid. The unused
    reservation is released."""
    async with async_session_factory() as session:
        run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if run is None or run.status not in ("queued", "needs_attention"):
            return False
        run.status, run.last_error = "cancelled", "cancelled by the user"
        run.updated_at = datetime.now(timezone.utc)
        await _release_rest(session, run)
        await session.commit()
        return True