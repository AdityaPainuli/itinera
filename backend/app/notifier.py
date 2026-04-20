"""Fire-and-forget webhook notifications.

Used to ping the operator when the daily quota is hit. The webhook URL is
shape-detected so the same env var works for Discord, Slack, and generic
JSON receivers (ntfy.sh, Make/Zapier, your own endpoint, etc.).

Setup hints (pick one — all free):
- Discord: server settings → Integrations → Webhooks → New Webhook → copy URL
- Slack:   api.slack.com/messaging/webhooks (workspace admin needed)
- ntfy.sh: just pick a topic name and POST to https://ntfy.sh/<topic>; subscribe
           on your phone via the ntfy app.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx

from app.config import settings

log = logging.getLogger(__name__)


def _build_payload(url: str, message: str) -> dict:
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        return {"content": message}
    if "hooks.slack.com" in url:
        return {"text": message}
    # Generic — include both common keys so most receivers find one they like.
    # ntfy.sh just reads the request body as the message regardless of shape.
    return {"text": message, "content": message, "message": message}


async def _post(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                log.warning(
                    "notification webhook returned %s: %s", resp.status_code, resp.text[:200]
                )
    except Exception as exc:  # noqa: BLE001 — never let webhook errors leak out
        log.warning("notification webhook failed: %s", exc)


def notify_limit_reached(count: int, limit: int, reset_at: datetime) -> None:
    """Schedule a fire-and-forget webhook ping. Returns immediately.

    Silently no-ops if NOTIFY_WEBHOOK_URL is unset, so it's safe to call
    unconditionally from the request handler.
    """
    url = settings.notify_webhook_url
    if not url:
        return

    message = (
        f":rotating_light: Itinera daily limit reached ({count}/{limit}). "
        f"Resets at {reset_at:%Y-%m-%d %H:%M UTC}. "
        f"To bump it now: `UPDATE rate_limits SET count = 0, notified_at = NULL WHERE id = 1;`"
    )
    payload = _build_payload(url, message)

    # Fire-and-forget: don't block the response on the webhook round-trip.
    # The task is referenced by the running loop until it completes; we don't
    # need to await or store it.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_post(url, payload))
    except RuntimeError:
        # No running loop (shouldn't happen inside a FastAPI handler, but be safe).
        log.warning("no running loop for notification; dropping")
