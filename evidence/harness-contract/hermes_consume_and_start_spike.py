"""Nunchi step 9b spike: a plugin consumes every room message and starts turns itself.

Built on Hermes's own test pattern (tests/gateway/test_plugin_origin_injection.py): the real
GatewayRunner and BasePlatformAdapter ingress with a recording transport; only the model call
(``_run_agent_inner``) is replaced. Questions:

1. post_gateway_admission returning ``handled`` with no reply consumes a person's message silently.
2. A plugin-injected turn whose answer is a bare "[SILENT]" sends nothing; a normal answer is sent.
3. While an injected turn runs, a person's message in the same chat still reaches the hook.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import hermes_yaml as yaml

import gateway.run as gateway_run
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from gateway.run import GatewayRunner
from hermes_cli.plugins import PluginContext, PluginManifest, get_plugin_manager

PLUGIN = "nunchi"
ROOM = "room-1"


class _RecordingAdapter(BasePlatformAdapter):
    def __init__(self, per_user=True):
        super().__init__(PlatformConfig(enabled=True, token="tok",
                                        extra={"group_sessions_per_user": per_user}), Platform.TELEGRAM)
        self.sent: list[tuple[str, str]] = []
        self._running = True

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        return True

    async def disconnect(self) -> None:
        self._mark_disconnected()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append((str(chat_id), content))
        return SendResult(success=True, message_id=str(len(self.sent)))

    async def send_typing(self, chat_id, metadata=None):
        return None

    async def get_chat_info(self, chat_id):
        return {"id": chat_id, "type": "group"}


@pytest.fixture(params=[True, False], ids=["per-user-sessions", "shared-sessions"])
def gateway(request, tmp_path, monkeypatch):
    home = tmp_path / "hh"
    home.mkdir()
    (home / "config.yaml").write_text(yaml.safe_dump({
        "plugins": {"entries": {PLUGIN: {"allow_gateway_injection": True}}},
    }), encoding="utf-8")
    # u1 is a person; nunchi-turns is the identity the plugin's injected turns run as.
    (home / ".env").write_text("TELEGRAM_ALLOWED_USERS=u1,nunchi-turns\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    for key in ("GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "u1,nunchi-turns")
    monkeypatch.setattr(gateway_run, "_hermes_home", home)

    runner = GatewayRunner(GatewayConfig(sessions_dir=home / "sessions",
                                         group_sessions_per_user=request.param))
    adapter = _RecordingAdapter(per_user=request.param)
    runner.adapters = {Platform.TELEGRAM: adapter}
    adapter.gateway_runner = runner
    adapter.set_message_handler(runner._handle_message)

    turns = []
    answers = []          # what each turn answers, in order
    gates = []            # optional asyncio.Event per turn: the turn waits on it

    async def _fake_turn(message, context_prompt, history, source, session_id, **_kwargs):
        index = len(turns)
        turns.append(SimpleNamespace(message=message, user=source.user_id, session_id=session_id))
        if index < len(gates) and gates[index] is not None:
            await gates[index].wait()
        return {"final_response": answers[index], "messages": [], "tools": [],
                "history_offset": len(history), "last_prompt_tokens": 0}

    runner._run_agent_inner = _fake_turn

    manager = get_plugin_manager()
    manager._discovered = True
    ctx = PluginContext(PluginManifest(name=PLUGIN, key=PLUGIN, source="user"), manager)
    seen = []

    def consume(session_key, platform, source, message_id, text, **_kwargs):
        seen.append((source.get("user_id"), text))
        return {"action": "handled"}  # no reply: consume silently

    ctx.register_hook("post_gateway_admission", consume)
    with patch("hermes_cli.plugins._known_plugin_managers", return_value=[manager]):
        yield SimpleNamespace(runner=runner, adapter=adapter, ctx=ctx, turns=turns,
                              answers=answers, gates=gates, seen=seen)


async def _publish(runner):
    runner._gateway_loop = asyncio.get_running_loop()
    runner._running = True
    runner._install_plugin_message_injector()


async def _settle(runner, adapter, rounds: int = 300):
    for _ in range(rounds):
        await asyncio.sleep(0.01)
        if not runner._background_tasks and not adapter._session_tasks and not adapter._active_sessions:
            return


def _origin():
    return {"platform": "telegram", "chat_id": ROOM, "chat_type": "group",
            "user_id": "nunchi-turns", "user_name": "Nunchi"}


async def _person_says(adapter, text):
    source = adapter.build_source(chat_id=ROOM, chat_type="group", user_id="u1", user_name="Sam")
    await adapter.handle_message(MessageEvent(text=text, message_type=MessageType.TEXT, source=source))


@pytest.mark.asyncio
async def test_consume_then_injected_turns_can_stay_silent_or_speak(gateway):
    runner, adapter = gateway.runner, gateway.adapter
    await _publish(runner)

    await _person_says(adapter, "anyone around?")
    await _settle(runner, adapter)
    assert gateway.seen == [("u1", "anyone around?")]
    assert gateway.turns == [] and adapter.sent == []          # consumed: no run, no reply

    gateway.answers.extend(["[SILENT]", "Hi Sam, I'm here."])
    assert gateway.ctx.inject_message("Nunchi turn 1", origin=_origin()) is True
    await _settle(runner, adapter)
    assert len(gateway.turns) == 1 and gateway.turns[0].message.endswith("Nunchi turn 1")
    assert adapter.sent == []                                   # injected [SILENT] stays silent

    assert gateway.ctx.inject_message("Nunchi turn 2", origin=_origin()) is True
    await _settle(runner, adapter)
    assert adapter.sent == [(ROOM, "Hi Sam, I'm here.")]        # a normal answer is delivered
    assert gateway.turns[1].session_id == gateway.turns[0].session_id  # one Nunchi session


@pytest.mark.asyncio
async def test_a_person_speaking_during_an_injected_turn_still_reaches_the_hook(gateway):
    runner, adapter = gateway.runner, gateway.adapter
    await _publish(runner)
    hold = asyncio.Event()
    gateway.gates.append(hold)
    gateway.answers.append("[SILENT]")

    assert gateway.ctx.inject_message("Nunchi turn", origin=_origin()) is True
    for _ in range(100):
        await asyncio.sleep(0.01)
        if gateway.turns:
            break
    assert len(gateway.turns) == 1                              # the injected turn is running

    await _person_says(adapter, "actually, never mind")
    await asyncio.sleep(0.2)
    assert gateway.seen == [("u1", "actually, never mind")]     # the hook saw it mid-turn
    assert len(gateway.turns) == 1                              # and it started no run of its own

    hold.set()
    await _settle(runner, adapter)
    assert adapter.sent == []
