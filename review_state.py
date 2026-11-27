import asyncio
import sys
from collections import Counter

from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
load_dotenv()


async def go():
    from sqlalchemy import select

    from src.database.companies import async_session_factory
    from src.models.companies import (
        FacebookPostScheduleModel as F,
        TelegramPostReviewModel as R,
    )

    async with async_session_factory() as session:
        rows = (await session.execute(select(R))).scalars().all()
        print("reviews by status:", dict(Counter(r.status for r in rows)))
        for r in rows:
            sched = await session.get(F, r.schedule_id)
            fb = sched.facebook_post_id if sched is not None else None
            print(str(r.schedule_id)[:8], "|", r.status, "| facebook_post_id:", fb,
                  "|", (r.last_error or "")[:80])


asyncio.run(go())