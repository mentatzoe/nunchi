"""Installed-host normal-turn probes for the Nunchi Hermes V2 plugin.

Opt-in: these run only against an installed stock Hermes with the shipped
Discord platform plugin and the ``messaging`` extra. Set
``NUNCHI_REQUIRE_HERMES_NORMAL_TURN=1`` in such an environment (no source
worktree on ``PYTHONPATH``; ``python -I`` is fine).

What is real here
-----------------
* ``gateway.run.GatewayRunner`` constructed from the stock ``config.yaml`` in
  a temporary ``HERMES_HOME``.
* The shipped ``plugins.platforms.discord.adapter.DiscordAdapter`` created by
  ``GatewayRunner._create_adapter`` and wired with the same calls
  ``GatewayRunner.start()`` makes.
* Stock authorisation (``DISCORD_ALLOWED_USERS``, ``_is_user_authorized``,
  ``_discord_message_admission``), the stock turn
  (``_handle_message_with_agent`` → ``AIAgent``), stock tool dispatch and the
  stock delivery path (``_process_message_background`` → ``DiscordAdapter.send``).
* Nunchi loaded through ``hermes_cli.plugins.PluginManager`` from the
  installed entry point, exactly as a gateway would load it.

What is a double (and labelled as such)
---------------------------------------
* The model provider: a loopback OpenAI-compatible SSE server that Hermes
  reaches through its own ``model.provider: custom`` route. This is NOT
  live-provider acceptance.
* The Discord client object after ``connect()``: records ``channel.send``
  and hands back message-shaped acknowledgements. Discord-side
  authentication is therefore out of scope; Hermes-side authorisation is
  exercised for real.

Each probe records what the host actually did; a failing assertion is a
baseline fact for the owner card, not a request to weaken the probe.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from tests.v2 import hermes_normal_turn_support as sup

_REQUIRED = os.environ.get("NUNCHI_REQUIRE_HERMES_NORMAL_TURN") == "1"

HUMAN = 100  # allowlisted human
STRANGER = 200  # not allowlisted
PEER_BOT = 555  # another bot in the room
BOT = 999  # this Hermes bot's own Discord user id


def _deliver_and_settle(host: sup.ProbeHost, message: Any, *, timeout: float = 60.0) -> bool:
    async def _go() -> bool:
        admitted = await host.deliver(message)
        await host.settle(timeout=timeout)
        # Give detached auxiliary work (title generation) a moment to hit the double.
        await asyncio.sleep(0.2)
        return admitted

    return sup.run(_go(), timeout=timeout + 10)


_PROCESS_HOME: tuple[Any, Path] | None = None
_PROCESS_SERVER: sup.FakeOpenAIServer | None = None


def _process_home() -> Path:
    """One HERMES_HOME for the whole process: stock binds its log file and
    state DB at first use, so switching homes mid-process only produces
    'Logging error' noise and loses agent.log."""

    global _PROCESS_HOME
    if _PROCESS_HOME is None:
        tmp, home = sup.new_home()
        home.mkdir(parents=True, exist_ok=True)
        os.environ["HERMES_HOME"] = str(home)
        _PROCESS_HOME = (tmp, home)
    return _PROCESS_HOME[1]


def _process_server() -> sup.FakeOpenAIServer:
    """One model double per process: stock caches OpenAI clients by base_url
    (agent/auxiliary_client.py ``_client_cache``), so a fresh port per test
    would leave cached clients pointing at closed sockets."""

    global _PROCESS_SERVER
    if _PROCESS_SERVER is None:
        _PROCESS_SERVER = sup.FakeOpenAIServer()
    return _PROCESS_SERVER


class _Base(unittest.TestCase):
    """One HERMES_HOME per process (stock binds logs/state DB at import time);
    a fresh room id, model double and GatewayRunner per test so every probe
    starts with an empty session. Nunchi on or off per class."""

    enable_nunchi = False
    trust_nunchi_llm = False
    nunchi_timeout_seconds = 20.0
    nunchi_ack_enabled: bool | None = None
    _room_counter = 0

    @classmethod
    def setUpClass(cls) -> None:
        if not _REQUIRED:
            raise unittest.SkipTest("set NUNCHI_REQUIRE_HERMES_NORMAL_TURN=1 in an installed stock Hermes env")
        cls.removed_env = sup.scrub_ambient_environment()
        cls._class_home = _process_home()
        os.environ["DISCORD_BOT_TOKEN"] = "probe-token-not-a-secret"
        os.environ["DISCORD_ALLOWED_USERS"] = str(HUMAN)
        os.environ["DISCORD_AUTO_THREAD"] = "false"
        cls.facts = {
            "hermes_version": sup.hermes_version(),
            "nunchi_version": sup.nunchi_version(),
            "paths": sup.installed_paths(),
            "scrubbed_env": cls.removed_env,
        }

    @classmethod
    def tearDownClass(cls) -> None:
        keep = os.environ.get("NUNCHI_PROBE_KEEP_HOME")
        if keep:
            import shutil

            target = Path(keep) / "process-home"
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(cls._class_home, target, ignore=shutil.ignore_patterns("*.db*", "audio_cache", "image_cache"))

    def setUp(self) -> None:
        _Base._room_counter += 1
        self.room = 42_000 + _Base._room_counter
        self.peer_room = self.room + 500  # Hermes-allowlisted, never configured for Nunchi
        self.home = self._class_home
        self.server = _process_server()
        self.server.reset()
        sup.write_hermes_home(self.home, model_base_url=self.server.base_url, enable_nunchi=self.enable_nunchi, trust_nunchi_llm=self.trust_nunchi_llm)
        self.loaded: dict[str, Any] | None = None
        if self.enable_nunchi:
            self._load_nunchi(timeout_seconds=self.nunchi_timeout_seconds)
        else:
            # Same discovery call the gateway makes, now with nunchi absent
            # from plugins.enabled: hooks from a previous Nunchi probe are gone.
            import hermes_cli.plugins as plugins

            plugins.discover_plugins(force=True)
        self.client = sup.FakeDiscordClient(bot_user_id=BOT)
        self.host = sup.ProbeHost(home=self.home, client=self.client)

    def _load_nunchi(self, *, timeout_seconds: float) -> None:
        sup.write_nunchi_config(
            self.home,
            room_id=str(self.room),
            bot_user_id=BOT,
            timeout_seconds=timeout_seconds,
            ack_enabled=self.nunchi_ack_enabled,
        )
        self.loaded = sup.load_nunchi_via_plugin_manager()
        self.assertIsNone(
            self.loaded["state"]["error"],
            "stock PluginManager refused Nunchi. On 0.21.x a 'load timed out' here is the "
            "register() deadlock: the loader thread holds PluginManager._discovery_lock, and "
            "_active_discord_adapter_class() -> platform_registry.get('discord') runs the deferred "
            "Discord loader, which re-acquires that lock. state=%r" % (self.loaded["state"],),
        )

    def tearDown(self) -> None:
        try:
            sup.run(self.host.close(), timeout=20)
        finally:
            if self.loaded is not None:
                sup.unload_nunchi(self.loaded)

    # -- helpers -----------------------------------------------------------

    def approval_command(self) -> tuple[str, Path]:
        # Native /approve really executes this command. Never use a shared
        # fixed /tmp target: delete only data just created in this fixture home.
        target = Path(tempfile.mkdtemp(prefix="approval-target-", dir=self.home)).resolve()
        assert target.is_relative_to(self.home.resolve())
        (target / "marker").write_text("disposable approval fixture\n")
        return f"rm -rf -- {shlex.quote(str(target))}", target

    def human(self, content: str, *, room: int | None = None, author: int = HUMAN, mention: bool = True) -> Any:
        room = self.room if room is None else room
        message = sup.human_message(self.host, channel_id=room, author_id=author, content=(f"<@{BOT}> " if mention else "") + content)
        if mention:
            message.mentions = [self.client.user]
        return message

    def peer(self, content: str, *, room: int | None = None, mention: bool = True) -> Any:
        room = self.room if room is None else room
        message = sup.peer_bot_message(self.host, channel_id=room, author_id=PEER_BOT, content=(f"<@{BOT}> " if mention else "") + content)
        if mention:
            message.mentions = [self.client.user]
        return message

    def deliveries(self) -> list[str]:
        return [c["content"] for c in self.client.send_calls]

    def model_turns(self) -> list[dict[str, Any]]:
        """Chat-completion requests that carried tools (the normal agent turn)."""

        return [b for b in self.server.bodies() if "tools" in b]

    def side_calls(self) -> list[str]:
        """Stock auxiliary calls (approval guard, title) the double answered."""

        out = []
        for b in self.server.bodies():
            system = " ".join(str(m.get("content", "")) for m in b.get("messages", []) if m.get("role") == "system")
            if "security reviewer" in system:
                out.append("approval-guard")
            elif "descriptive title" in system:
                out.append("title")
        return out

    def attention_calls(self) -> list[dict[str, Any]]:
        """Nunchi's structured attention call goes through host PluginLlm with no tools."""

        return [b for b in self.server.bodies() if "tools" not in b and any("DEFER" in str(m.get("content", "")) for m in b.get("messages", []))]

    def receipts(self) -> list[dict[str, Any]]:
        return sup.receipts(self.home, room_id=str(self.room))

    def attend(self, disposition: str) -> None:
        """Make the double answer Nunchi's attention call with one disposition.

        Returns ``None`` so it can sit first in a ``server.script(...)`` call
        for readability without consuming a FIFO slot (``script`` skips None).
        """

        def _answer(body: dict[str, Any]) -> dict[str, Any]:
            return {"content": sup.attention_judgment(disposition, _event_id_from_prompt(body))}

        self.server.attention = _answer
        return None


