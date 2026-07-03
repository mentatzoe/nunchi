"""Shared demo OpenAI-compatible responder for nunchi platform adapters.

Extracted from the Matrix adapter so it can be reused by Telegram, Discord,
and any future platform adapter without copying code.

This is clearly labelled a DEMO — the adapter product is the gating loop.
Composition is pluggable; see individual adapter module docstrings for the
callback contract (trigger, history, gate_result) -> str | None.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request

from .channel import ChannelGateResult

logger = logging.getLogger("nunchi.adapters._responder")


def _demo_responder(
    trigger: dict,
    history: list[dict],
    gate_result: ChannelGateResult,
    *,
    agent_id: str,
    model: str,
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
    max_history_items: int = 8,
) -> str | None:
    """Demo responder: one OpenAI-compatible chat-completions call via urllib.

    Clearly labelled a DEMO — the adapter's product is the gating loop.
    Composition is pluggable; see the module docstring for the callback contract.
    """
    truncated = history[-max_history_items:] if len(history) > max_history_items else history
    transcript_lines = []
    for msg in truncated:
        author = msg.get("author") or "unknown"
        content = msg.get("content") or ""
        transcript_lines.append(f"[{author}]: {content}")
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no prior context)"

    system_prompt = (
        f"You are a participant agent named {agent_id}. "
        f"Reply with exactly one turn matching this guidance: {gate_result.run_shape} "
        "Plain text only — no markdown, no headers. "
        "You are in a shared channel; be brief and on-topic."
    )
    user_content = (
        f"Recent transcript:\n{transcript}\n\n"
        f"New message from {trigger.get('author', 'unknown')}:\n{trigger.get('content', '')}"
    )

    payload = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        logger.error("Demo responder HTTP %d: %s", exc.code, details[:200])
        return None
    except (socket.timeout, urllib.error.URLError, OSError) as exc:
        logger.error("Demo responder request failed: %s", exc)
        return None

    try:
        return body["choices"][0]["message"]["content"].strip() or None
    except (KeyError, IndexError, AttributeError):
        logger.error("Demo responder unexpected response shape: %s", str(body)[:200])
        return None
