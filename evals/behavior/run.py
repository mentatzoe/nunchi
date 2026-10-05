"""Run behavior scenes against real attention models.

Usage:

    python3 -m evals.behavior.run --list
    python3 -m evals.behavior.run --dry-run
    NUNCHI_OPENROUTER=... python3 -m evals.behavior.run \\
        --models google/gemini-3.8-flash,openai/gpt-6-luna --runs 3

Each moment is judged through the production path: the scene's events go
through `ObservationProvider`, the snapshot through `AttentionEngine` with
the default policy, and the model through `OpenAICompatibleAttentionModel`.
The runner writes `results.jsonl` (every call), `summary.md`, and `run.json`
(what ran, never the key) to `--out`.

`--dry-run` replaces the model with an offline one that always wakes, so the
plumbing can be checked without a network or a key.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Mapping
import urllib.error

from nunchi import __version__
from nunchi.ack import AckPolicy, ReactionCapability
from nunchi.attention import (
    AttentionEngine,
    AttentionError,
    AttentionPolicy,
    OpenAICompatibleAttentionModel,
    ParticipantProfile,
    _validate_model_judgment,
)
from nunchi.adapters.decisions_api import DEFAULT_URL as DECISIONS_URL, DecisionsAttentionModel
from nunchi.attention_questions import answers_leaning
from nunchi.observation import ObservationProvider, ParticipantBinding
from nunchi.participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
    TransportResult,
)
from nunchi.participant_model import OpenAICompatibleParticipant
from nunchi.pipeline import NunchiV2Pipeline
from nunchi.receipts import ReceiptJournal

from .scene import SCENES, Moment, Scene, load_scenes, parse_offset, profile_sha256
from .score import cell, collective_silence, grade, pile_on, visible_result


DEFAULT_MODELS = (
    "google/gemini-3.8-flash",
    "openai/gpt-6-luna",
    "qwen/qwen3.8-flash",
    "anthropic/claude-haiku-4.5",
    "z-ai/glm-5.3-flash",
    "deepseek/deepseek-v4.1-flash",
    "typesafe/jev-1.13",
)
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_KEY_ENV = "NUNCHI_OPENROUTER"
DRY_RUN_MODEL = "offline/always-wake"
DRY_RUN_AGENT = "offline/always-speaks"
ACK_REACTION = "👂"
AGENT_TIMEOUT_SECONDS = 90.0


class OfflineModel:
    """Always wakes with a one-line reading; checks the plumbing without a network."""

    name = "participant-attention"
    provider = "offline"

    def __init__(self, model_id: str = DRY_RUN_MODEL) -> None:
        self.model_id = model_id

    def judge(self, *, instructions, projection, timeout_seconds):
        return {
            **answers_leaning("WAKE"),
            "notes": [
                {"note": "offline dry run", "evidence_event_ids": [projection["trigger_event_id"]]}
            ],
        }


class RecordingModel:
    """Pass-through that keeps the raw judgment, any error, and the latency."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.name = inner.name
        self.provider = inner.provider
        self.model_id = inner.model_id
        self.raw: Any = None
        self.error: str | None = None
        self.raw_reply: Any = None
        self.latency_ms: int | None = None

        if callable(getattr(inner, "answer", None)):
            # A typed decision model answers the questions natively.
            self.answer = self._answer

    def judge(self, **kwargs: Any) -> Mapping[str, Any]:
        return self._record(self.inner.judge, kwargs)

    def _answer(self, **kwargs: Any) -> Mapping[str, Any]:
        return self._record(self.inner.answer, kwargs)

    def _record(self, call: Callable[..., Any], kwargs: Mapping[str, Any]) -> Mapping[str, Any]:
        started = time.monotonic()
        try:
            self.raw = call(**kwargs)
            return self.raw
        except BaseException as exc:
            self.error = _describe_error(exc)
            self.raw_reply = _raw_reply(self.inner)
            raise
        finally:
            self.latency_ms = int((time.monotonic() - started) * 1000)


class OfflineAgent:
    """Always speaks; checks the agent plumbing without a network."""

    def run_protocol(self, *, wake, opportunity, expand, cancel):
        return {
            "kind": "message",
            "origin_event_id": wake["trigger_event_id"],
            "text": "offline dry run",
        }