# ===========================================================================
# Stock baseline (no Nunchi) — proves the harness exercises real Hermes
# ===========================================================================


class StockHermesNormalTurnBaseline(_Base):
    enable_nunchi = False

    def test_authenticated_human_turn_reaches_model_and_delivers_ack(self) -> None:
        self.server.script({"content": "stock reply"})
        admitted = _deliver_and_settle(self.host, self.human("hello"))
        self.assertTrue(admitted, "shipped DiscordAdapter admitted an allowlisted human")
        turns = self.model_turns()
        self.assertEqual(1, len(turns), self.server.bodies())
        self.assertEqual("probe-model", turns[0]["model"])
        self.assertTrue(turns[0].get("stream"), "0.19.0+ streams chat completions")
        self.assertIn("stock reply", self.deliveries())
        # Native ack: DiscordAdapter.send returned the message object from channel.send
        self.assertEqual(1, len(self.client.channel(self.room).sent))
        self.assertEqual([], self.host.leaked_session_guards(), "stock releases the session guard when the owner task ends")

    def test_unauthorised_human_is_dropped_before_model(self) -> None:
        admitted = _deliver_and_settle(self.host, self.human("hello", author=STRANGER))
        self.assertFalse(admitted)
        self.assertEqual([], self.model_turns())
        self.assertEqual([], self.deliveries())

    def test_peer_bot_is_dropped_by_stock_default_allow_bots_none(self) -> None:
        admitted = _deliver_and_settle(self.host, self.peer("hello"))
        self.assertFalse(admitted, "stock DISCORD_ALLOW_BOTS defaults to none")
        self.assertEqual([], self.model_turns())

    def test_ordinary_tool_runs_through_native_dispatcher(self) -> None:
        # Model asks for a benign read-only tool; stock executes it natively
        # and makes a second model call with the tool result.
        self.server.script(
            {"content": None, "tool_calls": [sup.tool_call("read_file", {"path": str(self.home / "config.yaml")})]},
            {"content": "I read the config"},
        )
        _deliver_and_settle(self.host, self.human("read my config"))
        turns = self.model_turns()
        self.assertEqual(2, len(turns), [t.get("messages", [])[-1] for t in turns])
        tail = turns[1]["messages"][-3:]
        self.assertEqual("tool", tail[-1].get("role"), f"native dispatcher fed the tool result back to the model; tail={tail}")
        tool_message = turns[1]["messages"][-1]
        self.assertIn("model:", str(tool_message.get("content")), "read_file actually ran against the temp HERMES_HOME")
        self.assertIn("I read the config", self.deliveries())

    def test_native_approval_blocks_dangerous_terminal_until_approve(self) -> None:
        # Stock approval flow: dangerous terminal command parks the agent
        # thread in tools.approval; /approve from the same route resumes it.
        command, target = self.approval_command()
        self.server.script(
            {"content": None, "tool_calls": [sup.tool_call("terminal", {"command": command})]},
            {"content": "done after approval"},
        )
        from tools import approval as approval_mod

        async def _go() -> dict[str, Any]:
            await self.host.deliver(self.human("delete that"))
            session_key = None
            # Wait for the native approval queue to hold an entry.
            for _ in range(400):
                queues = getattr(approval_mod, "_gateway_queues", {})
                if queues:
                    session_key = next(iter(queues))
                    break
                await asyncio.sleep(0.05)
            prompt_seen = any("Approval Required" in d or "needs your OK" in d or "/approve" in d for d in self.deliveries())
            if session_key is None:
                return {"pending": False, "prompt_seen": prompt_seen}
            self.assertTrue((target / "marker").is_file(), "executed before approval")
            approve_admitted = await self.host.deliver(self.human("/approve"))
            await self.host.settle(timeout=60)
            await asyncio.sleep(0.2)
            return {"pending": True, "prompt_seen": prompt_seen, "approve_admitted": approve_admitted, "session_key": session_key}

        outcome = sup.run(_go(), timeout=120)
        self.assertTrue(outcome["pending"], f"stock approval never parked the agent: {outcome} deliveries={self.deliveries()}")
        self.assertTrue(outcome["prompt_seen"], self.deliveries())
        self.assertTrue(outcome["approve_admitted"])
        self.assertIn("done after approval", self.deliveries())
        self.assertEqual(2, len(self.model_turns()))
        self.assertFalse(target.exists(), "approved native command did not execute")

    def test_native_deny_returns_blocked_result_to_model(self) -> None:
        command, target = self.approval_command()
        self.server.script(
            {"content": None, "tool_calls": [sup.tool_call("terminal", {"command": command})]},
            {"content": "ok, not deleting"},
        )
        from tools import approval as approval_mod

        async def _go() -> bool:
            await self.host.deliver(self.human("delete that"))
            for _ in range(400):
                if getattr(approval_mod, "_gateway_queues", {}):
                    break
                await asyncio.sleep(0.05)
            else:
                return False
            await self.host.deliver(self.human("/deny"))
            await self.host.settle(timeout=60)
            return True

        self.assertTrue(sup.run(_go(), timeout=120))
        turns = self.model_turns()
        self.assertEqual(2, len(turns))
        self.assertIn("denied", str(turns[1]["messages"][-1].get("content")).lower())
        self.assertIn("ok, not deleting", self.deliveries())
        self.assertTrue((target / "marker").is_file(), "denied command executed")


