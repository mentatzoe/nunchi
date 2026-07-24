"""Installed Telegram V2 adapter with bounded long-poll ingress."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from collections.abc import Mapping, Sequence
from urllib.parse import urlencode
import urllib.error
import urllib.request

from .. import __version__
from ..errors import NunchiError, ValidationError
from ..participant import TransportResult
from .runtime import CAPABILITIES, ReferenceAdapterRuntime, load_pinned_config


class TelegramTransport:
    def __init__(self, config: Mapping[str, object]) -> None:
        allowed = {"bot_token_env", "api_base", "poll_timeout_seconds"}
        if set(config) - allowed:
            raise ValidationError("Telegram transport config has unexpected fields")
        env_name = str(config.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
        token = os.environ.get(env_name)
        if not token:
            raise ValidationError(f"Telegram credential is absent from {env_name}")
        base = str(config.get("api_base", "https://api.telegram.org")).rstrip("/")
        self.base_url = f"{base}/bot{token}"
        self.poll_timeout = int(config.get("poll_timeout_seconds", 30))
        if self.poll_timeout < 1 or self.poll_timeout > 50:
            raise ValidationError("Telegram poll timeout must be within 1..50 seconds")

    def _call(self, method: str, payload: Mapping[str, object]):
        request = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=urlencode(payload).encode(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.poll_timeout + 10) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise OSError(f"Telegram {method} returned a non-success response")
        return result.get("result")

    def dispatch(self, *, action, wake) -> TransportResult:
        if action["kind"] not in ("message", "reply"):
            return TransportResult("unavailable", "Telegram reference adapter cannot perform this action")
        payload = {
            "chat_id": wake["room"]["id"],
            "text": action["text"],
        }
        if action["kind"] == "reply":
            native = action["target_event_id"].removeprefix("telegram:message:")
            _, _, message_id = native.rpartition(":")
            if not message_id:
                return TransportResult("failed", "Telegram reply target is not native")
            payload["reply_to_message_id"] = message_id
        try:
            result = self._call("sendMessage", payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            return TransportResult("failed", f"Telegram HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            return TransportResult("unknown", f"Telegram acknowledgement lost: {exc}")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        return TransportResult("sent", f"telegram:message:{wake['room']['id']}:{message_id}")

    def updates(self, offset: int | None):
        payload = {
            "timeout": self.poll_timeout,
            "allowed_updates": json.dumps(
                ["message", "channel_post", "my_chat_member", "chat_member"]
            ),
        }
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload)


def _parser():
    parser = argparse.ArgumentParser(prog="nunchi-telegram")
    parser.add_argument("--config")
    parser.add_argument(
        "--config-sha256",
        default=os.environ.get("NUNCHI_ADAPTER_CONFIG_SHA256"),
    )
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--stdin", action="store_true")
    return parser


def _static_probe():
    return {
        "product": "nunchi",
        "product_version": __version__,
        "generation": 2,
        "surface": "telegram",
        "capabilities": CAPABILITIES["telegram"],
        "configured": False,
        "v1_fallback": False,
    }


def _save_offset(path: Path, offset: int) -> None:
    temporary = path.with_suffix(".tmp")
    payload = str(offset).encode()
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("short Telegram offset write")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.config:
            if args.probe:
                print(json.dumps(_static_probe(), sort_keys=True, separators=(",", ":")))
                return 0
            raise ValidationError("--config is required")
        if not args.config_sha256:
            raise ValidationError("--config-sha256 is required")
        config = load_pinned_config(args.config, args.config_sha256)
        transport_raw = config.get("transport")
        if not isinstance(transport_raw, Mapping):
            raise ValidationError("Telegram config must contain transport")
        transport = TelegramTransport(transport_raw)
        runtime = ReferenceAdapterRuntime(
            surface="telegram",
            config=config,
            transport=transport,
        )
        if args.probe:
            probe = runtime.probe()
            probe["configured"] = True
            print(json.dumps(probe, sort_keys=True, separators=(",", ":")))
            return 0
        if args.stdin:
            failed = False
            for line in sys.stdin:
                if not line.strip():
                    continue
                try:
                    runtime.process(json.loads(line))
                except (json.JSONDecodeError, NunchiError, ValueError) as exc:
                    failed = True
                    print(f"telegram delivery error: {exc}", file=sys.stderr)
            return 1 if failed else 0

        offset_path = Path(config["state_directory"]) / "telegram-update-offset"
        offset = int(offset_path.read_text()) if offset_path.exists() else None
        while True:
            updates = transport.updates(offset)
            if not isinstance(updates, list):
                raise ValidationError("Telegram getUpdates result must be an array")
            first_sync = offset is None
            for update in updates:
                if not isinstance(update, Mapping) or not isinstance(update.get("update_id"), int):
                    continue
                runtime.process(update, live=not first_sync)
                offset = max(offset or 0, update["update_id"] + 1)
            if offset is not None:
                _save_offset(offset_path, offset)
            if args.once:
                return 0
    except (NunchiError, urllib.error.URLError, OSError, ValueError) as exc:
        print(f"telegram adapter error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
