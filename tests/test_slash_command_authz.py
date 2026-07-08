"""Trust-chain tests for the /nunchi slash command (governance poisoning).

Where authorization lives
-------------------------
The plugin registers ``_nunchi_command`` via ``ctx.register_command`` and the
handler receives ONLY the argument string — no sender identity, channel, or
role ever reaches the plugin. Per-user authorization therefore CANNOT be
implemented at this layer: it lives in hermes' command dispatcher, which
decides whose "/nunchi ..." messages are routed to registered handlers at
all. That seam is what these tests pin down:

1. The handler's signature structurally excludes sender identity (so nobody
   "adds a quick user check" here and believes the gate is protected).
2. The trust chain is documented, precisely, in the handler's docstring —
   and the docstring is enforced by test so it cannot silently rot.
3. Blast radius: whatever hermes lets through can only ever write
   ``OVERRIDABLE_KEYS`` to the config-pinned state file. Operator-only keys
   (binary, log_path, state_path, agent_id, mention_id, timeout_seconds)
   are unreachable from any slash input, however adversarial.
4. The conversational path cannot mutate state at all: ``_gate_event`` never
   writes state — not for ordinary messages, not for messages that merely
   LOOK like slash commands ("/nunchi disable global" as chat text), and not
   for non-allowlisted senders. A non-allowlisted user's message is dropped
   by sender policy before any state or classifier touch.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_PATH = _REPO_ROOT / "integrations" / "hermes" / "nunchi-gate" / "__init__.py"


def _load_plugin() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("nunchi_gate_authz_test", _PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _event(
    text: str = "hello",
    *,
    chat_id: str = "1518384310321811456",
    user_name: str = "mallory",
    user_id: str = "666",
    is_bot: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        message_id="m1",
        channel_context=None,
        source=SimpleNamespace(
            platform=SimpleNamespace(value="discord"),
            chat_id=chat_id,
            parent_chat_id=None,
            thread_id=None,
            user_id=user_id,
            user_name=user_name,
            is_bot=is_bot,
            message_id="m1",
        ),
    )


class _TmpStateMixin(unittest.TestCase):
    def setUp(self) -> None:
        self.p = _load_plugin()
        self.tmp = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmp, "state.json")
        self.cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": "1518384310321811456",
            "agent_id": "aleph",
            "bypass_commands": True,
            "fail_open": True,
            "log_path": "",
            "state_path": self.state_file,
        }

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_slash(self, args_str: str) -> str:
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=self.cfg):
            return self.p._nunchi_command(args_str)

    def _state_on_disk(self) -> dict:
        if not os.path.exists(self.state_file):
            return {}
        with open(self.state_file, encoding="utf-8") as f:
            return json.load(f)


class TestAuthorizationSeam(_TmpStateMixin):
    """The seam that exists: identity never reaches the plugin."""

    def test_handler_receives_no_sender_identity(self):
        """_nunchi_command takes exactly one string argument. There is no
        user/channel/role parameter, so per-user authorization is
        structurally impossible in the plugin — hermes' command dispatcher
        is the authorization boundary."""
        params = list(inspect.signature(self.p._nunchi_command).parameters)
        self.assertEqual(params, ["raw_args"])

    def test_trust_chain_documented_in_handler_docstring(self):
        """The docstring must state the trust chain precisely; enforced here
        so the documentation cannot silently rot."""
        doc = self.p._nunchi_command.__doc__ or ""
        self.assertIn("authorization boundary", doc.lower())
        self.assertIn("hermes", doc.lower())
        self.assertIn("OVERRIDABLE_KEYS", doc)
        self.assertIn("state_path", doc)

    def test_register_exposes_exactly_one_command_surface(self):
        """The only slash surface is 'nunchi' -> _nunchi_command; no other
        command name can reach state mutation."""
        p = _load_plugin()
        registered: dict[str, object] = {}

        class FakeCtx:
            def register_hook(self, name, fn):
                pass

            def register_command(self, name, handler, description="", args_hint=""):
                registered[name] = handler

        p.register(FakeCtx())
        self.assertEqual(set(registered), {"nunchi"})
        self.assertIs(registered["nunchi"], p._nunchi_command)


class TestSlashBlastRadius(_TmpStateMixin):
    """Whatever hermes forwards, only OVERRIDABLE_KEYS can land in state."""

    def _assert_state_within_whitelist(self) -> None:
        state = self._state_on_disk()
        allowed_meta = {"updated_at", "updated_by", "global", "channels"}
        self.assertLessEqual(set(state), allowed_meta, f"unexpected top-level keys: {state}")
        overridable = self.p._state.OVERRIDABLE_KEYS
        for key in state.get("global", {}):
            self.assertIn(key, overridable, f"global override {key!r} escaped the whitelist")
        for cid, ch in (state.get("channels") or {}).items():
            for key in ch:
                self.assertIn(
                    key, overridable, f"channel {cid!r} override {key!r} escaped the whitelist"
                )

    def test_every_mutating_subcommand_stays_within_whitelist(self):
        self._run_slash("enable global")
        self._run_slash("disable 1518384310321811456")
        self._run_slash("senders humans")
        self._run_slash("senders allowlist 1518384310321811456")
        self._run_slash("verbosity debug")
        self._run_slash("verbosity minimal 1518384310321811456")
        self._assert_state_within_whitelist()

    def test_adversarial_args_cannot_set_operator_only_keys(self):
        """No slash input can write binary/log_path/state_path/agent_id/
        mention_id/timeout_seconds — there is no subcommand for them and the
        state whitelist drops them at every write path."""
        adversarial = [
            "binary /tmp/evil",
            "log_path /tmp/evil.jsonl",
            "state_path /tmp/evil-state.json",
            "agent_id evil-bot",
            "senders humans log_path=/tmp/evil",
            "enable log_path",
            "verbosity debug binary",
            "set binary /tmp/evil",
        ]
        for args in adversarial:
            out = self._run_slash(args)
            self.assertIsInstance(out, str)
        # Adversarial values may at worst appear as harmless channel-id
        # strings under "channels"; operator-only keys must never appear as
        # override KEYS anywhere in the state document.
        state = self._state_on_disk()
        operator_only = {
            "binary", "log_path", "state_path", "agent_id", "mention_id", "timeout_seconds",
        }
        self.assertFalse(operator_only & set(state.get("global", {})))
        for ch in (state.get("channels") or {}).values():
            self.assertFalse(operator_only & set(ch))
        self._assert_state_within_whitelist()

    def test_slash_writes_only_to_config_pinned_state_path(self):
        """Mutations land in cfg['state_path'] and nowhere else in the tmp
        dir; the path itself is config.yaml-only and not overridable."""
        self._run_slash("enable global")
        written = sorted(os.listdir(self.tmp))
        self.assertEqual(written, ["state.json"])
        self.assertNotIn("state_path", self.p._state.OVERRIDABLE_KEYS)

    def test_invalid_input_writes_nothing(self):
        for args in ("", "frobnicate", "senders bogus", "verbosity extreme", "enable"):
            self._run_slash(args)
        self.assertFalse(os.path.exists(self.state_file))


class TestConversationalPathCannotMutateState(_TmpStateMixin):
    """A chat message — from anyone — can never mutate state via the gate."""

    def test_gate_event_never_calls_save_state_for_plain_message(self):
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=self.cfg):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "SPEAK", "silent": False}
            ):
                with unittest.mock.patch.object(self.p._state, "save_state") as save:
                    self.p._gate_event(_event("hello everyone"))
        save.assert_not_called()
        self.assertFalse(os.path.exists(self.state_file))

    def test_slash_looking_message_text_does_not_execute_commands(self):
        """'/nunchi disable global' as message TEXT is bypassed by
        bypass_commands and never executes the handler — command execution
        happens only through hermes' dispatcher, which owns authorization."""
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=self.cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi") as run:
                with unittest.mock.patch.object(self.p._state, "save_state") as save:
                    result = self.p._gate_event(_event("/nunchi disable global"))
        self.assertIsNone(result)
        run.assert_not_called()
        save.assert_not_called()
        self.assertFalse(os.path.exists(self.state_file))

    def test_non_allowlisted_sender_is_dropped_and_mutates_nothing(self):
        """senders=allowlist: a non-allowlisted user's message is dropped by
        sender policy — no classifier call, no state write. Combined with
        the bypass test above, a non-allowlisted user has NO path to state
        mutation through the plugin; only hermes' dispatcher could grant one."""
        cfg = dict(self.cfg)
        cfg["senders"] = "allowlist"
        cfg["allow_from"] = ["zoe", "42"]
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi") as run:
                with unittest.mock.patch.object(self.p._state, "save_state") as save:
                    result = self.p._gate_event(
                        _event("/nunchi enable global", user_name="mallory", user_id="666")
                    )
                    # Slash-looking text bypasses; plain text is policy-dropped.
                    result2 = self.p._gate_event(
                        _event("please enable yourself", user_name="mallory", user_id="666")
                    )
        self.assertIsNone(result)
        self.assertEqual(result2, {"action": "skip", "reason": "nunchi:sender-policy"})
        run.assert_not_called()
        save.assert_not_called()
        self.assertFalse(os.path.exists(self.state_file))


if __name__ == "__main__":
    unittest.main()
