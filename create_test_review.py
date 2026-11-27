"""Create ONE test review for an existing scheduled post of your owner.

Run from the project root. Reads TELEGRAM_REVIEW_OWNER_ID from .env.
It never contacts Facebook, Telegram or OpenRouter: it only writes one
row to your database, through the app's own state layer.

  python create_test_review.py                  list your scheduled posts
  python create_test_review.py --create POST_ID create the review
  python create_test_review.py --create POST_ID --make-due
        same, and also set the post's scheduled time to now when it is
        still in the future (prints the old time so you can restore it)

The running sender picks the review up on its next pass (about 30 s)
and sends it to your Telegram chat.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select, update  # noqa: E402

from src.database.companies import async_session_factory  # noqa: E402
from src.models.companies import (  # noqa: E402
    DesignImageGenerationModel as G,
    DoctorModel as D,
    FacebookPostScheduleModel as F,
    TelegramPostReviewModel as R,
)
from src.services import telegram_reviews as tr  # noqa: E402


def owner_from_env() -> UUID:
    try:
        return UUID(os.environ.get("TELEGRAM_REVIEW_OWNER_ID", ""))
    except ValueError:
        raise SystemExit(
            "TELEGRAM_REVIEW_OWNER_ID is missing or not a valid UUID.") from None


def short(text: str, width: int = 40) -> str:
    one_line = " ".join((text or "").split())
    return one_line if len(one_line) <= width else one_line[: width - 3] + "..."


async def list_posts(owner_id: UUID, out) -> int:
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(F.id, F.status, F.scheduled_for, F.caption, R.status)
            .outerjoin(R, R.schedule_id == F.id)
            .where(F.owner_id == owner_id)
            .order_by(F.scheduled_for.desc()).limit(20))).all()
    if not rows:
        out("No scheduled posts found for this owner.")
        return 0
    out("post id | post status | scheduled for | review | caption")
    for sid, status, when, caption, review in rows:
        out(f"{sid} | {status} | {when} | {review or '-'} | {short(caption)}")
    return 0


async def create_review(owner_id: UUID, raw_id: str, make_due: bool, out) -> int:
    try:
        schedule_id = UUID(raw_id)
    except ValueError:
        out("That is not a valid post id.")
        return 1
    now = datetime.now(timezone.utc)
    changed = False
    old_time = now
    async with async_session_factory() as session:
        row = (await session.execute(
            select(F, G.stored, G.company_id, D.owner_id, R.id)
            .join(G, G.id == F.generation_id)
            .join(D, D.id == G.company_id)
            .outerjoin(R, R.schedule_id == F.id)
            .where(F.id == schedule_id, F.owner_id == owner_id))).first()
        if row is None:
            out("No such scheduled post for this owner. Nothing created.")
            return 1
        schedule, stored, gen_company, company_owner, review_id = row
        if review_id is not None:
            out("A review already exists for this post. Nothing created.")
            return 1
        if (not stored or company_owner != owner_id
                or gen_company != schedule.company_id):
            out("The post's image or company does not check out. Nothing created.")
            return 1
        if schedule.facebook_post_id is not None:
            out("This post already has a Facebook post id. Nothing created.")
            return 1
        old_time = schedule.scheduled_for
        aware = old_time if old_time.tzinfo else old_time.replace(tzinfo=timezone.utc)
        if aware > now:
            if not make_due:
                out(f"This post is scheduled for {old_time}, in the future."
                    " Add --make-due to set it to now. Nothing created.")
                return 1
            await session.execute(
                update(F).where(F.id == schedule_id).values(scheduled_for=now))
            await session.commit()
            changed = True
            out(f"scheduled_for changed: {old_time} -> {now}")
        generation_id = schedule.generation_id
    created = await tr.create_review(owner_id, schedule_id, generation_id)
    restore = ""
    if changed:
        restore = (f"  UPDATE facebook_post_schedules SET scheduled_for = '{old_time}'"
                   f" WHERE id = '{schedule_id}';")
    if not created:
        out("A review already exists for this post. No review created.")
        if changed:
            out("The schedule time was changed; to restore it:")
            out(restore)
        return 1
    async with async_session_factory() as session:
        review = await session.scalar(select(R).where(R.schedule_id == schedule_id))
    if review is None:
        out("Review row not found after creating it; check the table.")
        return 1
    out(f"Created review {review.id} (status {review.status}) for post {schedule_id}.")
    out("The sender will pick it up within about 30 seconds.")
    out("To undo, only while its status is pending or awaiting_approval:")
    out(f"  DELETE FROM telegram_post_reviews WHERE id = '{review.id}'"
        " AND status IN ('pending', 'awaiting_approval');")
    if changed:
        out("To restore the schedule time:")
        out(restore)
    return 0


async def run(argv: list[str], out=print) -> int:
    parser = argparse.ArgumentParser(description="Create one test review.")
    parser.add_argument("--create", metavar="POST_ID")
    parser.add_argument("--make-due", action="store_true")
    args = parser.parse_args(argv)
    owner_id = owner_from_env()
    if args.create:
        return await create_review(owner_id, args.create, args.make_due, out)
    return await list_posts(owner_id, out)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(run(sys.argv[1:])))
