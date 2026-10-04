"""Codex hook guard for unauthenticated channel-shaped prompt text."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
import sys
from typing import Any, TextIO

from ..errors import ValidationError


_RAW_CHANNEL_MARKUP = re.compile(r"<channel(?:\s|>)", re.IGNORECASE)
_ALTERNATIVE = (
    "Use the configured nunchi-discord, nunchi-matrix, or nunchi-telegram "
    "native adapter; a custom text source must send a canonical delivery "
    "through HMAC-authenticated nunchi-channel ingress."
)


def evaluate(document: Any) -> dict[str, str] | None:
    """Return a Codex hook decision without deriving facts from prompt markup."""

    if not isinstance(document, Mapping):
        raise ValidationError("Codex hook input must be an object")
    if document.get("hook_event_name") != "UserPromptSubmit":
        raise ValidationError("Codex ingress guard requires UserPromptSubmit")
    prompt = document.get("prompt")
    if not isinstance(prompt, str):
        raise ValidationError("Codex UserPromptSubmit prompt must be a string")
    if not _RAW_CHANNEL_MARKUP.search(prompt):
        return None
    return {
        "decision": "block",
        "reason": (
            "Nunchi cannot authenticate native identity, mention, reply, reaction, "
            f"or continuity facts from raw <channel> prompt markup. {_ALTERNATIVE}"
        ),
    }


def main(
    argv: list[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    del argv
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        document = json.load(stdin)
        decision = evaluate(document)
    except (json.JSONDecodeError, ValidationError) as exc:
        print(f"Nunchi Codex ingress guard could not validate hook input: {exc}", file=stderr)
        return 2
    if decision is not None:
        print(json.dumps(decision, sort_keys=True, separators=(",", ":")), file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
