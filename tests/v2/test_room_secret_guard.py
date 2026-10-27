"""Partly obsolete: tests that exercise the turn host or sending check the design under architecture review. They are not requirements for the new design.

Reference adapters share the room's secret guard with their participants."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from nunchi.adapters.discord import DiscordPyTransport
from nunchi.adapters.matrix import MatrixTransport
from nunchi.adapters.runtime import ReferenceAdapterRuntime
from nunchi.adapters.telegram import TelegramTransport

ATTENTION_KEY = "fake-attention-key-" + "z" * 20
DISCORD_TOKEN = "M" * 24 + "." + "G" * 6 + "." + "x" * 30
TELEGRAM_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MATRIX_TOKEN = "syt_dmlnaWw_HjBkBhVqRSnMKiumAIOt_0BnKrg"
PARTICIPANT_KEY = "fake-participant-key-" + "p" * 20


def _refuses(guard, text: str) -> bool:
    return guard.refusal({"kind": "message", "origin_event_id": "e1", "text": text}) is not None


def _profile(directory: Path, actor_id: str) -> dict:
    raw = json.dumps(
        {
            "profile_id": "vigil",
            "participant_id": "vigil",
            "actor_id": actor_id,
            "instructions": "Contribute carefully.",
            "provenance": "trusted:test",
        }
    ).encode()
    path = directory / "profile.json"
    path.write_bytes(raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


# -- the reference adapters --------------------------------------------------------------


class ReferenceAdapterGuardTests(unittest.TestCase):
    """Each reference adapter: its turns and its room refuse the same secrets."""

    def _runtime(self, surface: str, actor_id: str, room_id: str, transport, **extra):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        config = {
            "schema_version": 2,
            "binding": {
                "participant_id": "vigil",
                "actor_id": actor_id,
                "platform": surface,
                "room_id": room_id,
                "continuity_scope_id": f"{surface}:{room_id}",
            },
            "profile": _profile(base, actor_id),
            "attention": {
                "policy": {"preattention_enabled": False},
                "model": {"model": "m", "base_url": "http://127.0.0.1:9/v1", "api_key_env": "REF_ATTENTION_KEY"},
            },
            "limits": {},
            "state_directory": str(base / "state"),
            # No api_key_env: the participant reads its key from the default variable.
            "participant_model": {"model": "m", "base_url": "http://127.0.0.1:9/v1"},
            **extra,
        }
        with mock.patch.dict(
            os.environ, {"REF_ATTENTION_KEY": ATTENTION_KEY, "NUNCHI_PARTICIPANT_API_KEY": PARTICIPANT_KEY}
        ):
            runtime = ReferenceAdapterRuntime(surface=surface, config=config, transport=transport)
        self.addCleanup(runtime.lane.cancel)
        return runtime

    def _check(self, runtime, token: str, shaped: str) -> None:
        participant = runtime.room.participant
        self.assertIs(participant.guard, runtime.room.guard)
        self.assertIs(runtime.room.guard, runtime.room.host.guard)
        for text in (PARTICIPANT_KEY, ATTENTION_KEY, token, f"look: {shaped}"):
            with self.subTest(text=text[:12]):
                self.assertTrue(_refuses(runtime.room.guard, text))
        self.assertFalse(_refuses(runtime.room.guard, "On it: the deploy failed on step three."))

    def test_discord(self) -> None:
        # The transport section is optional, and the token's variable unnamed.
        transport = DiscordPyTransport(SimpleNamespace(), None, "42", token="held-discord-bot-token-value")
        runtime = self._runtime("discord", "discord:actor:9", "42", transport)
        self._check(runtime, "held-discord-bot-token-value", DISCORD_TOKEN)

    def test_telegram(self) -> None:
        with mock.patch.dict(os.environ, {"REF_TELEGRAM_TOKEN": "987654321:held-telegram-token-value-0123456789"}):
            transport = TelegramTransport({"bot_token_env": "REF_TELEGRAM_TOKEN"})
        runtime = self._runtime("telegram", "telegram:actor:987654321", "-100", transport)
        self._check(runtime, "987654321:held-telegram-token-value-0123456789", TELEGRAM_TOKEN)

    def test_matrix(self) -> None:
        with mock.patch.dict(os.environ, {"REF_MATRIX_TOKEN": "held-matrix-access-token"}):
            transport = MatrixTransport(
                {"homeserver": "https://matrix.example", "access_token_env": "REF_MATRIX_TOKEN"},
                room_id="!room:example",
                actor_id="matrix:actor:@vigil:example",
            )
        runtime = self._runtime("matrix", "matrix:actor:@vigil:example", "!room:example", transport)
        self._check(runtime, "held-matrix-access-token", MATRIX_TOKEN)


if __name__ == "__main__":
    unittest.main()