# ===========================================================================
# Nunchi loaded through the stock PluginManager on the same host
# ===========================================================================


class NunchiDefaultInstallTrustGate(_Base):
    """Baseline fact: on a default install stock PluginLlm refuses Nunchi's
    attention call (provider/model override not trusted), so every admitted
    message wakes via ERROR_FALLBACK. Recorded, not hidden."""

    enable_nunchi = True
    trust_nunchi_llm = False

    def test_default_install_attention_is_refused_and_falls_back_to_wake(self) -> None:
        self.server.script({"content": "woke by error fallback"})
        admitted = _deliver_and_settle(self.host, self.human("hello"))
        self.assertTrue(admitted)
        attention = [r for r in self.receipts() if r.get("stage") == "attention"]
        self.assertTrue(attention, self.receipts())
        error = attention[-1].get("body", {}).get("error", {})
        self.assertEqual("host-permission-denied", error["code"])
        self.assertIn("Save & allow attention models", error["detail"])
        self.assertIn("restart Hermes", error["detail"])
        self.assertIn("No substitute attention model was used", error["detail"])
        self.assertNotIn("classifier_disposition", attention[-1]["body"])
        self.assertEqual([], self.attention_calls())
        self.assertEqual(1, len(self.model_turns()))
        self.assertEqual("probe-model", self.model_turns()[0]["model"])
        self.assertIn("ERROR_FALLBACK", json.dumps(self.model_turns()[0]["messages"]))
        self.assertIn("woke by error fallback", self.deliveries())

    def test_denied_attention_then_save_and_restart_uses_selected_model(self) -> None:
        from nunchi.integrations.hermes_dashboard_store import (
            default_config_paths, read_dashboard_snapshot, write_config_document,
        )
        self.server.script({"content": "before consent"})
        self.assertTrue(_deliver_and_settle(self.host, self.human("first")))
        self.assertEqual([], self.attention_calls())
        self.assertEqual("host-permission-denied", [r["body"] for r in self.receipts()
                         if r["stage"] == "attention"][-1]["error"]["code"])
        paths = default_config_paths("default", hermes_home=self.home)
        document = json.loads(paths.config.read_text())
        document["rooms"][0]["attention"]["model"]["model"] = "attention-after-save"
        env = {"HERMES_HOME": str(self.home)}
        before = read_dashboard_snapshot("default", environ=env)
        write_config_document("default", document=document, expected_revision=before.revision, environ=env)
        # Restart the installed plugin/runner, retaining the real saved files.
        # No manual trust edit or fixture config rewrite occurs after Save.
        sup.run(self.host.close())
        assert self.loaded is not None
        sup.unload_nunchi(self.loaded)
        self.loaded = sup.load_nunchi_via_plugin_manager()
        self.assertIsNone(self.loaded["state"]["error"])
        self.host = sup.ProbeHost(home=self.home, client=self.client)
        self.server.reset()
        self.server.script(self.attend("WAKE"), {"content": "after consent"})
        self.assertTrue(_deliver_and_settle(self.host, self.human("second")))
        self.assertEqual(1, len(self.attention_calls()))
        self.assertEqual("attention-after-save", self.attention_calls()[0]["model"])
        self.assertEqual(1, len(self.model_turns()))
        self.assertEqual("probe-model", self.model_turns()[0]["model"])
        self.assertIn("after consent", self.deliveries())
        attention = [r["body"] for r in self.receipts() if r["stage"] == "attention"][-1]
        self.assertNotIn("error", attention)
        self.assertEqual("WAKE", attention["effective_disposition"])
        self.assertTrue(any(r["stage"] == "transport" and r["body"].get("delivery") == "sent"
                            for r in self.receipts()))


