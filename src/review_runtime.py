"""Runtime for the Telegram review loops: flags, config checks, supervisor.

Everything is OFF by default. REVIEW_FLOW_ENABLED=true starts the sender
and the callback poller only. REVIEW_PUBLISH_ENABLED=true (publishes to
Facebook) and REVIEW_REGENERATE_ENABLED=true (one paid image generation
per rejected review) each add one more loop, and only count while the
master flag is on. Any other value, or no value, means off.

validate_config runs before any loop is created. It refuses to start on
any problem and reports variable NAMES only, never values. With
publishing on, TELEGRAM_REVIEW_PAGE_ID must be set and equal
FACEBOOK_PAGE_ID: that is the owner-to-page binding, so the one
configured review owner can only publish to the one page named here.

The heavy modules (database, storage, Telegram, Facebook) are imported
only when a loop is built, so with the flags off nothing is imported or
started. The supervisor restarts a loop that crashes with a growing
delay and logs the exception class only. start is idempotent: a second
call never creates a second poller. Nothing here talks to Telegram or
Facebook by itself; the loops do, once started.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping
from uuid import UUID

logger = logging.getLogger(__name__)

ON = "true"
MAX_BACKOFF_SECONDS = 60.0


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Flags:
    sender_poller: bool
    publish: bool
    regenerate: bool


def read_flags(env: Mapping[str, str] | None = None) -> Flags:
    env = os.environ if env is None else env
    master = env.get("REVIEW_FLOW_ENABLED") == ON
    return Flags(
        sender_poller=master,
        publish=master and env.get("REVIEW_PUBLISH_ENABLED") == ON,
        regenerate=master and env.get("REVIEW_REGENERATE_ENABLED") == ON,
    )


def _bad_uuid(value: str | None) -> bool:
    try:
        UUID(value or "")
    except ValueError:
        return True
    return False


def _bad_int(value: str | None) -> bool:
    try:
        int(value or "")
    except ValueError:
        return True
    return False


def config_problems(flags: Flags, env: Mapping[str, str] | None = None) -> list[str]:
    """Names of invalid or missing variables for the enabled loops."""
    env = os.environ if env is None else env
    problems: list[str] = []
    if flags.sender_poller:
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            if not env.get(name):
                problems.append(name)
        if _bad_int(env.get("TELEGRAM_REVIEWER_USER_ID")):
            problems.append("TELEGRAM_REVIEWER_USER_ID")
        if _bad_uuid(env.get("TELEGRAM_REVIEW_OWNER_ID")):
            problems.append("TELEGRAM_REVIEW_OWNER_ID")
    if flags.publish:
        for name in ("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN",
                     "TELEGRAM_REVIEW_PAGE_ID"):
            if not env.get(name):
                problems.append(name)
        bound = env.get("TELEGRAM_REVIEW_PAGE_ID")
        if bound and bound != env.get("FACEBOOK_PAGE_ID"):
            problems.append("TELEGRAM_REVIEW_PAGE_ID (must equal FACEBOOK_PAGE_ID)")
    if flags.regenerate and not env.get("OPENROUTER_API_KEY"):
        problems.append("OPENROUTER_API_KEY")
    return problems


def validate_config(flags: Flags, env: Mapping[str, str] | None = None) -> None:
    problems = config_problems(flags, env)
    if problems:
        raise ConfigError(
            "Invalid review configuration: " + ", ".join(problems))
LoopFactory = Callable[[], Awaitable[None]]


def build_loops(flags: Flags) -> dict[str, LoopFactory]:
    """Zero-argument loop starters for the enabled flags; imports lazily."""
    loops: dict[str, LoopFactory] = {}
    if flags.sender_poller:
        from src.services import telegram_poller, telegram_sender
        from src.services.telegram_bot import TelegramBot

        bot = TelegramBot()
        loops["sender"] = lambda: telegram_sender.run_review_sender_loop(bot)
        loops["poller"] = lambda: telegram_poller.run_callback_poller(bot)
    if flags.publish:
        from src.services import review_publisher
        from src.services.facebook_review_client import ReviewPagePublisher

        publisher = ReviewPagePublisher()
        loops["publisher"] = (
            lambda: review_publisher.run_review_publisher_loop(publisher))
    if flags.regenerate:
        from src.agents.design_image_agent import design_image_agent
        from src.services import review_regenerator

        loops["regenerator"] = (
            lambda: review_regenerator.run_review_regenerator_loop(
                design_image_agent))
    return loops


async def _supervise(
    name: str, factory: LoopFactory, base_delay: float = 2.0
) -> None:
    failures = 0
    while True:
        try:
            await factory()
            logger.error("Review loop %s ended unexpectedly", name)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            logger.error(
                "Review loop %s crashed: %s", name, type(exc).__name__)
            await asyncio.sleep(
                min(MAX_BACKOFF_SECONDS, base_delay * 2 ** (failures - 1)))


class ReviewRuntime:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def running(self) -> list[str]:
        return sorted(self._tasks)

    def start(self, flags: Flags | None = None) -> list[str]:
        """Validate, build and start the enabled loops; returns their names.

        Does nothing when the flags are off or the runtime already
        started. Raises ConfigError before creating any task."""
        if self._tasks:
            return self.running
        flags = flags or read_flags()
        if not flags.sender_poller:
            logger.info("Review flow is disabled; no loops started")
            return []
        validate_config(flags)
        for name, factory in build_loops(flags).items():
            self._tasks[name] = asyncio.create_task(
                _supervise(name, factory), name=f"review-{name}")
        logger.info("Review loops started: %s", ", ".join(self.running))
        return self.running

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks = {}
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)