class RecordingAgent:
    """Pass-through for the simulated agent that keeps what it saw and did.

    It keeps the wake's attention block, every context page the agent asked
    for, its action, and any error. With ``paired``, a turn whose wake
    carries a reading is played a second time on the same wake with the
    reading removed and the source kept. That second action is recorded and
    graded but never dispatched, so each turn shows what the reading changed
    at the same moment.
    """

    def __init__(
        self,
        inner: Any,
        *,
        paired: bool = False,
        arrive: Callable[[], None] | None = None,
    ) -> None:
        self.inner = inner
        self.paired = paired
        # Messages that arrive while the agent is composing its turn.
        self.arrive = arrive
        self.called = False
        self.action: Any = None
        self.error: str | None = None
        self.raw_reply: Any = None
        self.latency_ms: int | None = None
        self.attention: Mapping[str, Any] | None = None
        self.expansions: list[dict[str, Any]] = []
        self.without_reading: dict[str, Any] | None = None
        self.usage: dict[str, Any] | None = None

    def _usage_since(self, start: int) -> dict[str, Any] | None:
        log = getattr(self.inner, "usage_log", None)
        return usage_total(log[start:]) if isinstance(log, list) else None

    def _calls_so_far(self) -> int:
        return len(getattr(self.inner, "usage_log", None) or ())

    def run_protocol(self, *, wake: Mapping[str, Any], expand: Any, **kwargs: Any) -> Any:
        self.called = True
        self.attention = deepcopy(dict(wake.get("attention", {})))
        if self.arrive is not None:
            arrive, self.arrive = self.arrive, None
            arrive()
        started = time.monotonic()
        first_call = self._calls_so_far()
        try:
            self.action = self.inner.run_protocol(
                wake=wake, expand=self._recorded(expand, "with reading"), **kwargs
            )
        except BaseException as exc:
            self.error = _describe_error(exc)
            self.raw_reply = _raw_reply(self.inner)
            raise
        finally:
            self.latency_ms = int((time.monotonic() - started) * 1000)
            self.usage = self._usage_since(first_call)
        if self.paired and self.attention.get("advice"):
            self.without_reading = self._play_without_reading(wake, expand, kwargs)
        return self.action

    def _play_without_reading(
        self, wake: Mapping[str, Any], expand: Any, kwargs: Mapping[str, Any]
    ) -> dict[str, Any]:
        bare = deepcopy(dict(wake))
        bare["attention"] = {"source": wake["attention"]["source"]}
        # The second play gets its own fresh view of the same turn. Sharing the
        # first play's view would hide what that play already read, including
        # a message that arrived mid-turn.
        fork = getattr(getattr(expand, "__self__", None), "fork", None)
        if callable(fork):
            expand = fork().expand
        played: dict[str, Any] = {}
        started = time.monotonic()
        first_call = self._calls_so_far()
        try:
            played["action"] = self.inner.run_protocol(
                wake=bare, expand=self._recorded(expand, "without reading"), **kwargs
            )
        except Exception as exc:
            # The paired turn is a measurement; it never changes the real one.
            played["error"] = _describe_error(exc)
            raw = _raw_reply(self.inner)
            if raw is not None:
                played["raw_reply"] = raw
        played["latency_ms"] = int((time.monotonic() - started) * 1000)
        usage = self._usage_since(first_call)
        if usage is not None:
            played["usage"] = usage
        return played

    def _recorded(self, expand: Any, arm: str) -> Callable[..., Any]:
        def recorded(**request: Any) -> Any:
            entry: dict[str, Any] = {"arm": arm, "request": dict(request)}
            self.expansions.append(entry)
            try:
                page = expand(**request)
            except Exception as exc:
                entry["error"] = _describe_error(exc)
                raise
            entry["events"] = len(page.get("events", ())) if isinstance(page, Mapping) else None
            return page

        return recorded


class RecordingEngine(AttentionEngine):
    """The production engine; keeps the last request and decision it made."""

    last_request: Mapping[str, Any] | None = None
    last_decision: Mapping[str, Any] | None = None

    def judge(self, request, **kwargs):
        decision = super().judge(request, **kwargs)
        self.last_request = request
        self.last_decision = decision
        return decision


class EvalTransport:
    """Records every visible move: Nunchi's ACK and the agent's own actions."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, *, action, wake):
        self.calls.append(deepcopy(dict(action)))
        return TransportResult("sent", f"eval:{len(self.calls)}")

    def reaction_capability(self) -> ReactionCapability:
        return ReactionCapability(
            supported=True,
            authenticated=True,
            operations=("add", "remove"),
            reactions=("*",),
            permissions_revision="behavior-eval",
        )


def agent_move(calls: list[Mapping[str, Any]]) -> str:
    """The move the room saw from the agent's own actions."""

    kinds = {call.get("kind") for call in calls}
    if kinds & {"message", "reply"}:
        return "speak"
    if "reaction" in kinds:
        return "mhm"
    if kinds:
        return "other"
    return "stay_quiet"


