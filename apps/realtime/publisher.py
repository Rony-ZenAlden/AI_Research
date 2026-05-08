"""Tiny Redis publisher used by other apps to push events to the Go realtime hub.

Wire format (UTF-8 JSON):
    {
      "type":  "<event_type>",   # e.g. "research.progress", "test.ping"
      "data":  { ... },          # arbitrary payload
      "ts":    1715212800        # unix seconds
    }

Channel:  "user:<user_id>"

The Go service does PSUBSCRIBE on "user:*", so we only need to PUBLISH —
no HTTP roundtrip, no protocol handshake.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _client


def publish_to_user(user_id: int, event_type: str, data: dict[str, Any] | None = None) -> int:
    """Publish an event to a specific user's WebSocket connections.

    Returns the number of subscribers Redis delivered to (>=1 if the user is
    online; 0 if no connections / the Go hub is down).
    """
    payload = json.dumps(
        {"type": event_type, "data": data or {}, "ts": int(time.time())},
        separators=(",", ":"),
    )
    channel = f"user:{int(user_id)}"
    try:
        delivered = _get_client().publish(channel, payload)
        logger.debug("publish to %s delivered=%s type=%s", channel, delivered, event_type)
        return int(delivered)
    except redis.RedisError:
        logger.exception("redis publish failed for channel=%s", channel)
        return 0
