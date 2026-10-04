"""Installed Matrix V2 adapter with reactive `/sync` ingress."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from collections.abc import Mapping, Sequence
from urllib.parse import quote, urlencode
import urllib.error
import urllib.request

from .. import __version__
from ..errors import NunchiError, ValidationError
from ..ack import ReactionCapability
from ..participant import TransportResult
from .runtime import CAPABILITIES, ReferenceAdapterRuntime, load_pinned_config


class MatrixTransport:
    def __init__(
        self,
        config: Mapping[str, object],
        *,
        room_id: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        allowed = {"homeserver", "access_token_env", "sync_timeout_ms"}
        if set(config) - allowed or "homeserver" not in config:
            raise ValidationError("Matrix transport config has an invalid closed shape")
        self.homeserver = str(config["homeserver"]).rstrip("/")
        env_name = str(config.get("access_token_env", "MATRIX_ACCESS_TOKEN"))
        self.token = os.environ.get(env_name)
        if not self.token:
            raise ValidationError(f"Matrix credential is absent from {env_name}")
        if room_id is not None and (not isinstance(room_id, str) or not room_id):
            raise ValidationError("Matrix reaction room binding is invalid")
        if actor_id is not None and (
            not isinstance(actor_id, str)
            or not actor_id.startswith("matrix:actor:")
            or not actor_id.removeprefix("matrix:actor:")
        ):
            raise ValidationError("Matrix reaction actor binding is invalid")
        self.room_id = room_id
        self.actor_id = actor_id
        self.native_actor_id = (
            actor_id.removeprefix("matrix:actor:") if actor_id is not None else None
        )
        self._unavailable_reaction_revision = hashlib.sha256(
            (
                f"matrix-reaction-unavailable-v2\0{self.homeserver}\0{env_name}\0"
                f"{room_id or 'unbound'}\0{actor_id or 'unbound'}"
            ).encode()
        ).hexdigest()
        self.sync_timeout_ms = int(config.get("sync_timeout_ms", 30_000))
        if self.sync_timeout_ms < 1 or self.sync_timeout_ms > 60_000:
            raise ValidationError("Matrix sync_timeout_ms must be within 1..60000")

    def ordinary_action_capabilities(self) -> tuple[str, ...]:
        return ("message", "reply", "reaction")

    def reaction_capability(self) -> ReactionCapability:
        if self.room_id is None or self.actor_id is None or self.native_actor_id is None:
            return self._unavailable_reaction_capability(
                "Matrix reaction capability lacks an exact room and self binding"
            )
        authenticated = False
        try:
            if self.authenticated_actor_id() != self.actor_id:
                return self._unavailable_reaction_capability(
                    "Matrix authenticated account does not match exact self binding"
                )
            authenticated = True
            room = quote(self.room_id, safe="")
            payload = self._request(
                "GET",
                f"/_matrix/client/v3/rooms/{room}/state/m.room.power_levels",
            )
            if not isinstance(payload, Mapping):
                raise ValidationError("Matrix power-level response is not an object")
            users = payload.get("users", {})
            events = payload.get("events", {})
            if not isinstance(users, Mapping) or not isinstance(events, Mapping):
                raise ValidationError("Matrix power-level maps are malformed")
            user_level = self._power_level(
                users.get(self.native_actor_id),
                default=self._power_level(payload.get("users_default"), default=0),
            )
            required_level = self._power_level(
                events.get("m.reaction"),
                default=self._power_level(payload.get("events_default"), default=0),
            )
            allowed = user_level >= required_level
            revision = hashlib.sha256(
                (
                    f"matrix-power-levels-v2\0{self.homeserver}\0{self.room_id}\0"
                    f"{self.native_actor_id}\0{user_level}\0{required_level}\0{int(allowed)}"
                ).encode()
            ).hexdigest()
            return ReactionCapability(
                supported=allowed,
                authenticated=True,
                operations=("add",) if allowed else (),
                reactions=("*",) if allowed else (),
                permissions_revision=revision,
                detail=(
                    ""
                    if allowed
                    else "Matrix room power levels do not allow reaction events"
                ),
            )
        except Exception:
            return ReactionCapability(
                supported=False,
                authenticated=authenticated,
                permissions_revision=self._unavailable_reaction_revision,
                detail="Matrix room reaction permission is unavailable or unattested",
            )

    @staticmethod
    def _power_level(value, *, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError("Matrix power level must be an integer")
        return value

    def _unavailable_reaction_capability(self, detail: str) -> ReactionCapability:
        return ReactionCapability(
            supported=False,
            authenticated=False,
            permissions_revision=self._unavailable_reaction_revision,
            detail=detail,
        )

    def _request(self, method: str, path: str, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.homeserver + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(
            request,
            timeout=max(10, self.sync_timeout_ms / 1000 + 5),
        ) as response:
            return json.load(response)

    def dispatch(self, *, action, wake) -> TransportResult:
        room = quote(wake["room"]["id"], safe="")
        transaction = quote(f"nunchi-{secrets.token_urlsafe(18)}", safe="")
        try:
            if action["kind"] in ("message", "reply"):
                content = {"msgtype": "m.text", "body": action["text"]}
                if action["kind"] == "reply":
                    target = action["target_event_id"].removeprefix("matrix:event:")
                    content["m.relates_to"] = {"m.in_reply_to": {"event_id": target}}
                payload = self._request(
                    "PUT",
                    f"/_matrix/client/v3/rooms/{room}/send/m.room.message/{transaction}",
                    content,
                )
            elif action["kind"] == "reaction":
                if action["operation"] != "add":
                    return TransportResult(
                        "unavailable",
                        "Matrix reaction removal requires the native reaction event ID",
                    )
                target = action["target_event_id"].removeprefix("matrix:event:")
                payload = self._request(
                    "PUT",
                    f"/_matrix/client/v3/rooms/{room}/send/m.reaction/{transaction}",
                    {
                        "m.relates_to": {
                            "rel_type": "m.annotation",
                            "event_id": target,
                            "key": action["reaction"],
                        }
                    },
                )
            else:
                return TransportResult("unavailable", "Matrix action is unsupported")
        except urllib.error.HTTPError as exc:
            return TransportResult("failed", f"Matrix returned HTTP {exc.code}")
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return TransportResult("unknown", "Matrix acknowledgement was lost")
        event_id = payload.get("event_id") if isinstance(payload, dict) else None
        if (
            not isinstance(event_id, str)
            or not event_id.startswith("$")
            or not event_id[1:]
        ):
            return TransportResult(
                "unknown",
                "Matrix acknowledgement lacked a native event ID",
            )
        return TransportResult("sent", event_id)

    def authenticated_actor_id(self) -> str:
        payload = self._request("GET", "/_matrix/client/v3/account/whoami")
        user_id = payload.get("user_id") if isinstance(payload, Mapping) else None
        if not isinstance(user_id, str) or not user_id:
            raise ValidationError("Matrix whoami response lacks a stable user_id")
        return f"matrix:actor:{user_id}"

    def sync(self, since: str | None):
        query = {"timeout": str(self.sync_timeout_ms)}
        if since:
            query["since"] = since
        return self._request("GET", "/_matrix/client/v3/sync?" + urlencode(query))


def _parser():
    parser = argparse.ArgumentParser(prog="nunchi-matrix")
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
        "surface": "matrix",
        "capabilities": CAPABILITIES["matrix"],
        "configured": False,
        "v1_fallback": False,
    }


def _save_token(path: Path, token: str) -> None:
    temporary = path.with_suffix(".tmp")
    payload = token.encode()
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("short sync-token write")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


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
            raise ValidationError("Matrix config must contain transport")
        binding_raw = config.get("binding")
        if not isinstance(binding_raw, Mapping):
            raise ValidationError("Matrix config must contain a binding")
        room_id = binding_raw.get("room_id")
        actor_id = binding_raw.get("actor_id")
        transport = MatrixTransport(
            transport_raw,
            room_id=room_id if isinstance(room_id, str) else None,
            actor_id=actor_id if isinstance(actor_id, str) else None,
        )
        runtime = ReferenceAdapterRuntime(
            surface="matrix",
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
                "authenticated Matrix account does not match exact self binding"
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
                    print(f"matrix delivery error: {exc}", file=sys.stderr)
            if not runtime.drain(300):
                failed = True
                print("matrix participant deadline exceeded", file=sys.stderr)
            return 1 if failed or runtime.lane.errors else 0

        token_path = Path(config["state_directory"]) / "matrix-sync-token"
        since = token_path.read_text().strip() if token_path.exists() else None
        while True:
            response = transport.sync(since)
            next_batch = response.get("next_batch")
            if not isinstance(next_batch, str) or not next_batch:
                raise ValidationError("Matrix sync response lacks next_batch")
            rooms = response.get("rooms", {}).get("join", {})
            if isinstance(rooms, Mapping):
                for room_id, room_data in rooms.items():
                    if not isinstance(room_data, Mapping):
                        continue
                    timeline = room_data.get("timeline", {})
                    events = timeline.get("events", []) if isinstance(timeline, Mapping) else []
                    if (
                        isinstance(timeline, Mapping)
                        and timeline.get("limited") is True
                    ):
                        runtime.lane.cancel()
                        runtime.pipeline.observation.mark_continuity_gap(
                            delivery_id=f"matrix:sync-gap:{room_id}:{next_batch}",
                            detail="Matrix reported a limited timeline",
                        )
                    for event in events:
                        payload = {"room_id": room_id, "event": event}
                        if since is None:
                            runtime.process(payload, live=False)
                        else:
                            runtime.submit(payload)
            _save_token(token_path, next_batch)
            since = next_batch
            if args.once:
                return 0 if runtime.drain(300) and not runtime.lane.errors else 1
    except (NunchiError, urllib.error.URLError, OSError, ValueError) as exc:
        print(f"matrix adapter error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
