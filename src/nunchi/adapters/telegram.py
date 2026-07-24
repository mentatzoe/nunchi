"""Installed Telegram V2 adapter with bounded long-poll ingress."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
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
            return TransportResult("failed", f"Telegram returned HTTP {exc.code}")
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return TransportResult("unknown", "Telegram acknowledgement was lost")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        return TransportResult("sent", f"telegram:message:{wake['room']['id']}:{message_id}")

    def authenticated_actor_id(self) -> str:
        payload = self._call("getMe", {})
        actor_id = payload.get("id") if isinstance(payload, Mapping) else None
        if not isinstance(actor_id, (str, int)) or str(actor_id) == "":
            raise ValidationError("Telegram getMe response lacks a stable actor ID")
        return f"telegram:actor:{actor_id}"

    def updates(
        self,
        offset: int | None,
        *,
        timeout_seconds: int | None = None,
        limit: int | None = None,
    ):
        payload = {
            "timeout": (
                self.poll_timeout if timeout_seconds is None else timeout_seconds
            ),
            "allowed_updates": json.dumps(
                ["message", "channel_post", "my_chat_member", "chat_member"]
            ),
        }
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
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
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _save_backfill_complete(path: Path) -> None:
    temporary = path.with_suffix(".tmp")
    payload = b'{"backfill_complete":true,"schema_version":2}'
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("short Telegram backfill marker write")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _poll_updates(
    transport: TelegramTransport,
    *,
    offset: int | None,
    backfilling: bool,
):
    if backfilling:
        # Telegram defines a negative offset as a bounded tail read that
        # forgets older pending updates. This establishes one finite startup
        # frontier even if the room remains active.
        return transport.updates(
            -100,
            timeout_seconds=0,
            limit=100,
        )
    return transport.updates(offset)


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
        if transport.authenticated_actor_id() != runtime.binding.actor_id:
            raise ValidationError(
                "authenticated Telegram bot does not match exact self binding"
            )
        if args.stdin:
            failed = False
            for line in sys.stdin:
                if not line.strip():
                    continue
                try:
                    runtime.submit(json.loads(line))
                except (json.JSONDecodeError, NunchiError, ValueError) as exc:
                    failed = True
                    print(f"telegram delivery error: {exc}", file=sys.stderr)
            if not runtime.drain(300):
                failed = True
                print("telegram participant deadline exceeded", file=sys.stderr)
            return 1 if failed or runtime.lane.errors else 0

        offset_path = Path(config["state_directory"]) / "telegram-update-offset"
        backfill_path = Path(config["state_directory"]) / "telegram-backfill-complete.json"
        if backfill_path.exists():
            try:
                marker = json.loads(backfill_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValidationError(
                    "Telegram backfill marker is untrustworthy"
                ) from exc
            if marker != {"backfill_complete": True, "schema_version": 2}:
                raise ValidationError(
                    "Telegram backfill marker has an invalid closed shape"
                )
        offset = int(offset_path.read_text()) if offset_path.exists() else None
        backfilling = not backfill_path.exists()
        while True:
            updates = _poll_updates(
                transport,
                offset=offset,
                backfilling=backfilling,
            )
            if not isinstance(updates, list):
                raise ValidationError("Telegram getUpdates result must be an array")
            for update in updates:
                if not isinstance(update, Mapping) or not isinstance(update.get("update_id"), int):
                    continue
                if backfilling:
                    runtime.process(update, live=False)
                else:
                    runtime.submit(update)
                offset = max(offset or 0, update["update_id"] + 1)
            if offset is not None:
                _save_offset(offset_path, offset)
            if backfilling:
                runtime.pipeline.observation.mark_continuity_gap(
                    delivery_id=(
                        "telegram:startup-backfill-gap:"
                        f"{time.time_ns()}"
                    ),
                    detail=(
                        "Telegram startup used a bounded native tail; older or "
                        "concurrent pre-frontier updates are not asserted complete"
                    ),
                )
                _save_backfill_complete(backfill_path)
                backfilling = False
            if args.once:
                return 0 if runtime.drain(300) and not runtime.lane.errors else 1
    except NunchiError as exc:
        print(f"telegram adapter error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1
    except (urllib.error.URLError, OSError, ValueError):
        print("telegram adapter operational failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