class NunchiOnInstalledHostNormalTurn(_Base):
    enable_nunchi = True
    trust_nunchi_llm = True  # see NunchiDefaultInstallTrustGate for the default-install baseline

    def test_plugin_loaded_and_shims_installed(self) -> None:
        state = self.loaded["state"]
        self.assertEqual("entrypoint", state["source"])
        self.assertIsNone(state["error"])
        from gateway.platforms.base import BasePlatformAdapter
        from nunchi.integrations import hermes_v2

        self.assertTrue(getattr(BasePlatformAdapter.handle_message, "__nunchi_v2_ingress__", False))
        self.assertIsNotNone(hermes_v2._SHIM_OWNER)
        probe = hermes_v2._SHIM_OWNER.probe()
        self.assertEqual(self.facts["hermes_version"], probe["hermes_version"])
        self.assertEqual([{"platform": "discord", "room_id": str(self.room)}], [{"platform": r["platform"], "room_id": r["room_id"]} for r in probe["rooms"]])

    def test_admitted_human_turn_wakes_once_and_delivers_with_sent_receipt(self) -> None:
        # Attention double says WAKE (first chat completion, no tools);
        # stock turn then answers (second, with tools).
        event_id = "pending"
        self.server.script(
            self.attend("WAKE"),
            {"content": "participant reply"},
        )
        admitted = _deliver_and_settle(self.host, self.human("hello nunchi"))
        self.assertTrue(admitted)
        bodies = self.server.bodies()
        turns = self.model_turns()
        self.assertEqual(1, len(turns), f"exactly one native participant invocation; saw {len(turns)} of {len(bodies)} requests")
        # Nunchi injected bounded facts via pre_llm_call
        joined = json.dumps(turns[0]["messages"])
        self.assertIn("Nunchi turn facts", joined)
        self.assertIn("participant reply", self.deliveries())
        stages = [(r.get("stage"), r.get("body", {}).get("delivery") or r.get("body", {}).get("outcome")) for r in self.receipts()]
        self.assertIn(("transport", "sent"), stages, stages)

    def test_stock_session_guard_released_after_configured_turn(self) -> None:
        """Baseline fact: Nunchi's lifecycle shim runs stock's
        ``_process_message_background`` inside a child task
        (``_run_stock_process_with_deadline``). Stock's cleanup only releases
        ``_active_sessions[key]`` when ``asyncio.current_task()`` is the task it
        registered in ``_session_tasks`` (0.19.0 base.py ~5570), so the guard
        stays held after the turn. The next message in that room then takes
        the active-session branch (busy/queue) instead of a fresh turn."""

        self.server.script(
            self.attend("WAKE"),
            {"content": "first reply"},
        )
        _deliver_and_settle(self.host, self.human("first"))
        self.assertIn("first reply", self.deliveries())
        self.assertEqual(
            [],
            self.host.leaked_session_guards(),
            "stock _active_sessions guard still held after the Nunchi-wrapped turn finished",
        )

    def test_suppressed_turn_makes_no_native_invocation_or_delivery(self) -> None:
        self.attend("SUPPRESS")
        message = self.human("just chatting", mention=False)
        admitted = _deliver_and_settle(self.host, message)
        self.assertTrue(admitted)
        self.assertEqual(1, len(self.attention_calls()))
        self.assertEqual([], self.model_turns(), "SUPPRESS must not reach the stock participant")
        self.assertEqual([], self.deliveries())
        self.assertEqual([], message.reactions)

    def test_self_bot_in_configured_room_keeps_stock_denial(self) -> None:
        message = self.peer("own echo")
        message.author = self.client.user
        self.assertFalse(_deliver_and_settle(self.host, message))
        self.assertEqual([], self.attention_calls())
        self.assertEqual([], self.model_turns())
        self.assertEqual([], self.deliveries())

    def test_peer_bot_in_configured_room_is_admitted_and_routed_through_nunchi(self) -> None:
        # Stock would drop this (DISCORD_ALLOW_BOTS=none). Nunchi narrows the
        # bot gate to its exact room; the peer should reach attention.
        self.server.script(
            self.attend("WAKE"),
            {"content": "reply to peer"},
        )
        admitted = _deliver_and_settle(self.host, self.peer("hello from peer"))
        self.assertTrue(admitted, "peer bot in a configured Nunchi room must be admitted")
        self.assertEqual(1, len(self.model_turns()))
        self.assertIn("reply to peer", self.deliveries())

    def test_peer_bot_outside_configured_room_still_falls_through_to_stock_denial(self) -> None:
        admitted = _deliver_and_settle(self.host, self.peer("hello", room=self.peer_room))
        self.assertFalse(admitted, "unconfigured room keeps stock DISCORD_ALLOW_BOTS=none")
        self.assertEqual([], self.model_turns())

    def test_unconfigured_room_human_turn_is_pure_stock(self) -> None:
        self.server.script({"content": "stock reply elsewhere"})
        admitted = _deliver_and_settle(self.host, self.human("hello", room=self.peer_room))
        self.assertTrue(admitted)
        turns = self.model_turns()
        self.assertEqual(1, len(turns))
        self.assertNotIn("Nunchi turn facts", json.dumps(turns[0]["messages"]))
        self.assertIn("stock reply elsewhere", self.deliveries())
        self.assertEqual([], self.receipts(), "no Nunchi receipts for an unconfigured room")

    def test_unauthorised_human_in_configured_room_is_still_denied_by_stock_auth(self) -> None:
        admitted = _deliver_and_settle(self.host, self.human("hello", author=STRANGER))
        self.assertFalse(admitted)
        self.assertEqual([], self.server.bodies(), "no attention call for an unauthenticated sender")

    def test_ordinary_tool_on_configured_route(self) -> None:
        """The probe must agree with an ordinary tool executing under stock Hermes."""

        self.server.script(
            self.attend("WAKE"),
            {"content": None, "tool_calls": [sup.tool_call("read_file", {"path": str(self.home / "config.yaml")})]},
            {"content": "tool outcome relayed"},
        )
        _deliver_and_settle(self.host, self.human("read my config"))
        turns = self.model_turns()
        self.assertEqual(2, len(turns), self.server.bodies())
        tool_result = str(turns[1]["messages"][-1].get("content"))
        self.assertIn("model:", tool_result, f"read_file did not execute natively on a configured route; model received: {tool_result[:200]}")
        self._assert_tool_probe()

    def _assert_tool_probe(self) -> None:
        from nunchi.integrations import hermes_v2

        probe = hermes_v2._SHIM_OWNER.probe()
        self.assertEqual("stock-hermes-with-nunchi-invocation-guards", probe["tool_execution"])
        self.assertFalse(probe["complete_v2_lifecycle"])
        self.assertEqual("disabled-configured-routes", probe["auto_title"])
        self.assertEqual("disabled-configured-turns", probe["stock_typing"])
        self.assertEqual("disabled-configured-routes", probe["discord_voice_input"])
        self.assertIn("background", probe["unsupported_configured_commands"])

    def test_native_approval_control_on_configured_route(self) -> None:
        """Owner fa0119a: /approve must reach stock while its participant waits."""

        command, target = self.approval_command()
        self.server.script(
            self.attend("WAKE"),
            {"content": None, "tool_calls": [sup.tool_call("terminal", {"command": command})]},
            {"content": "done after approval"},
        )
        from tools import approval as approval_mod

        async def _go() -> dict[str, Any]:
            await self.host.deliver(self.human("delete that"))
            parked = False
            for _ in range(400):
                if getattr(approval_mod, "_gateway_queues", {}):
                    parked = True
                    break
                await asyncio.sleep(0.05)
            if not parked:
                await self.host.settle(timeout=60)
                return {"parked": False}
            self.assertTrue((target / "marker").is_file(), "executed before approval")
            approve_admitted = await self.host.deliver(self.human("/approve"))
            await self.host.settle(timeout=60)
            await asyncio.sleep(0.2)
            return {"parked": True, "approve_admitted": approve_admitted}

        outcome = sup.run(_go(), timeout=120)
        turns = self.model_turns()
        self.assertTrue(
            outcome["parked"],
            f"stock approval never parked on a configured route (tool blanket-denied before approval?). "
            f"turns={len(turns)} last_tool_msg={str(turns[-1]['messages'][-1].get('content'))[:200] if turns else None} "
            f"deliveries={self.deliveries()} receipts={[(r.get('stage'), r.get('body', {}).get('wake_source') or r.get('body', {}).get('error') or r.get('body', {}).get('delivery')) for r in self.receipts()]}",
        )
        self.assertTrue(outcome["approve_admitted"])
        self.assertIn("done after approval", self.deliveries())
        # Exactly once: one tool request, one approved execution, one reply.
        self.assertEqual(2, len(turns), self.server.bodies())
        results = [m for m in turns[1]["messages"] if m.get("role") == "tool"]
        self.assertEqual(1, len(results), results)
        result = json.loads(results[0]["content"])
        self.assertEqual(0, result.get("exit_code"), result)
        self.assertIn("approved by the user", json.dumps(result))
        self._assert_tool_probe()
        self.assertFalse(target.exists(), "approved native command did not execute")

    def test_cancel_via_stop_makes_no_new_native_invocation(self) -> None:
        hold = threading.Event()
        self.server.script(
            self.attend("WAKE"),
            {"content": "late reply", "hold": hold, "hold_timeout": 60},
        )

        async def _go() -> None:
            await self.host.deliver(self.human("start something"))
            # Wait until the stock turn is in flight at the model double.
            for _ in range(400):
                if len(self.model_turns()) >= 1:
                    break
                await asyncio.sleep(0.05)
            await self.host.deliver(self.human("/stop"))
            await asyncio.sleep(0.5)
            hold.set()
            await self.host.settle(timeout=60)
            await asyncio.sleep(0.3)

        sup.run(_go(), timeout=120)
        self.assertEqual(1, len(self.model_turns()), "no second native invocation after /stop")
        self.assertNotIn("late reply", self.deliveries(), "late model text must not be delivered after cancellation")
        stages = [(r.get("stage"), r.get("body", {}).get("delivery")) for r in self.receipts() if r.get("stage") == "transport"]
        self.assertTrue(stages, "a transport receipt should record the cancelled/unknown outcome")
        self.assertNotIn(("transport", "sent"), stages, stages)

    def test_stale_run_past_deadline_is_not_delivered(self) -> None:
        # Re-materialise the room with a 2s opportunity deadline.
        sup.unload_nunchi(self.loaded)
        self._load_nunchi(timeout_seconds=2.0)
        self.host = sup.ProbeHost(home=self.home, client=self.client)
        hold = threading.Event()
        self.server.script(
            self.attend("WAKE"),
            {"content": "too late", "hold": hold, "hold_timeout": 60},
        )

        async def _go() -> None:
            await self.host.deliver(self.human("slow one"))
            await asyncio.sleep(3.0)
            hold.set()
            await self.host.settle(timeout=60)
            await asyncio.sleep(0.3)

        sup.run(_go(), timeout=120)
        self.assertNotIn("too late", self.deliveries())
        stages = [(r.get("stage"), r.get("body", {}).get("delivery")) for r in self.receipts() if r.get("stage") == "transport"]
        self.assertNotIn(("transport", "sent"), stages, stages)

    def test_delivery_failure_is_recorded_not_sent(self) -> None:
        import discord

        self.server.script(
            self.attend("WAKE"),
            {"content": "will not land"},
        )
        self.client.send_failure = discord.HTTPException(
            __import__("types").SimpleNamespace(status=500, reason="boom"), {"message": "boom"}
        )
        _deliver_and_settle(self.host, self.human("hello"))
        self.assertEqual(1, len(self.model_turns()))
        stages = [(r.get("stage"), r.get("body", {}).get("delivery")) for r in self.receipts() if r.get("stage") == "transport"]
        self.assertTrue(stages)
        self.assertNotIn(("transport", "sent"), stages, stages)