def _attention_summary(attention: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """What the agent was told about attention: the source and the reading's size."""

    if attention is None:
        return None
    return {
        "source": attention.get("source"),
        "reading_items": len(attention.get("advice", ())),
    }


def _describe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    cause = exc.__cause__
    if isinstance(cause, urllib.error.HTTPError):
        try:
            body = cause.read(600).decode("utf-8", "replace")
        except Exception:
            body = ""
        text += f" ({body.strip()})" if body else ""
    elif cause is not None:
        text += f" ({type(cause).__name__}: {cause})"
    return text


ModelFactory = Callable[[str], Any]
AgentFactory = Callable[[ParticipantProfile], Any]


def invalid_reason(raw: Any, event_ids: set[str], trigger_event_id: str) -> str:
    """Why the engine rejected a reply that the model did return."""

    try:
        _validate_model_judgment(raw, event_ids=event_ids, trigger_event_id=trigger_event_id)
    except AttentionError as exc:
        return str(exc)
    return "the decision failed the attention contract check"


TYPED_DECISION_PREFIX = "typesafe/"

# A chat model may carry a reasoning effort after "@", for example
# "deepseek/deepseek-v4.1-flash@low", so one run can compare efforts side by
# side. Without one, the provider's default applies. "off" turns reasoning
# off, for models that take only on/off or a token budget (OpenRouter lists
# Qwen3.8 Flash so). Which efforts a model accepts is the provider's to say;
# a refused effort fails that model's calls.
REASONING_EFFORTS = ("off", "none", "minimal", "low", "medium", "high", "xhigh", "max")
# The agent's replies are short JSON. Without a cap, OpenRouter reserves the
# model's whole output limit against the credit balance on every call.
AGENT_MAX_TOKENS = 4096


def model_spec(label: str) -> tuple[str, str | None]:
    """Split a model label into the provider's model id and a reasoning effort."""

    model_id, at, effort = label.partition("@")
    if not model_id:
        raise ValueError(f"model {label!r} has no id")
    if not at:
        return model_id, None
    if effort not in REASONING_EFFORTS:
        raise ValueError(f"model {label!r}: reasoning effort must be one of {', '.join(REASONING_EFFORTS)}")
    if is_typed_decision_model(model_id):
        raise ValueError(f"model {label!r}: a typed decision model takes no reasoning effort")
    return model_id, effort


def _count(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return value


def call_usage(response: Any) -> dict[str, Any]:
    """Tokens, cost, and the serving provider of one model call, when reported.

    Reads the OpenAI-compatible shape (``prompt_tokens``, ``completion_tokens``,
    ``completion_tokens_details.reasoning_tokens``) and the Decisions API shape
    (``input_tokens``, ``output_tokens``); ``cost`` is the provider's own figure.
    """

    if not isinstance(response, Mapping):
        return {}
    usage = response.get("usage") if isinstance(response.get("usage"), Mapping) else {}
    details = usage.get("completion_tokens_details")
    entry = {
        "model": response.get("model") if isinstance(response.get("model"), str) else None,
        "provider": response.get("provider") if isinstance(response.get("provider"), str) else None,
        "prompt_tokens": _count(usage.get("prompt_tokens", usage.get("input_tokens"))),
        "completion_tokens": _count(usage.get("completion_tokens", usage.get("output_tokens"))),
        "reasoning_tokens": _count(details.get("reasoning_tokens")) if isinstance(details, Mapping) else None,
        "cost": _count(usage.get("cost")),
    }
    return {key: value for key, value in entry.items() if value is not None}


def usage_total(calls: list[Mapping[str, Any]]) -> dict[str, Any]:
    """The usage of several calls added up, with the providers that served them."""

    total: dict[str, Any] = {"calls": len(calls)}
    for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cost"):
        values = [call[key] for call in calls if key in call]
        if values:
            total[key] = round(sum(values), 8) if key == "cost" else sum(values)
    providers = sorted({call["provider"] for call in calls if "provider" in call})
    if providers:
        total["providers"] = providers
    return total


def is_typed_decision_model(model_id: str) -> bool:
    return model_id.startswith(TYPED_DECISION_PREFIX) or model_id.startswith("~" + TYPED_DECISION_PREFIX)


def openai_compatible_factory(
    *,
    api_key: str,
    base_url: str,
    temperature: float | None,
    jev_url: str = DECISIONS_URL,
) -> ModelFactory:
    """Build each attention model: a typed decision model (``typesafe/``,
    such as Jev) through the Decisions API, any other model through the
    OpenAI-compatible chat endpoint. Both answer the same typed questions."""

    openrouter = "openrouter.ai" in base_url

    def build(label: str) -> Any:
        model_id, effort = model_spec(label)
        if is_typed_decision_model(model_id):
            return DecisionsAttentionModel(model=model_id, api_key=api_key, url=jev_url)
        extra: dict[str, Any] = {}
        if openrouter:
            # OpenRouter reports each call's cost only when asked.
            extra["usage"] = {"include": True}
        if effort is not None and openrouter:
            extra["reasoning"] = {"enabled": False} if effort == "off" else {"effort": effort}
        elif effort is not None:
            extra["reasoning_effort"] = "none" if effort == "off" else effort
        return OpenAICompatibleAttentionModel(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            provider="openrouter" if openrouter else "openai-compatible",
            temperature=temperature,
            extra_body=extra or None,
        )

    return build


class RecordingParticipant(OpenAICompatibleParticipant):
    """The simulated agent, keeping its latest raw reply.

    When the turn protocol rejects a reply, the record carries that reply so
    the failure can be read, as it does for attention's rejected replies.
    """

    last_reply: Any = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # One entry per model call, in order; the agent splits it by play.
        self.usage_log: list[dict[str, Any]] = []

    def _invoke(self, protocol: Any) -> Any:
        self.last_reply = None
        try:
            self.last_reply = super()._invoke(protocol)
            return self.last_reply
        finally:
            if self.last_response is not None:
                self.usage_log.append(call_usage(self.last_response))


RAW_REPLY_MAX_CHARS = 4000


def _raw_reply(agent: Any) -> Any:
    reply = getattr(agent, "last_reply", None)
    if isinstance(reply, str) and len(reply) > RAW_REPLY_MAX_CHARS:
        return reply[:RAW_REPLY_MAX_CHARS] + "…"
    return reply


def openai_compatible_agent_factory(
    *, api_key: str, base_url: str, model: str
) -> AgentFactory:
    def build(profile: ParticipantProfile) -> Any:
        openrouter = "openrouter.ai" in base_url
        return RecordingParticipant(
            profile=profile,
            model=model,
            api_key=api_key,
            base_url=base_url,
            provider="openrouter" if openrouter else "openai-compatible",
            timeout_seconds=AGENT_TIMEOUT_SECONDS / 2,
            extra_body={"max_tokens": AGENT_MAX_TOKENS, **({"usage": {"include": True}} if openrouter else {})},
        )

    return build


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_event(raw: Mapping[str, Any], *, at: datetime | None) -> dict[str, Any]:
    if raw.get("type", "message") == "reaction":
        event: dict[str, Any] = {
            "id": raw["id"],
            "type": "reaction",
            "author_id": raw["author"],
            "target_event_id": raw["target"],
            "reaction": raw["reaction"],
            "operation": "add",
        }
    else:
        event = {
            "id": raw["id"],
            "type": "message",
            "author_id": raw["author"],
            "text": raw["text"],
            "mentioned_actor_ids": list(raw.get("mentions", [])),
            "mentions_room": bool(raw.get("mentions_room", False)),
        }
        if "reply_to" in raw:
            event["reply_to_event_id"] = raw["reply_to"]
    if at is not None:
        event["timestamp"] = _timestamp(at)
    return event


def _event_actors(scene: Scene, raw: Mapping[str, Any]) -> dict[str, Any]:
    referenced = {raw["author"], *raw.get("mentions", [])}
    return {actor_id: dict(scene.actors[actor_id]) for actor_id in referenced}


@dataclass
class Job:
    scene: Scene
    moment_index: int
    participant: str
    model: str
    run: int

    @property
    def moment(self) -> Moment:
        return self.scene.moments[self.moment_index]


def _not_simulated(**_: Any) -> None:
    """Stands in for the agent when only attention is evaluated."""

    return None


def judge_moment(
    job: Job,
    factory: ModelFactory,
    *,
    timeout_seconds: float,
    agent_factory: AgentFactory | None = None,
    ack: str = "agent",
    paired: bool = False,
    reading_items: int = 4,
    reading_chars: int = 400,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run one moment through the production pipeline and grade what the room saw.

    Observation, attention, the participant host, and ACK are Nunchi's own.
    With an agent factory, a model plays the woken agent's turn through the
    shared participant protocol; without one, a woken agent counts as
    "agent decides". By default (``ack="agent"``) Nunchi never nods itself:
    an ACK judgment gives the agent a turn, and any "mhm" is the agent's own.
    ``ack="nunchi"`` turns Nunchi's own nod back on. With ``paired``, a turn
    that carried a reading is also played without it.
    """

    scene, moment, participant = job.scene, job.moment, job.participant
    record: dict[str, Any] = {
        "scene": scene.id,
        "moment": job.moment_index,
        "label": moment.label,
        "participant": participant,
        "model": job.model,
        "run": job.run,
        "provider_error": False,
    }
    if moment.is_pause:
        record.update(
            result="unsupported",
            grade=grade(moment, "unsupported"),
            detail="today's V2 has no route that looks again after a pause",
        )
        return record

    last = scene.event_index(moment.seen_through or moment.event)
    observed = scene.events[: last + 1]
    # The latest observed event happens now; a judged event may be older than
    # later context (a late judgment), so take the smallest offset.
    end_offset = min((parse_offset(raw["at"]) for raw in observed if "at" in raw), default=0)
    now = now or datetime.now(timezone.utc)
    profile_doc = scene.profiles[participant]
    binding = ParticipantBinding(
        participant_id=participant,
        actor_id=participant,
        platform=scene.platform,
        room_id=f"eval-{scene.id}",
        continuity_scope_id=f"eval:{scene.id}",
        names=tuple(profile_doc.get("names", ())),
        role=profile_doc.get("role"),
    )
    profile = ParticipantProfile(
        profile_id=f"eval-{participant}",
        participant_id=participant,
        actor_id=participant,
        instructions=profile_doc["instructions"],
        provenance="trusted:behavior-eval",
        sha256=profile_sha256(profile_doc),
    )
    receipts = ReceiptJournal()
    observation = ObservationProvider(binding, receipts=receipts)
    transport = EvalTransport()
    ack_policy = AckPolicy(reaction=ACK_REACTION, enabled=ack == "nunchi")
    inner = factory(job.model)
    model = RecordingModel(inner)
    engine = RecordingEngine(
        profile=profile,
        model=model,
        policy=AttentionPolicy(
            timeout_seconds=timeout_seconds,
            reading_items=reading_items,
            reading_note_chars=reading_chars,
        ),
        receipts=receipts,
        ack_policy=ack_policy,
        reaction_capability_provider=transport.reaction_capability,
    )
    def arrive() -> None:
        # The scene's mid-turn messages reach the room after the wake was
        # built, so only looking again shows them to the agent.
        for event_id in moment.during_turn:
            raw = scene.events[scene.event_index(event_id)]
            observation.observe(
                delivery_id=f"d-{raw['id']}",
                event=canonical_event(raw, at=datetime.now(timezone.utc)),
                actors=_event_actors(scene, raw),
            )

    agent = (
        RecordingAgent(
            agent_factory(profile),
            paired=paired,
            arrive=arrive if moment.during_turn else None,
        )
        if agent_factory is not None
        else None
    )
    scheduler = ConversationOpportunityScheduler(f"{participant}:eval:{scene.id}")
    host = ParticipantTurnHost(
        observation=observation,
        participant=agent if agent is not None else _not_simulated,
        transport=transport,
        scheduler=scheduler,
        receipts=receipts,
        # A paired turn plays the agent twice before the real action is sent.
        participant_timeout_seconds=timeout_seconds + AGENT_TIMEOUT_SECONDS * (2 if paired else 1),
        ack_policy=ack_policy,
    )
    pipeline = NunchiV2Pipeline(
        observation=observation, attention=engine, host=host, scheduler=scheduler
    )
    token = None
    for raw in observed:
        at = None
        if "at" in raw:
            at = now - timedelta(seconds=parse_offset(raw["at"]) - end_offset)
        delivery = {
            "delivery_id": f"d-{raw['id']}",
            "event": canonical_event(raw, at=at),
            "actors": _event_actors(scene, raw),
        }
        if raw["id"] == moment.event:
            _, token = pipeline.observe_and_offer(**delivery)
        else:
            observation.observe(**delivery)
    if token is None:
        # The transport keeps the participant's own events from waking it.
        record.update(
            result="stay_quiet",
            by="transport",
            grade=grade(moment, "stay_quiet"),
            detail="own event: the transport does not wake the participant",
        )
        return record

    outcomes = pipeline.run_opportunities(token)
    decision = engine.last_decision
    if decision is None:
        detail = outcomes[0].operational_error if outcomes else "no opportunity ran"
        record.update(
            result="woken",
            grade=grade(moment, "woken"),
            provider_error=True,
            error=detail,
        )
        return record

    request = engine.last_request
    event_ids = [event["id"] for event in request["events"]]
    record["snapshot_event_ids"] = event_ids
    rejected = decision.get("error", {}).get("code") == "provider-failure"
    if rejected and model.raw is not None:
        # The model answered but the engine rejected the reply; keep it so the
        # failure can be diagnosed.
        record["raw_reply"] = model.raw
        record["invalid_reason"] = invalid_reason(model.raw, set(event_ids), request["trigger_event_id"])

    attention = visible_result(decision)
    result = attention
    by = {"stay_quiet": "attention", "mhm": "nunchi", "woken": None}[attention]
    provider_error = decision.get("status") == "error"
    if attention == "woken" and agent is not None:
        transport_result = outcomes[0].transport if outcomes else None
        failed = (
            agent.error is not None
            or (transport_result is not None and transport_result.delivery == "failed")
        )
        record["agent"] = {
            "action": agent.action,
            "latency_ms": agent.latency_ms,
            "attention": _attention_summary(agent.attention),
        }
        if agent.usage is not None:
            record["agent"]["usage"] = agent.usage
        if agent.expansions:
            record["agent"]["expansions"] = agent.expansions
        looked_again = [
            entry
            for entry in agent.expansions
            if entry["arm"] == "with reading" and entry["request"].get("direction") == "new"
        ]
        if looked_again:
            # How many new messages the agent was shown before it posted.
            record["agent"]["looked_again"] = sum(entry.get("events") or 0 for entry in looked_again)
        if failed:
            provider_error = True
            record["agent"]["error"] = agent.error or transport_result.detail
            if agent.raw_reply is not None:
                record["agent"]["raw_reply"] = agent.raw_reply
        else:
            result = agent_move(transport.calls)
            by = "agent"
        if agent.without_reading is not None:
            unread = dict(agent.without_reading)
            if "error" not in unread:
                action = unread.get("action")
                unread["move"] = agent_move([action] if action else [])
                unread["grade"] = grade(moment, unread["move"], attention=attention)["visible"]
            record["agent"]["without_reading"] = unread

    response = getattr(inner, "last_response", None)
    if isinstance(response, Mapping):
        if "answers" in response:
            # The typed answers behind the judgment, and the snapshot that served them.
            record["model_response"] = {
                key: response[key] for key in ("model", "answers", "usage") if key in response
            }
        usage = call_usage(response)
        if usage:
            record["attention_usage"] = usage
    evidence = set(decision.get("evidence_event_ids", []))
    record.update(
        result=result,
        by=by,
        grade=grade(moment, result, attention=attention),
        provider_error=provider_error,
        error=model.error,
        latency_ms=model.latency_ms,
        decision={
            key: decision[key]
            for key in (
                "status",
                "classifier_disposition",
                "effective_disposition",
                "routing_audit",
                "reasons",
                "evidence_event_ids",
                "attention_advice",
                "answers",
                "error",
            )
            if key in decision
        },
        cited=[bool(evidence & set(fact["events"])) for fact in moment.notice],
    )
    return record


def select_scenes(scenes: list[Scene], selector: str) -> list[Scene]:
    if selector in ("", "all"):
        return scenes
    wanted = [item.strip() for item in selector.split(",") if item.strip()]
    chosen = []
    for scene in scenes:
        groups: tuple[str, ...] = ()
        if scene.path and Path(scene.path).is_relative_to(SCENES):
            groups = Path(scene.path).relative_to(SCENES).parts[:-1]
        if any(item in groups or scene.id == item or scene.id.startswith(item) for item in wanted):
            chosen.append(scene)
    return chosen


def plan(scenes: list[Scene], models: list[str], runs: int) -> list[Job]:
    return [
        Job(scene, index, participant, model, run)
        for scene in scenes
        for index in range(len(scene.moments))
        for participant in scene.participants
        for model in models
        for run in range(runs)
    ]


def together_findings(scenes: list[Scene], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple, list[str]] = defaultdict(list)
    for record in records:
        by_key[(record["scene"], record["moment"], record["model"], record["run"])].append(record["result"])
    checks = {"not-all-quiet": ("collective silence", collective_silence), "no-pile-on": ("pile-on", pile_on)}
    findings = []
    for scene in scenes:
        for name in scene.together:
            label, failed = checks[name]
            for (scene_id, moment, model, run), results in sorted(by_key.items()):
                if scene_id == scene.id and len(results) == len(scene.participants) and failed(results):
                    findings.append(
                        {"scene": scene_id, "moment": moment, "model": model, "run": run, "kind": label}
                    )
    return findings


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, cwd=Path(__file__).parent
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def turn_source(record: Mapping[str, Any]) -> str:
    """How the agent got its turn: the wake source, and for DEFER, why."""

    source = ((record.get("agent") or {}).get("attention") or {}).get("source") or "unknown"
    if source != "DEFER":
        return source
    decision = record.get("decision", {})
    judged = decision.get("classifier_disposition", "?")
    valve = decision.get("routing_audit", {}).get("valve", "?")
    return "DEFER (model)" if judged == "DEFER" else f"{judged} widened to DEFER ({valve})"


def _agent_turn_sections(records: list[dict[str, Any]], *, paired: bool) -> list[str]:
    turns = [record for record in records if "agent" in record]
    lines = [
        "",
        "## What the agent saw",
        "",
        "Every agent turn by how it got its turn. *Reading* counts turns whose wake",
        "carried attention's reading.",
        "",
        "| Wake | Turns | Reading | Spoke | Quiet | Mhm | Fits | Miss | Errors |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in turns:
        by_source[turn_source(record)].append(record)
    for source in sorted(by_source):
        mine = by_source[source]
        moves = Counter(record["result"] for record in mine if record.get("by") == "agent")
        grades = Counter(record["grade"]["visible"] for record in mine if record.get("by") == "agent")
        lines.append(
            f"| {source} | {len(mine)} | "
            f"{sum(1 for record in mine if (record['agent'].get('attention') or {}).get('reading_items'))} | "
            f"{moves['speak']} | {moves['stay_quiet']} | {moves['mhm']} | {grades['fits']} | {grades['miss']} | "
            f"{sum(1 for record in mine if 'error' in record['agent'])} |"
        )
    looked = [record for record in turns if record["agent"].get("looked_again")]
    if looked:
        moves = Counter(record["result"] for record in looked)
        lines += [
            "",
            f"In {len(looked)} turn(s) others posted while the agent was composing, and it was "
            f"shown their messages before posting: it then spoke {moves['speak']}, stayed quiet "
            f"{moves['stay_quiet']}, and nodded {moves['mhm']} time(s).",
        ]
    if not paired:
        return lines
    pairs = [
        record
        for record in turns
        if record.get("by") == "agent"
        and "grade" in (record["agent"].get("without_reading") or {})
    ]
    lines += [
        "",
        "## The reading, paired",
        "",
        "Each turn that carried a reading was played again on the same wake without it.",
        "The second move is graded but never sent.",
        "",
        "| Wake | Pairs | Fits with / without | Miss with / without | Spoke with / without | Move changed |",
        "|---|---|---|---|---|---|",
    ]
    if not pairs:
        return lines[:-2] + ["No agent turn carried a reading."]
    by_source = defaultdict(list)
    for record in pairs:
        by_source[turn_source(record)].append(record)
    for source in sorted(by_source):
        mine = by_source[source]
        unread = [record["agent"]["without_reading"] for record in mine]
        lines.append(
            "| {} | {} | {} / {} | {} / {} | {} / {} | {} |".format(
                source,
                len(mine),
                sum(1 for record in mine if record["grade"]["visible"] == "fits"),
                sum(1 for item in unread if item["grade"] == "fits"),
                sum(1 for record in mine if record["grade"]["visible"] == "miss"),
                sum(1 for item in unread if item["grade"] == "miss"),
                sum(1 for record in mine if record["result"] == "speak"),
                sum(1 for item in unread if item["move"] == "speak"),
                sum(1 for record, item in zip(mine, unread) if record["result"] != item["move"]),
            )
        )
    failed = sum(
        1 for record in turns if "error" in (record["agent"].get("without_reading") or {})
    )
    if failed:
        lines += ["", f"{failed} paired turn(s) without the reading failed and are left out."]
    return lines


def _cost(value: float) -> str:
    return f"${value:.4f}"


def _cost_section(models: list[str], records: list[dict[str, Any]]) -> list[str]:
    """What each route cost and how many tokens it used, as the providers reported."""

    def agent_usage(record: Mapping[str, Any], arm: str) -> Mapping[str, Any]:
        agent = record.get("agent") or {}
        usage = (agent.get("without_reading") or {}).get("usage") if arm == "paired" else agent.get("usage")
        return usage or {}

    if not any(record.get("attention_usage") or agent_usage(record, "turn") for record in records):
        return []
    lines = [
        "",
        "## Cost and tokens",
        "",
        "As each provider reported it. A call that failed or timed out reports",
        "nothing, so it is not counted. *Per moment* is attention plus the agent's",
        "real turn, over every moment of that route; the paired play is a",
        "measurement and is listed apart.",
        "",
        "| Model | Attention calls reported / moments | Median tokens in / out / reasoning | Attention cost | Agent turns' cost | Per moment | Paired play cost | Providers |",
        "|---|---|---|---|---|---|---|---|",
    ]
    totals = Counter()
    for model in models:
        mine = [record for record in records if record["model"] == model and record["result"] != "unsupported"]
        calls = [record["attention_usage"] for record in mine if record.get("attention_usage")]

        def median(key: str) -> str:
            values = [call[key] for call in calls if key in call]
            return str(int(statistics.median(values))) if values else "-"

        attention = sum(call.get("cost", 0) for call in calls)
        turns = sum(agent_usage(record, "turn").get("cost", 0) for record in mine)
        paired = sum(agent_usage(record, "paired").get("cost", 0) for record in mine)
        totals.update(attention=attention, turns=turns, paired=paired)
        providers = Counter(call["provider"] for call in calls if "provider" in call)
        lines.append(
            "| `{}` | {}/{} | {} / {} / {} | {} | {} | {} | {} | {} |".format(
                model,
                len(calls),
                len(mine),
                median("prompt_tokens"),
                median("completion_tokens"),
                median("reasoning_tokens"),
                _cost(attention),
                _cost(turns),
                _cost((attention + turns) / len(mine)) if mine else "-",
                _cost(paired),
                ", ".join(f"{name} ({count})" for name, count in providers.most_common(3)) or "-",
            )
        )
    lines += [
        "",
        f"Reported cost of the whole run: {_cost(totals['attention'] + totals['turns'] + totals['paired'])}"
        f" (attention {_cost(totals['attention'])}, agent turns {_cost(totals['turns'])},"
        f" paired play {_cost(totals['paired'])}).",
    ]
    return lines


def summarize(
    scenes: list[Scene],
    models: list[str],
    records: list[dict[str, Any]],
    together: list[dict[str, Any]],
    meta: Mapping[str, Any],
) -> str:
    lines = [
        "# Behavior evaluation",
        "",
        f"- Started: {meta['started_at']}; finished: {meta['finished_at']}",
        f"- Commit: `{meta['git_sha']}`{' (dirty)' if meta['git_dirty'] else ''}; Nunchi {meta['nunchi_version']}",
        f"- Models: {', '.join(f'`{model}`' for model in models)}",
        f"- Runs per moment: {meta['runs']}; temperature: {meta['temperature']}; endpoint: {meta['base_url']}",
        f"- Scenes: {len(scenes)}; attention calls: {meta['calls']}; agent turns: {meta.get('agent_calls', 0)}; provider errors: {meta['provider_errors']}",
        f"- Command: `{meta['command']}`",
        f"- Reading: "
        + (
            f"up to {meta.get('reading_items', 4)} note{'' if meta.get('reading_items', 4) == 1 else 's'} "
            f"of up to {meta.get('reading_chars', 400)} characters"
            if meta.get("reading_items", 4)
            else "none asked for"
        ),
        "",
    ]
    if meta.get("agent_model"):
        lines[-1:-1] = [
            "- Mhm: "
            + (
                "the agent's own; an ACK judgment gives the agent a turn"
                if meta.get("ack") == "agent"
                else "sent by Nunchi on an ACK judgment"
            )
            + ("; each turn with a reading is also played without it" if meta.get("paired") else ""),
        ]
    if meta.get("agent_model"):
        lines += [
            f"Each moment runs through Nunchi's pipeline. When attention wakes the agent,",
            f"`{meta['agent_model']}` plays its turn through the shared participant",
            "protocol, and the move the room sees is graded. Step 1 is graded on",
            "attention alone. See `evals/behavior/score.py`.",
            "",
        ]
    else:
        lines += [
            "Today's V2 makes one attention decision per moment, and the agent's own",
            "move is not simulated in this run; woken runs count as *agent decides*.",
            "See `evals/behavior/score.py` for the grades.",
            "",
        ]
    failed = [record for record in records if record["provider_error"]]
    if failed:
        # A failed call wakes the agent under the default policy, so it would
        # read as "agent decides". Say up front that the results are incomplete.
        lines += [
            "## Provider errors",
            "",
            f"**{len(failed)} of {len(records)} runs had a failed attention or agent call, so these results are incomplete.**",
            "",
            "| Model | Errors | First error |",
            "|---|---|---|",
        ]
        for model in models:
            mine = [record for record in failed if record["model"] == model]
            if mine:
                engine_error = mine[0].get("decision", {}).get("error", {})
                agent_error = mine[0].get("agent", {}).get("error")
                first = (
                    mine[0].get("error")
                    or (mine[0].get("invalid_reason") and f"invalid reply: {mine[0]['invalid_reason']}")
                    or (agent_error and f"agent: {agent_error}")
                    or engine_error.get("detail")
                    or "unknown"
                )
                first = first.replace("|", "/").replace("\n", " ")
                lines.append(f"| `{model}` | {len(mine)} | {first[:300]} |")
        lines.append("")
    lines += [
        "## Per model",
        "",
        "| Model | Moments | Fits | Miss | Unlisted | Agent decides | Agent spoke / quiet / mhm | Step 1 over-suppress | Step 1 over-wake | Nunchi-sent mhm | Cited facts | Errors | Median ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model in models:
        mine = [record for record in records if record["model"] == model and record["result"] != "unsupported"]
        visible = Counter(record["grade"]["visible"] for record in mine)
        step1 = Counter(record["grade"]["step1"] for record in mine)
        cited = [flag for record in mine for flag in record.get("cited", [])]
        latencies = [record["latency_ms"] for record in mine if record.get("latency_ms") is not None]
        agent = Counter(record["result"] for record in mine if record.get("by") == "agent")
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                model,
                len(mine),
                visible["fits"],
                visible["miss"],
                visible["unlisted"],
                visible["agent-decides"],
                f"{agent['speak']} / {agent['stay_quiet']} / {agent['mhm']}" if meta.get("agent_model") else "-",
                step1["over-suppress"],
                step1["over-wake"],
                sum(1 for record in mine if record.get("by") == "nunchi"),
                f"{sum(cited)}/{len(cited)}" if cited else "-",
                sum(1 for record in mine if record["provider_error"]),
                int(statistics.median(latencies)) if latencies else "-",
            )
        )
    lines += _cost_section(models, records)
    if meta.get("agent_model"):
        lines += _agent_turn_sections(records, paired=bool(meta.get("paired")))
    if together:
        lines += ["", "## Collective checks", ""]
        for item in together:
            what = "every participant stayed quiet" if item["kind"] == "collective silence" else "every participant spoke"
            lines.append(
                f"- {item['kind']}: {item['scene']} moment {item['moment'] + 1}, `{item['model']}` run {item['run'] + 1}: {what}"
            )
    lines += [
        "",
        "## Moments",
        "",
        "Each cell has one letter per run: Q quiet (attention), q quiet (the agent's",
        "choice), M mhm sent by Nunchi, m the agent's own mhm, S the agent spoke,",
        "O another agent action, W woken (agent not simulated), E an error, and a",
        "dash where today's V2 has no route. A trailing `!` marks a clear miss in",
        "some run; `?` marks an unlisted move.",
        "",
        "| Scene | Moment | Who | Step 1 | Fitting | " + " | ".join(f"`{model}`" for model in models) + " |",
        "|---|---|---|---|---|" + "---|" * len(models),
    ]
    grouped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(record["scene"], record["moment"], record["participant"], record["model"])].append(record)
    for scene in scenes:
        for index, moment in enumerate(scene.moments):
            for participant in scene.participants:
                cells = [
                    cell(sorted(grouped[(scene.id, index, participant, model)], key=lambda item: item["run"]))
                    for model in models
                ]
                lines.append(
                    f"| {scene.id} | {moment.label} | {participant} | {moment.step1} | {', '.join(moment.fitting)} | "
                    + " | ".join(cells)
                    + " |"
                )
    misses = [record for record in records if record["grade"]["visible"] == "miss"]
    if misses:
        lines += ["", "## Clear misses", ""]
        by_scene = {scene.id: scene for scene in scenes}
        for record in misses:
            moment = by_scene[record["scene"]].moments[record["moment"]]
            reasons = "; ".join(record.get("decision", {}).get("reasons", [])) or record.get("detail", "")
            lines.append(
                f"- **{record['scene']}** ({moment.label}, {record['participant']}), `{record['model']}` run {record['run'] + 1}: "
                f"{record['result']}. Scene: {moment.miss_reason(record['result'])} Model: {reasons}"
            )
    unsupported = sorted({(record["scene"], record["label"]) for record in records if record["result"] == "unsupported"})
    if unsupported:
        lines += ["", "## Not supported today", ""]
        lines += [f"- {scene_id}: {label}" for scene_id, label in unsupported]
    drafts = [scene.id for scene in scenes if scene.review.startswith("draft")]
    if drafts:
        lines += ["", f"{len(drafts)} of {len(scenes)} scenes are drafts awaiting Zoe's review of their ranges."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--scenes", default="all", help="all, behavior, litmus, a litmus category, or scene ids/prefixes")
    parser.add_argument("--out", default="behavior-eval-out")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--jev-url",
        default=DECISIONS_URL,
        help="Decisions API endpoint for typesafe/ models",
    )
    parser.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--per-model",
        type=int,
        default=3,
        help="at most this many calls to one model at a time (rate limits)",
    )
    parser.add_argument(
        "--agent-model",
        default="",
        help="model that plays the woken agent's turn; empty grades attention alone",
    )
    parser.add_argument(
        "--ack",
        choices=("agent", "nunchi"),
        default="agent",
        help="who sends the mhm on an ACK judgment: the agent in its own turn (the default), or Nunchi itself",
    )
    parser.add_argument(
        "--paired",
        action="store_true",
        help="also play each agent turn that carried a reading without it, on the same wake",
    )
    parser.add_argument(
        "--reading-items",
        type=int,
        default=4,
        help="ask attention for at most this many reading notes (0 asks for none)",
    )
    parser.add_argument(
        "--reading-chars",
        type=int,
        default=400,
        help="ask for reading notes of at most this many characters (40 to 400)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    scenes = select_scenes(load_scenes(), args.scenes)
    if not scenes:
        parser.error(f"no scenes match {args.scenes!r}")
    if args.list:
        for scene in scenes:
            print(f"{scene.id:48} {len(scene.moments)} moment(s)  {scene.review[:40]}")
        return 0
    if args.runs < 1 or args.workers < 1 or args.per_model < 1:
        parser.error("--runs, --workers and --per-model must be positive")
    if args.paired and not args.agent_model:
        parser.error("--paired needs --agent-model")
    try:
        AttentionPolicy(reading_items=args.reading_items, reading_note_chars=args.reading_chars)
    except ValueError as exc:
        parser.error(str(exc))

    agent_factory: AgentFactory | None = None
    if args.dry_run:
        models = [DRY_RUN_MODEL]
        factory: ModelFactory = OfflineModel
        if args.agent_model:
            agent_factory = lambda profile: OfflineAgent()  # noqa: E731
    else:
        models = [item.strip() for item in args.models.split(",") if item.strip()]
        for model in models:
            try:
                model_spec(model)
            except ValueError as exc:
                parser.error(str(exc))
        api_key = os.environ.get(args.key_env)
        if not api_key:
            parser.error(f"set {args.key_env} to the provider key, or use --dry-run")
        factory = openai_compatible_factory(
            api_key=api_key,
            base_url=args.base_url,
            temperature=args.temperature,
            jev_url=args.jev_url,
        )
        if args.agent_model:
            agent_factory = openai_compatible_agent_factory(
                api_key=api_key, base_url=args.base_url, model=args.agent_model
            )

    jobs = plan(scenes, models, args.runs)
    slots = {model: threading.Semaphore(args.per_model) for model in models}

    def run_job(job: Job) -> dict[str, Any]:
        with slots[job.model]:
            return judge_moment(
                job,
                factory,
                timeout_seconds=args.timeout,
                agent_factory=agent_factory,
                ack=args.ack,
                paired=args.paired,
                reading_items=args.reading_items,
                reading_chars=args.reading_chars,
            )

    started = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(run_job, jobs))
    finished = datetime.now(timezone.utc)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    together = together_findings(scenes, records)
    meta = {
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "nunchi_version": __version__,
        "python": platform.python_version(),
        "command": " ".join(["python3 -m evals.behavior.run", *(argv if argv is not None else sys.argv[1:])]),
        "models": models,
        "reasoning_efforts": {model: model_spec(model)[1] for model in models if model_spec(model)[1]},
        "agent_model": (DRY_RUN_AGENT if args.dry_run else args.agent_model) if args.agent_model else None,
        "ack": args.ack,
        "paired": args.paired,
        "reading_items": args.reading_items,
        "reading_chars": args.reading_chars,
        "runs": args.runs,
        "temperature": None if args.dry_run else args.temperature,
        "timeout_seconds": args.timeout,
        "workers": args.workers,
        "per_model": args.per_model,
        "base_url": "offline" if args.dry_run else args.base_url,
        "jev_url": args.jev_url if not args.dry_run and any(is_typed_decision_model(model) for model in models) else None,
        "key_env": None if args.dry_run else args.key_env,
        "scenes": [scene.id for scene in scenes],
        "calls": sum(1 for record in records if record["result"] != "unsupported" and "decision" in record),
        "agent_calls": sum(1 for record in records if "agent" in record),
        "provider_errors": sum(1 for record in records if record["provider_error"]),
        "collective_silence": together,
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = summarize(scenes, models, records, together, meta)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    if meta["provider_errors"]:
        print(f"{meta['provider_errors']} provider error(s): the results are incomplete", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
