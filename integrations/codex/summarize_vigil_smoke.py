#!/usr/bin/env python3
"""Summarize a Vigil live-smoke receipt log into evidence markdown.

This intentionally treats smoke success as a two-surface claim:

- runner admitted a room trigger and `codex exec` exited successfully
- outbound Codex hook allowed a room send for that admitted trigger

The output never includes message content.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOW_ACTIONS = {"allow-speak", "allow-ask", "allow-ack"}


def _load_receipts(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"cannot read receipt log {path}: {exc}") from exc
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSON on receipt line {lineno}: {exc}") from exc
        if isinstance(record, dict):
            records.append(record)
    return records


def _matches_channel(record: dict[str, Any], channel: str) -> bool:
    return str(record.get("channel") or "") == channel


def _first_wake(
    records: list[dict[str, Any]],
    channel: str,
    trigger_message_id: str | None = None,
) -> dict[str, Any] | None:
    for record in records:
        if (
            _matches_channel(record, channel)
            and record.get("action") == "wake-ok"
            and record.get("wake_exit") == 0
            and record.get("verdict") in {"SPEAK", "ASK", "ACK"}
        ):
            if trigger_message_id and str(record.get("message_id") or "") != trigger_message_id:
                continue
            return record
    return None


def _first_outbound_allow(
    records: list[dict[str, Any]],
    channel: str,
    trigger_message_id: str | None,
) -> dict[str, Any] | None:
    for record in records:
        if not _matches_channel(record, channel):
            continue
        if record.get("direction") != "hook-outbound":
            continue
        if record.get("action") not in ALLOW_ACTIONS:
            continue
        if trigger_message_id and record.get("trigger_message_id") != trigger_message_id:
            continue
        return record
    return None


def _count_action(records: list[dict[str, Any]], channel: str, action: str) -> int:
    return sum(1 for record in records if _matches_channel(record, channel) and record.get("action") == action)


def build_summary(
    records: list[dict[str, Any]],
    channel: str,
    *,
    trigger_message_id: str | None = None,
    reply_message_id: str | None = None,
) -> str:
    wake = _first_wake(records, channel, trigger_message_id)
    if wake is None:
        raise RuntimeError(
            f"no successful wake-ok receipt found for channel {channel}"
            + (f" and trigger {trigger_message_id}" if trigger_message_id else "")
        )
    trigger_id = str(wake.get("message_id") or "")
    outbound = _first_outbound_allow(records, channel, trigger_id or None)
    if outbound is None:
        raise RuntimeError(
            f"no outbound hook allow receipt found for channel {channel}"
            + (f" and trigger {trigger_id}" if trigger_id else "")
        )

    pass_count = _count_action(records, channel, "pass-suppressed")
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Codex Vigil live smoke evidence",
        "",
        f"Generated: {now}",
        "",
        "Result: successful.",
        "",
        "| Check | Evidence |",
        "|---|---|",
        (
            "| Runner admitted room turn | "
            f"`action={wake.get('action')}`, `verdict={wake.get('verdict')}`, "
            f"`wake_exit={wake.get('wake_exit')}`, `message_id={trigger_id}` |"
        ),
        (
            "| Outbound hook allowed room send | "
            f"`direction={outbound.get('direction')}`, `action={outbound.get('action')}`, "
            f"`verdict={outbound.get('verdict')}`, "
            f"`trigger_message_id={outbound.get('trigger_message_id')}` |"
        ),
    ]
    if reply_message_id:
        lines.append(f"| Discord room delivery confirmed | `reply_message_id={reply_message_id}` |")
    lines += [
        f"| PASS suppression seen | `{pass_count}` receipt(s) |",
        "",
        f"Channel: `{channel}`",
        "",
        "Message bodies were intentionally omitted from this evidence file.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize Codex/Vigil live-smoke receipts without message content."
    )
    parser.add_argument("--log", required=True, help="Path to codex-runner-receipts.jsonl")
    parser.add_argument("--channel", default="1522258711047831653", help="Discord channel id")
    parser.add_argument("--trigger-message-id", help="Require evidence for this trigger message id")
    parser.add_argument("--reply-message-id", help="Discord message id observed as the delivered reply")
    parser.add_argument("--out", help="Markdown output path. Defaults to stdout.")
    args = parser.parse_args(argv)

    try:
        summary = build_summary(
            _load_receipts(Path(args.log)),
            str(args.channel),
            trigger_message_id=args.trigger_message_id,
            reply_message_id=args.reply_message_id,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")
    else:
        print(summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
