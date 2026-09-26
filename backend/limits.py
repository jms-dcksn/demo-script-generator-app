"""Per-IP daily usage limits.

Calendar-day UTC window. Uses Redis when REDIS_URL is set so counts survive
Fly auto-stop / redeploy; otherwise an in-process dict (local/pytest).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

MAX_MESSAGES_PER_IP = int(os.getenv("MAX_MESSAGES_PER_IP", "20"))
MAX_THREADS_PER_IP = int(os.getenv("MAX_THREADS_PER_IP", "8"))
LIMIT_DETAIL = "You've reached the free demo limit. Thanks for trying it out!"

_mem: dict[str, int] = {}
_redis_client: Any = None


def _day_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _ttl_seconds() -> int:
    now = datetime.now(timezone.utc)
    nxt = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    return int((nxt - now).total_seconds()) + 60


def _key(kind: str, ip: str) -> str:
    return f"dsg:{kind}:{ip}:{_day_stamp()}"


def _redis() -> Any:
    global _redis_client
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    if _redis_client is None:
        import redis

        _redis_client = redis.Redis.from_url(url, decode_responses=True)
    return _redis_client


def _get(key: str) -> int:
    r = _redis()
    if r is not None:
        raw = r.get(key)
        return int(raw) if raw else 0
    return _mem.get(key, 0)


def _incr(key: str) -> int:
    r = _redis()
    if r is not None:
        n = int(r.incr(key))
        if n == 1:
            r.expire(key, _ttl_seconds())
        return n
    _mem[key] = _mem.get(key, 0) + 1
    return _mem[key]


def message_count(ip: str) -> int:
    return _get(_key("msg", ip))


def thread_count(ip: str) -> int:
    return _get(_key("thr", ip))


def at_message_limit(ip: str) -> bool:
    return message_count(ip) >= MAX_MESSAGES_PER_IP


def at_thread_limit(ip: str) -> bool:
    return thread_count(ip) >= MAX_THREADS_PER_IP


def increment_message(ip: str) -> int:
    return _incr(_key("msg", ip))


def increment_thread(ip: str) -> int:
    return _incr(_key("thr", ip))


def usage_payload(ip: str) -> dict[str, int]:
    used = message_count(ip)
    threads_used = thread_count(ip)
    return {
        "used": used,
        "limit": MAX_MESSAGES_PER_IP,
        "remaining": max(0, MAX_MESSAGES_PER_IP - used),
        "threads_used": threads_used,
        "threads_limit": MAX_THREADS_PER_IP,
        "threads_remaining": max(0, MAX_THREADS_PER_IP - threads_used),
    }


def reset_limits() -> None:
    """Clear in-memory counts and drop any cached Redis client. Tests only."""
    global _redis_client
    _mem.clear()
    _redis_client = None