class NunchiAttentionAckDefault(_Base):
    """By default an ACK judgment is the participant's own turn (Zoe, 2026-10-05)."""

    enable_nunchi = True
    trust_nunchi_llm = True

    def setUp(self) -> None:
        super().setUp()
        os.environ["DISCORD_REACTIONS"] = "false"
        self.client.reaction_started = threading.Event()
        self.client.reaction_hold = None

    def test_ack_gives_the_participant_a_turn_and_nunchi_adds_no_reaction(self) -> None:
        self.server.script(self.attend("ACK"), {"content": "participant's own turn"})
        message = self.human("just letting you know the deploy finished")
        _deliver_and_settle(self.host, message)
        self.assertEqual([], [item for item in message.reactions if item == ("add", "👂")])
        self.assertEqual(1, len(self.model_turns()), "ACK widens to DEFER and runs the participant")
        attention = [r for r in self.receipts() if r.get("stage") == "attention"]
        self.assertTrue(attention)
        body = attention[-1]["body"]
        self.assertEqual("DEFER", body.get("effective_disposition"))
        self.assertEqual("ack-disabled", body.get("routing_audit", {}).get("override_cause"))


class NunchiAttentionAck(_Base):
    """Nunchi's own nod on the installed host, turned on in the room's config.

    Off by default since 2026-10-05; these tests cover the opt-in until step 7
    of #94 removes it. Not a participant turn.
    """

    enable_nunchi = True
    trust_nunchi_llm = True
    nunchi_ack_enabled = True

    def setUp(self) -> None:
        super().setUp()
        os.environ["DISCORD_REACTIONS"] = "false"
        self.client.reaction_started = threading.Event()
        self.client.reaction_hold = None

    def _ears(self, message: Any) -> list[tuple[str, str]]:
        return [item for item in message.reactions if item == ("add", "👂")]

    def test_ack_adds_one_native_reaction_and_skips_the_participant(self) -> None:
        self.attend("ACK")
        message = self.human("please just acknowledge, do not answer")
        admitted = _deliver_and_settle(self.host, message)
        self.assertTrue(admitted)
        self.assertEqual([], self.model_turns(), "ACK must not invoke the participant or main model")
        self.assertEqual([], self.deliveries())
        self.assertEqual([("add", "👂")], self._ears(message))
        bodies = [r.get("body", {}) for r in self.receipts()]
        self.assertTrue(any(body.get("effective_disposition") == "ACK" for body in bodies), bodies)
        self.assertTrue(any(body.get("invoked") is False for body in bodies), bodies)
        self.assertIn(("transport", "sent"), [(r.get("stage"), r.get("body", {}).get("delivery")) for r in self.receipts()])

    def test_replay_after_restart_does_not_repeat_the_reaction(self) -> None:
        self.attend("ACK")
        message = self.human("ack once")
        _deliver_and_settle(self.host, message)
        self.assertEqual(1, len(self._ears(message)))
        sup.unload_nunchi(self.loaded)
        self._load_nunchi(timeout_seconds=self.nunchi_timeout_seconds)
        self.host = sup.ProbeHost(home=self.home, client=self.client)
        self.attend("ACK")
        again = _deliver_and_settle(self.host, message)
        self.assertTrue(again)
        self.assertEqual(1, len(self._ears(message)), "restarted journal must not emit a second reaction")
        self.assertEqual([], self.model_turns())

    def test_unsupported_permission_falls_back_to_defer_without_a_reaction(self) -> None:
        channel = self.client.channel(self.room)
        channel.permissions.add_reactions = False
        self.server.script(self.attend("ACK"), {"content": "deferred participant"})
        message = self.human("cannot react here")
        _deliver_and_settle(self.host, message)
        self.assertEqual([], self._ears(message))
        self.assertEqual(1, len(self.model_turns()), "unsupported ACK widens to DEFER and runs the participant")
        attention = [r for r in self.receipts() if r.get("stage") == "attention"]
        self.assertTrue(attention)
        body = attention[-1]["body"]
        self.assertEqual("DEFER", body.get("effective_disposition"))
        self.assertEqual("ack-unsupported", body.get("routing_audit", {}).get("override_cause"))

    def test_changed_permission_does_not_send_the_reaction_or_wake(self) -> None:
        channel = self.client.channel(self.room)

        def _answer(body: dict[str, Any]) -> dict[str, Any]:
            channel.permissions.add_reactions = False
            return {"content": sup.attention_judgment("ACK", _event_id_from_prompt(body))}

        self.server.attention = _answer
        message = self.human("permission may change")
        _deliver_and_settle(self.host, message)
        self.assertEqual([], self._ears(message))
        self.assertEqual([], self.model_turns())
        deliveries = [r.get("body", {}).get("delivery") for r in self.receipts() if r.get("stage") == "transport"]
        self.assertIn("unavailable", deliveries, self.receipts())
        self.assertNotIn("sent", deliveries)

    def test_cancellation_and_late_native_result_are_not_sent(self) -> None:
        hold = asyncio.Event()
        self.client.reaction_hold = hold
        self.attend("ACK")
        message = self.human("cancel this ack")

        async def _go() -> None:
            task = asyncio.create_task(self.host.deliver(message))
            for _ in range(400):
                if self.client.reaction_started.is_set():
                    break
                await asyncio.sleep(0.05)
            await self.host.deliver(self.human("/stop"))
            hold.set()
            await task
            await self.host.settle(timeout=30)

        sup.run(_go(), timeout=60)
        deliveries = [r.get("body", {}).get("delivery") for r in self.receipts() if r.get("stage") == "transport"]
        self.assertNotIn("sent", deliveries, self.receipts())
        self.assertEqual([], self.model_turns())

        sup.unload_nunchi(self.loaded)
        self._load_nunchi(timeout_seconds=1.5)
        self.host = sup.ProbeHost(home=self.home, client=self.client)
        hold = asyncio.Event()
        self.client.reaction_hold = hold
        self.client.reaction_started = threading.Event()
        self.attend("ACK")
        late = self.human("late ack")

        async def _late() -> None:
            task = asyncio.create_task(self.host.deliver(late))
            await asyncio.sleep(2.2)
            hold.set()
            await task
            await self.host.settle(timeout=30)

        sup.run(_late(), timeout=60)
        late_deliveries = [r.get("body", {}).get("delivery") for r in self.receipts() if r.get("stage") == "transport" and r.get("body", {}).get("detail", "").find("late") >= -1]
        sent = [r for r in self.receipts() if r.get("stage") == "transport" and r.get("body", {}).get("delivery") == "sent"]
        self.assertEqual([], sent, self.receipts())
        self.assertEqual([], self.model_turns())

    def test_rollback_and_nonplugin_do_not_keep_the_ack_permit(self) -> None:
        from gateway.platforms.base import BasePlatformAdapter

        self.attend("ACK")
        message = self.human("before rollback")
        _deliver_and_settle(self.host, message)
        self.assertEqual(1, len(self._ears(message)))
        sup.unload_nunchi(self.loaded)
        self.loaded = None
        self.assertFalse(getattr(BasePlatformAdapter.handle_message, "__nunchi_v2_ingress__", False))
        stock_host = sup.ProbeHost(home=self.home, client=self.client)
        try:
            stock = self.human("stock after rollback")
            self.server.script({"content": "plain stock reply"})
            admitted = _deliver_and_settle(stock_host, stock)
            self.assertTrue(admitted)
            self.assertEqual([], self._ears(stock))
            self.assertEqual(1, len(self.model_turns()))
        finally:
            sup.run(stock_host.close(), timeout=20)


def _event_id_from_prompt(body: dict[str, Any]) -> str:
    """Pull the canonical event id Nunchi put in the attention projection."""

    text = json.dumps(body.get("messages", []))
    marker = "discord:message:"
    start = text.find(marker)
    if start < 0:
        return "discord:message:unknown"
    end = start + len(marker)
    while end < len(text) and text[end].isdigit():
        end += 1
    return text[start:end]


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
