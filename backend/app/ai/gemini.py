"""Thin wrapper around the Google Gen AI SDK (Vertex AI) with structured JSON output."""
from __future__ import annotations

import logging
import threading
from typing import TypeVar

from pydantic import BaseModel

from ..config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


_client = None
_lock = threading.Lock()


def client():
    """One shared client for the whole process, created once even when many threads start together.

    A genai.Client closes its HTTP connection when it is garbage-collected. With lru_cache, threads
    racing on the first call could each build a client; the extras were dropped mid-request and their
    cleanup closed the connection ("Cannot send a request, as the client has been closed").
    Keeping one strong module-level reference behind a lock prevents that.
    """
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                from google import genai  # imported lazily so mock mode needs no credentials
                from google.genai import types

                # The SDK does not retry by default. Retry rate limits (429) and overloads (5xx) with
                # exponential backoff, and give up on a single request after a few minutes.
                http = types.HttpOptions(
                    timeout=settings.request_timeout_s * 1000,
                    retry_options=types.HttpRetryOptions(attempts=6, initial_delay=2.0, max_delay=40.0,
                                                         http_status_codes=[408, 429, 500, 502, 503, 504]))
                _client = genai.Client(vertexai=True, project=settings.gcp_project or None,
                                       location=settings.gcp_location, http_options=http)
    return _client


def _reset_client():
    global _client
    with _lock:
        _client = None


def _call(model: str, contents: list, config):
    try:
        return client().models.generate_content(model=model, contents=contents, config=config)
    except RuntimeError as e:
        if "client has been closed" not in str(e):
            raise
        log.warning("Gemini HTTP client was closed; reconnecting and retrying once")
        _reset_client()
        return client().models.generate_content(model=model, contents=contents, config=config)


def png_part(data: bytes):
    from google.genai import types

    return types.Part.from_bytes(data=data, mime_type="image/png")


def generate_json(model: str, contents: list, schema: type[T], system: str | None = None,
                  thinking: str = "", max_tokens: int | None = None, cache: bool = False) -> T:
    """Call Gemini and force the reply into `schema`.

    Temperature is left at the model default: Google recommends the default for Gemini 3 models.
    `thinking` ("minimal", "low", "medium", "high") trades reasoning depth for speed.
    """
    from google.genai import types

    from . import cache as ai_cache

    ck = ai_cache.key("generate_json", model, schema.__name__, system, thinking, *contents) if cache else None
    if ck and (hit := ai_cache.get(ck)) is not None:
        return schema.model_validate(hit)
    out = _generate(types, model, contents, schema, system, thinking, max_tokens)
    if ck:
        ai_cache.put(ck, out.model_dump())
    return out


def _generate(types, model, contents, schema, system, thinking, max_tokens):
    kw = dict(response_mime_type="application/json", response_schema=schema, system_instruction=system,
              max_output_tokens=max_tokens or settings.max_output_tokens)
    if thinking:
        kw["thinking_config"] = types.ThinkingConfig(thinking_level=thinking.upper())
    try:
        resp = _call(model, contents, types.GenerateContentConfig(**kw))
    except Exception as e:  # noqa: BLE001 - some models reject a thinking level; retry with the default
        if thinking and "thinking" in str(e).lower():
            log.warning("thinking level %s rejected by %s; using model default", thinking, model)
            kw.pop("thinking_config")
            resp = _call(model, contents, types.GenerateContentConfig(**kw))
        else:
            raise
    if getattr(resp, "parsed", None) is not None:
        parsed = resp.parsed
        return parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
    if not resp.text:
        raise ValueError("Gemini returned an empty response")
    try:
        return schema.model_validate_json(resp.text)
    except ValueError:
        salvaged = salvage_truncated_json(resp.text)
        if salvaged is None:
            raise
        data, cut = salvaged
        log.warning("Gemini reply was cut off in field %r (runaway output); kept the complete fields", cut)
        if cut and "unreadable_fields" in schema.model_fields:
            data.setdefault("unreadable_fields", [])
            data["unreadable_fields"].append(cut)
        return schema.model_validate(data)


def salvage_truncated_json(text: str):
    """Recover the complete fields of a JSON object that was cut off mid-way.

    When a model gets stuck repeating a line, the output hits the token limit inside one string and
    the JSON never closes. Every field before that one is still valid: cut at the start of the last
    top-level key, close the object, and report which field was lost. Returns (data, lost_key) or None.
    """
    import json
    import re

    starts = [m.start() for m in re.finditer(r'\n\s{0,4}"(\w+)"\s*:', text)]
    for i in reversed(starts):
        head = text[:i].rstrip().rstrip(",")
        try:
            data = json.loads(head + "\n}")
        except ValueError:
            continue
        if isinstance(data, dict):
            m = re.match(r'\n\s{0,4}"(\w+)"', text[i:])
            return data, (m.group(1) if m else None)
    return None


def reason_json(contents: list, schema: type[T], system: str | None = None, thinking: str = "") -> T:
    """Use the stronger reasoning model, falling back to Flash if it is unavailable. Results are cached."""
    try:
        return generate_json(settings.model_reason, contents, schema, system, thinking=thinking, cache=True)
    except Exception as e:  # noqa: BLE001 - preview models can be removed or rate-limited
        log.warning("reasoning model failed (%s); falling back to %s", e, settings.model_reason_fallback)
        return generate_json(settings.model_reason_fallback, contents, schema, system, thinking=thinking, cache=True)
