"""Cache of Gemini results, keyed by a hash of exactly what was sent.

The same PDF bytes with the same model, schema and prompt always map to the same key, so a document
that has already been read (or a wording comparison already judged) comes back instantly and costs
nothing. Anything that changes the input, model or prompt gives a new key, so stale results are
never reused. Stored next to uploaded files: local disk in development, Cloud Storage on Cloud Run,
so the cache is shared by every Cloud Run instance and survives restarts.

Turn off with AI_CACHE=off (the benchmark turns it off itself so its timings are real).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

VERSION = "1"  # bump to invalidate every cached result after a prompt or schema change
enabled = os.getenv("AI_CACHE", "on").strip().lower() not in {"0", "off", "false", "no"}


def key(*parts: Any) -> str:
    h = hashlib.sha256(VERSION.encode())
    for p in parts:
        if isinstance(p, (bytes, bytearray)):
            h.update(hashlib.sha256(p).digest())
        elif hasattr(p, "inline_data") and getattr(p, "inline_data", None) is not None:  # genai Part with an image
            h.update(hashlib.sha256(p.inline_data.data).digest())
        else:
            h.update(json.dumps(p, sort_keys=True, default=str).encode())
        h.update(b"\x00")
    return h.hexdigest()


def get(k: str) -> Optional[Any]:
    if not enabled:
        return None
    from .. import storage

    try:
        raw = storage.files().get(f"_ai_cache/{k}.json")
        return json.loads(raw) if raw else None
    except Exception as e:  # noqa: BLE001 - a broken cache must never break a check
        log.warning("AI cache read failed: %s", e)
        return None


def put(k: str, value: Any) -> None:
    if not enabled:
        return
    from .. import storage

    try:
        storage.files().put(f"_ai_cache/{k}.json", json.dumps(value).encode())
    except Exception as e:  # noqa: BLE001
        log.warning("AI cache write failed: %s", e)
