"""Background SLA sweeper: auto-denies reviews past their SLA deadline."""

from __future__ import annotations

import asyncio
import logging

from paari.review.service import REVIEW

_log = logging.getLogger("paari.sla")


async def run_sla_sweeper(interval_seconds: int = 60) -> None:
    """Loop forever, auto-denying expired reviews every interval.

    Designed to be started as a FastAPI background task. On shutdown the
    loop exits cleanly.
    """
    while True:
        try:
            denied = await REVIEW.auto_deny_expired()
            if denied:
                _log.info("sla sweeper auto-denied %d review(s)", denied)
        except Exception as exc:  # noqa: BLE001 - sweeper must not crash the app
            _log.error("sla sweeper error: %s", exc)
        await asyncio.sleep(interval_seconds)
