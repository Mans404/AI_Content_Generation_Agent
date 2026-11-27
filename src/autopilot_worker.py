"""Worker process for autopilot runs.

Run it separately from the web app:  python -m src.autopilot_worker
With AUTOPILOT_ENABLED unset or not "true" it logs that it is disabled
and exits at once, so the flag (or simply not running this process) is the
kill switch. Run exactly one copy. At start, any run still marked running
is parked as needs_attention (a paid step may have happened) and is never
retried. Every post it schedules goes to Telegram review; this process
never publishes. Ctrl+C stops it after the current step.
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv


async def run() -> int:
    log = logging.getLogger(__name__)
    if os.environ.get("AUTOPILOT_ENABLED") != "true":
        log.info("AUTOPILOT_ENABLED is not true; autopilot worker not started")
        return 0
    from src.services import autopilot_runner as runner

    parked = await runner.recover_interrupted()
    if parked:
        log.warning("%d interrupted autopilot run(s) moved to needs_attention", parked)
    stop = asyncio.Event()
    try:
        await runner.run_loop(stop)
    finally:
        stop.set()
    return 0


def main() -> None:
    load_dotenv()
    if sys.platform == "win32":
        # psycopg's async driver cannot run on the default Proactor loop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logging.basicConfig(level=logging.INFO)
    try:
        code = asyncio.run(run())
    except KeyboardInterrupt:
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    main()
