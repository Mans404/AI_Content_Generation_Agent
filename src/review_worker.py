"""Worker process for the Telegram review loops.

Run it separately from the web app:  python -m src.review_worker
With REVIEW_FLOW_ENABLED unset or not "true" it logs that the flow is
disabled and exits at once, so the kill switch is the flag (or simply
not running this process). Bad configuration exits with status 2 and
names only the variables. Run exactly one copy: Telegram allows a single
poller per bot. Ctrl+C stops the loops; rows left mid-flight are moved
to needs_attention by the next enabled start, never retried blindly.
"""

import asyncio
import logging
import sys

from dotenv import load_dotenv

from src.review_runtime import ConfigError, ReviewRuntime, read_flags


async def run() -> int:
    flags = read_flags()
    if not flags.sender_poller:
        logging.getLogger(__name__).info(
            "REVIEW_FLOW_ENABLED is not true; review worker not started")
        return 0
    runtime = ReviewRuntime()
    try:
        runtime.start(flags)
    except ConfigError as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 2
    try:
        await asyncio.Event().wait()
    finally:
        await runtime.stop()
    return 0


def main() -> None:
    load_dotenv()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logging.basicConfig(level=logging.INFO)
    try:
        code = asyncio.run(run())
    except KeyboardInterrupt:
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    main()