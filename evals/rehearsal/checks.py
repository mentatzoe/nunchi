"""The probe's hard checks, and what it reports without judging (step 9f, PR 1).

A pass means exactly this: the pinned harness, run as a clean user, reached
its model and took part in the room through Nunchi, with live attention
judging. Each hard check that fails fails the harness, and its reason leads
summary.md:

1. **pins-and-isolation**: the harness is the pinned version; the homes its
   integration handed it (HOME, TMPDIR, and CODEX_HOME, HERMES_HOME or
   CLAUDE_CONFIG_DIR) are under the run's directory; the real user's
   ``~/.codex`` and ``~/.hermes`` were not created or changed; no process
   the run recorded got a key but the harness's own (Nunchi's keys stay in
   Nunchi's process), and the agent's own commands get no key at all where
   the harness's builder shows their environment (Hermes's terminal); and
   the harness showed nothing that says it ran otherwise than configured
   (Claude Code: a model it did not recognize, or another permission mode
   than the pinned version starts in for that model).
2. **record-complete**: the record holds what AGENTS.md asks for.
3. **turns-bound-and-ended**: at least one wake reached the harness, and
   every turn the library handed it was bound to its wake and ended with the
   harness's own result. The participant-host receipt is authoritative: a
   turn the host recorded as ``unknown`` with nothing handed to the room was
   cancelled, timed out or failed. A named failure fails too: the harness
   did not take the turn, which is never read as silence. So does a turn
   the harness itself ended in error, even after its post (Claude Code's
   error result, Codex's failed turn), in the harness's own words.
4. **attention-judged**: attention returned at least one judgment. Failed
   calls, and the wakes their error fallback caused, are counted and listed.
5. **one-room-action-per-turn**: no turn made more than one room action,
   and each was delivered: it reads ``sent``, or, for a harness that posts
   its final answer itself (Hermes), the room received exactly that text.
6. **no-leaks**: the room got only what the library committed, and no
   committed post names Nunchi's machinery: the conformance kit's own count
   (`nunchi.turn_conformance.leaks`). A gap the integration declares reads as
   a failure with its name, never as a pass.
7. **scripted-outcomes** (``--scripted`` only): with the model and attention
   scripted, each moment's outcome is known, so it is checked.

A run in the Discord room (``--room discord``, PR 3b) holds seven more, the
``discord-*`` checks, listed with them below.

Neither the key nor the canary may be in any output: the scan
(`scan.enforce`) fails the run after the record is written.

In a live run, whether a moment got a post or no turn is the model's to
decide: the probe reports it next to what the moment expects, and never
fails on it. A moment whose graded message never reached Nunchi reads ``not
delivered``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from nunchi.turn_conformance import KnownGap, Played, leaks

# The scenario name the probe's declared known gaps are scoped to (`KnownGap.covers`).
PROBE_SCENARIO = "rehearsal-probe"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str

    def document(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


def pins_and_isolation(
    *,
    harness_version: str | None,
    expected: str,
    actual_homes: Mapping[str, str],
    base: str,
    user_homes_before: Sequence[Mapping[str, Any]],
    user_homes_after: Sequence[Mapping[str, Any]],
    processes: Sequence[Mapping[str, Any]] = (),
    harness_keys: Sequence[str] = (),
    canary: str = "",
    not_as_configured: Sequence[str] = (),
) -> Check:
    """The pinned harness, run as a clean user and as configured, the real user's homes untouched, and keys kept where they belong.

    ``actual_homes`` are the homes the integration handed the harness, read
    from the environment it starts the harness with (Hermes, in this process:
    the kit's own home under the run's TMPDIR). ``processes`` are the
    recorded commands and processes, each with the ``secrets`` among its
    variables (names); one marked ``agent_shell`` is the environment of the
    agent's own commands. A process may hold the harness's own key
    (``harness_keys``) and the ``canary``; the agent's shell only the canary.
    ``not_as_configured`` is what the harness showed of running otherwise
    than the probe set it up (`probe.claude_code_report`).
    """

    problems: list[str] = []
    if not harness_version or expected not in harness_version:
        problems.append(f"the harness is {harness_version!r}, not the pinned {expected}")
    problems += [f"the harness did not run as configured: {item}" for item in not_as_configured]
    if not actual_homes:
        problems.append("the harness's homes were not read")
    for name, path in actual_homes.items():
        if not path:
            problems.append(f"the harness got no {name}")
        elif not Path(path).is_relative_to(base):
            problems.append(f"the harness got a {name} outside the run's directory")
    for entry in processes:
        name = entry.get("process") or entry.get("what") or "a process"
        if entry.get("error"):
            problems.append(f"{name}: its environment could not be read ({entry['error']})")
            continue
        allowed = {canary} if entry.get("agent_shell") else {canary, *harness_keys}
        extra = [variable for variable in entry.get("secrets", ()) if variable not in allowed]
        if extra:
            problems.append(f"{name} got a key in {', '.join(extra)}")
    before = {entry["path"]: entry for entry in user_homes_before}
    for after in user_homes_after:
        earlier = before.get(after["path"])
        if earlier is None:
            problems.append(f"{after['path']} was not looked at before the run")
        elif not earlier["exists"] and after["exists"]:
            problems.append(f"{after['path']} was created during the run")
        elif earlier["exists"] and earlier != after:
            problems.append(f"{after['path']} changed during the run")
    shells = [entry for entry in processes if entry.get("agent_shell")]
    detail = "; ".join(problems) or (
        f"{harness_version}; ran with the run's own {', '.join(sorted(actual_homes))}; "
        + ", ".join(f"{entry['path']} {'unchanged' if entry['exists'] else 'never created'}" for entry in user_homes_after)
        + f"; no recorded process got a key but {', '.join(harness_keys) or 'none'}"
        + ("; the agent's shell gets none" if shells else "")
    )
    return Check("pins-and-isolation", not problems, detail)


# What the record must hold (AGENTS.md: installed version, identity,
# configuration, command, and complete result), as dotted paths into run.json.
# Only what a run can fail to find; the probe writes the rest itself.
RECORD_FIELDS = (
    "commit.sha",
    "harness_install.version",
    "harness_install.executable",
    "configs",
    "commands",
    "moments",
)


def _lookup(document: Mapping[str, Any], dotted: str) -> Any:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def record_complete(document: Mapping[str, Any], *, require_wheel: bool) -> Check:
    missing = [name for name in RECORD_FIELDS if _lookup(document, name) in (None, "", [], {})]
    nunchi = document.get("nunchi") or {}
    wheel = nunchi.get("wheel") or {}
    if require_wheel and not wheel.get("sha256"):
        missing.append("nunchi.wheel.sha256")
    if not require_wheel and not wheel.get("sha256") and not (document.get("commit") or {}).get("sha"):
        missing.append("nunchi: neither a wheel's sha256 nor the source commit")
    configs = document.get("configs") or ()
    if any(not entry.get("sha256") for entry in configs):
        missing.append("a config's sha256")
    detail = ("missing: " + ", ".join(missing)) if missing else f"{len(RECORD_FIELDS)} fields and {len(configs)} configs recorded"
    return Check("record-complete", not missing, detail)


def turns_bound_and_ended(
    invocations: Sequence[Mapping[str, Any]],
    host_receipts: Sequence[Mapping[str, Any]],
    committed: Sequence[Mapping[str, Any]],
    *,
    harness_failures: Sequence[str] = (),
) -> Check:
    """At least one turn ran, and each was bound to its wake and ended with the harness's own result.

    The participant-host receipt says how each turn ended: ``silent``, or
    ``unknown``, which is an action handed to the room when one was, and
    otherwise a turn that was cancelled, outlived the host's deadline or
    failed. It wins over what the probe recorded. ``harness_failures`` are
    the turns the harness itself ended in error, in its own words: the
    library has its outcome once the turn posts, so a call that fails after
    the post shows only there, and it fails the check too.
    """

    problems: list[str] = []
    handed = {item.get("request_id") for item in committed}
    host = {
        receipt.get("request_id"): receipt.get("body") or {}
        for receipt in host_receipts
        if (receipt.get("body") or {}).get("invoked", True)
    }
    for item in invocations:
        request_id = item["request_id"]
        label = f"turn {request_id} on {item.get('trigger')}"
        outcome = (host.get(request_id) or {}).get("outcome")
        result = (item.get("result") or {}).get("kind")
        if "error" in item:
            problems.append(f"{label} failed: {str(item['error']).strip() or 'without a name'}")
        elif result is None:
            problems.append(f"{label} never ended (the host recorded {outcome!r})")
        elif not item.get("bound"):
            problems.append(f"{label} ended as {result!r} without being bound to its wake")
        elif request_id not in host:
            problems.append(f"{label} ended as {result!r}, but the host recorded no outcome")
        elif outcome == "silent" and result != "silence":
            problems.append(f"{label} ended as {result!r}, but the host recorded a silence")
        elif outcome != "silent" and request_id not in handed:
            problems.append(
                f"{label} was cancelled, outlived the host's deadline or failed: the host recorded "
                f"{outcome!r} and nothing was handed to the room (the probe saw {result!r})"
            )
    seen = {item["request_id"] for item in invocations}
    for request_id in host:
        if request_id not in seen:
            problems.append(f"the host invoked the harness for {request_id} and the probe saw no turn")
    problems += harness_failures
    if not invocations:
        problems.append("no wake reached the harness, so the run did not show it reaching its model")
    if problems:
        return Check("turns-bound-and-ended", False, "; ".join(problems))
    kinds = Counter((item.get("result") or {}).get("kind") for item in invocations)
    ended = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
    return Check("turns-bound-and-ended", True, f"{len(invocations)} turn(s), each bound and ended with the harness's own result: {ended}")


def turns_on_others_messages(invocations: Sequence[Mapping[str, Any]], delivered: Sequence[str]) -> Check:
    """Every turn started on a message the probe posted as someone else, never on the agent's own.

    The probe posts every person's and bot's message itself, so any other
    trigger (the agent's own post coming back from the room, say) is a turn
    the agent should never have had.
    """

    others = set(delivered)
    stray = [f"turn {item['request_id']} on {item.get('trigger')}" for item in invocations if item.get("trigger") not in others]
    if stray:
        return Check("turns-on-others-messages", False, "a turn started on a message no one else posted: " + "; ".join(stray))
    return Check("turns-on-others-messages", True, f"{len(invocations)} turn(s), each on a message someone else posted")


def attention_judged(calls: Sequence[Mapping[str, Any]], invocations: Sequence[Mapping[str, Any]]) -> Check:
    """Attention returned a judgment; its failures, and the wakes their fallback caused, are listed.

    When attention fails, uncertainty wakes the agent (`docs/behavior.md`):
    such a turn's source is ``ERROR_FALLBACK``, and it is not attention's
    judgment. A run in which attention never judged did not run with
    attention, so it fails.
    """

    failed = [call for call in calls if call.get("error")]
    judged = len(calls) - len(failed)
    fallback = [item.get("trigger") for item in invocations if item.get("source") == "ERROR_FALLBACK"]
    parts = [f"{judged} of {len(calls)} attention call(s) returned a judgment"]
    if failed:
        reasons = list(dict.fromkeys(str(call["error"])[:200] for call in failed))
        parts.append(f"{len(failed)} failed: " + "; ".join(reasons))
    if fallback:
        parts.append(f"{len(fallback)} wake(s) came from the error fallback, not attention's judgment: " + ", ".join(map(str, fallback)))
    detail = "; ".join(parts)
    if not judged:
        detail = "attention never returned a judgment: " + detail
    return Check("attention-judged", judged > 0, detail)


def delivered(committed: Sequence[Mapping[str, Any]], room_effects: Sequence[Mapping[str, Any]], *, harness_posts: bool) -> list[bool]:
    """Whether each committed action reached the room.

    An action is delivered when its transport attested it ``sent``. A
    harness that posts its final answer itself (Hermes, ``harness_posts``)
    leaves its delivery ``unknown`` by design: there it is delivered when the
    room received exactly that text, each message in the room matching one
    answer at most.
    """

    received = [effect.get("text") for effect in room_effects if effect.get("kind") == "message"]
    result = []
    for item in committed:
        if item.get("delivery") == "sent":
            result.append(True)
        elif harness_posts and item.get("delivery") == "unknown" and item.get("text") in received:
            received.remove(item.get("text"))
            result.append(True)
        else:
            result.append(False)
    return result


def one_room_action_per_turn(committed: Sequence[Mapping[str, Any]], arrived: Sequence[bool]) -> Check:
    """No turn made more than one room action, and each one was delivered (``arrived``, from `delivered`)."""

    per_turn = Counter(item.get("request_id") for item in committed)
    problems = [f"turn {request_id} made {count} room actions" for request_id, count in per_turn.items() if count > 1]
    problems += [
        f"turn {item.get('request_id')}'s {item.get('kind')} was not delivered: it reads {item.get('delivery')!r}"
        + (f" ({item['detail']})" if item.get("detail") else "")
        for item, ok in zip(committed, arrived)
        if not ok
    ]
    detail = "; ".join(problems) or f"{len(committed)} committed action(s) in {len(per_turn)} turn(s), each delivered"
    return Check("one-room-action-per-turn", not problems, detail)


def no_leaks(
    committed: Sequence[Mapping[str, Any]],
    room_effects: Sequence[Mapping[str, Any]],
    ids: Iterable[str],
    *,
    known_gaps: Sequence[KnownGap] = (),
) -> Check:
    """The room got only what the library committed, and no committed post names Nunchi's machinery.

    The kit's leak count (`turn_conformance.leaks`), with the room's effects
    as what the harness showed and ``ids`` the turns' request ids and tool
    names. ``known_gaps`` are what the integration declares its harness shows
    by itself (`HERMES_KNOWN_GAPS`), scoped to `PROBE_SCENARIO`: a match is
    named as that gap, and fails the check too (a declared gap reads as a gap,
    never as a pass).
    """

    played = Played(dispatched=[dict(item) for item in committed], shown=[dict(item) for item in room_effects], ids=set(ids))
    found, declared = leaks(PROBE_SCENARIO, played, known_gaps)
    problems = [*found, *(f"declared gap, {gap}" for gap in declared)]
    detail = "; ".join(problems) or f"{len(room_effects)} effect(s) reached the room, each one committed; no committed post names Nunchi's machinery"
    return Check("no-leaks", not problems, detail)


FITS = "fits"
MISSES = "misses"
NOT_DELIVERED = "not delivered"


def moment_outcome(expect: str, *, reached: bool, graded_turns: int, delivered_posts: int) -> str:
    """How a moment went against what it expects: `FITS`, `MISSES`, or `NOT_DELIVERED`.

    ``reached`` is whether its graded message reached Nunchi: when it did not,
    the moment tested nothing. Only a delivered post counts. In a live run
    this is reported, never a failure: the model decides.
    """

    if not reached:
        return NOT_DELIVERED
    if expect == "post":
        return FITS if delivered_posts == 1 else MISSES
    if expect == "no-turn":
        return FITS if graded_turns == 0 else MISSES
    raise ValueError(f"unknown expectation {expect!r}")


def scripted_outcomes(moments: Sequence[Mapping[str, Any]], answer: str, *, room_tool_called: bool | None = None) -> Check:
    """With the model and attention scripted, every moment's outcome is known: check it.

    Scripted attention wakes only for the direct question, and the scripted
    agent posts ``answer`` once. So each moment fits, no other message starts
    a turn, the one post is ``answer``, and, for Codex and Claude Code, it
    went through a room tool (``room_tool_called``).
    """

    problems: list[str] = []
    for moment in moments:
        if moment.get("outcome") != FITS:
            problems.append(f"{moment.get('name')} reads {moment.get('outcome')!r}, not {FITS!r}")
        if moment.get("other_turns"):
            problems.append(f"{moment.get('name')} had {moment['other_turns']} turn(s) on other messages")
        for post in moment.get("posts", ()):
            if post.get("text") != answer:
                problems.append(f"{moment.get('name')} posted {str(post.get('text'))[:80]!r}, not the scripted answer")
    if not moments:
        problems.append("no moment was played")
    if room_tool_called is False:
        problems.append("no room tool was called")
    detail = "; ".join(problems) or f"{len(moments)} moment(s), each as scripted"
    return Check("scripted-outcomes", not problems, detail)


# -- the Discord room (step 9f, PR 3b; `discord_room.py`) -------------------------------------------
#
# With ``--room discord`` the room is the Discord stand-in, reached at
# Discord's names through the launcher, and Nunchi's own Discord processes
# run on it unmodified. Beside the checks above, a run in it holds these:
#
# 8. **discord-preflight**: each Discord process's preflight passed in that
#    process's own environment, and showed the launcher's certificate.
# 9. **discord-processes**: each Discord process got only its own keys, was
#    still running when the moments ended, and stopped when asked.
# 10. **discord-standin-clean**: the stand-in's verdict is clean: no unknown
#     route, op, host, request or payload shape.
# 11. **discord-clients-complete**: every bot identified, got READY (and a
#     member chunk, where its client asks for one), and made the calls its
#     column must make.
# 12. **discord-writes-reconciled**: each committed action that reads
#     ``sent`` matches exactly one write the bot made, with the same content
#     and target, and every write the bot made matches a committed action.
# 13. **discord-continuity**: the continuity gap the column's process
#     declares when it starts reached the participant; after op 7, every bot
#     resumed its session (no new IDENTIFY) and the message posted meanwhile
#     reached Nunchi. On the shared transport, also no continuity gap: not in
#     the transport's journal, not in the participant's observations. The
#     reference marks a stream gap on any disconnect; that is recorded, not
#     failed.
# 14. **discord-addressing**: a graded message reached the agent as it was
#     sent: the pings it carried (the direct question and the thumbs-up
#     request ping the agent) and, for the reply, the agent's own last
#     message as the one it replies to.
#
# With ``--scripted``, `discord_scripted_outcomes` checks each moment of the
# Discord room. A moment that expects ``report`` is reported, not graded,
# unless the column pins it: both columns pin the first message after a start
# and the remark in a thread under the room ``reached`` (the shared transport
# once dropped both, and the reference refused the thread's as another room).

REACHED = "reached"


def discord_moment_outcome(
    expect: str,
    *,
    reached: bool,
    graded_turns: int,
    actions: Sequence[Mapping[str, Any]],
    graded_event: str | None,
    thread: str | None = None,
) -> str:
    """How a moment of the Discord room went against what it expects.

    ``actions`` are the delivered committed actions of the moment's graded
    turns. ``post`` and ``no-turn`` read as `moment_outcome`. ``reply`` fits
    one reply to the graded message, ``reaction`` one reaction on it, and
    ``thread-reply`` one reply to it that landed in the thread named
    ``thread`` (the action's ``where``, read from the wire), not in the
    channel. ``report`` reads `NOT_DELIVERED` or `REACHED`: it is never graded.
    """

    if expect in ("post", "no-turn"):
        posts = sum(1 for action in actions if action.get("kind") in ("message", "reply"))
        return moment_outcome(expect, reached=reached, graded_turns=graded_turns, delivered_posts=posts)
    if expect == "report":
        return REACHED if reached else NOT_DELIVERED
    if not reached:
        return NOT_DELIVERED
    if expect in ("reply", "thread-reply"):
        wanted = "reply"
    elif expect == "reaction":
        wanted = "reaction"
    else:
        raise ValueError(f"unknown expectation {expect!r}")
    fits = len(actions) == 1 and actions[0].get("kind") == wanted and actions[0].get("target_event_id") == graded_event
    if fits and expect == "thread-reply":
        fits = bool(thread) and actions[0].get("where") == thread
    return FITS if fits else MISSES


def discord_scripted_outcomes(
    moments: Sequence[Mapping[str, Any]],
    script: Mapping[str, Mapping[str, Any]],
    *,
    pins: Mapping[str, str] | None = None,
    room_tool_called: bool | None = None,
) -> Check:
    """With the model and attention scripted, every graded moment of the Discord room is known: check it.

    ``script`` gives, for each expectation (``post``, ``reply``,
    ``reaction``, ``thread-reply``), the one delivered action the scripted agent makes: its
    ``kind`` and its ``text`` or ``reaction``. Each graded moment must fit,
    with exactly that action, and no other message may start a turn. A
    ``report`` moment is checked only where ``pins`` names it, against the
    outcome pinned (a known gap, kept visible until the library closes it).
    """

    problems: list[str] = []
    pins = dict(pins or {})
    for moment in moments:
        name, expect = moment.get("name"), moment.get("expect")
        if moment.get("other_turns"):
            problems.append(f"{name} had {moment['other_turns']} turn(s) on other messages")
        if expect == "report":
            if name in pins and moment.get("outcome") != pins[name]:
                problems.append(f"{name} reads {moment.get('outcome')!r}, not the pinned {pins[name]!r}: update the pin and its docs")
            continue
        if moment.get("outcome") != FITS:
            problems.append(f"{name} reads {moment.get('outcome')!r}, not {FITS!r}")
        wanted = script.get(expect)
        if wanted is None:
            continue
        for action in moment.get("actions", ()):
            if action.get("kind") != wanted["kind"]:
                problems.append(f"{name} made a {action.get('kind')}, not the scripted {wanted['kind']}")
            for field in ("text", "reaction"):
                if field in wanted and action.get(field) != wanted[field]:
                    problems.append(f"{name}'s {field} is {str(action.get(field))[:80]!r}, not the scripted one")
    if not moments:
        problems.append("no moment was played")
    if room_tool_called is False:
        problems.append("no room tool was called")
    detail = "; ".join(problems) or (
        f"{len(moments)} moment(s), each as scripted"
        + (f"; pinned: {', '.join(f'{name} {outcome}' for name, outcome in pins.items())}" if pins else "")
    )
    return Check("scripted-outcomes", not problems, detail)


def discord_preflight(processes: Sequence[Mapping[str, Any]], *, leaf_sha256: str | None) -> Check:
    """Each Discord process's preflight passed in its own environment and showed the launcher's certificate."""

    problems: list[str] = []
    for process in processes:
        name = process.get("name", "a Discord process")
        result = process.get("preflight") or {}
        if not result.get("ok"):
            problems.append(f"{name}'s preflight failed: {'; '.join(result.get('failures') or ['it did not run'])}")
        elif not result.get("nonce_checked"):
            problems.append(f"{name}'s preflight did not check the run's nonce")
        elif not leaf_sha256 or result.get("certificate_sha256") != leaf_sha256:
            problems.append(f"{name}'s preflight saw another certificate than the launcher's")
    if not processes:
        problems.append("no Discord process ran")
    detail = "; ".join(problems) or (
        f"{len(processes)} process(es): Discord's names led each to this run's stand-in, with the launcher's certificate, and no proxy"
    )
    return Check("discord-preflight", not problems, detail)


def discord_processes(processes: Sequence[Mapping[str, Any]]) -> Check:
    """Each Discord process got only its own keys, ran through the moments, and stopped when asked.

    Each entry names the variables holding a key (``secrets``) and those its
    column allows (``own_keys``): its bot token, and for the transport its
    output key, for the reference its attention and participant keys. Any
    other key, the harness's or the canary, fails.
    """

    problems: list[str] = []
    for process in processes:
        name = process.get("name", "a Discord process")
        extra = sorted(set(process.get("secrets", ())) - set(process.get("own_keys", ())))
        if extra:
            problems.append(f"{name} got a key that is not its own in {', '.join(extra)}")
        if not process.get("running_after_moments"):
            problems.append(f"{name} was not running when the moments ended (exit {process.get('exit')})")
        if process.get("stopped_by") not in ("SIGINT", "SIGTERM") or process.get("exit") is None:
            problems.append(f"{name} did not stop when asked ({process.get('stopped_by')}, exit {process.get('exit')})")
    if not processes:
        problems.append("no Discord process ran")
    detail = "; ".join(problems) or "; ".join(
        f"{process.get('name')}: keys {', '.join(process.get('secrets', ())) or 'none'}, stopped by {process.get('stopped_by')} "
        f"(exit {process.get('exit')})"
        for process in processes
    )
    return Check("discord-processes", not problems, detail)


def discord_standin_clean(verdict: Mapping[str, Any]) -> Check:
    """The stand-in's own verdict: no unknown route, op, host, request or payload shape (`fake_discord.wire.verdict`)."""

    unknown = list(verdict.get("unknown") or ())
    if verdict.get("clean") and not unknown:
        raised = len(verdict.get("raised") or ())
        return Check("discord-standin-clean", True, "no unknown record" + (f"; {raised} message time(s) raised to keep ids increasing" if raised else ""))
    shown = "; ".join(
        f"{item.get('what')}: " + json.dumps({key: value for key, value in item.items() if key not in ("kind", "at", "n", "what")}, sort_keys=True)[:200]
        for item in unknown[:10]
    )
    return Check("discord-standin-clean", False, f"{len(unknown)} unknown record(s): {shown or 'the verdict is not clean'}")


def discord_clients_complete(
    bots: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, Mapping[str, Any]],
    calls: Mapping[str, Iterable[str]],
) -> Check:
    """Every expected bot identified, got READY (and a member chunk where asked), and made its column's calls.

    ``bots`` is the verdict's per-bot count; ``expected`` gives, per bot,
    ``chunk`` (its client asks for members) and ``calls``, each
    ``METHOD /route`` it must have made with a 2xx answer; ``calls`` is what
    it made.
    """

    problems: list[str] = []
    for bot, want in expected.items():
        seen = bots.get(bot) or {}
        if not seen.get("identify"):
            problems.append(f"{bot} never identified")
        if not seen.get("ready"):
            problems.append(f"{bot} never got READY")
        if want.get("chunk") and not seen.get("chunks"):
            problems.append(f"{bot} never got a member chunk")
        missing = sorted(set(want.get("calls", ())) - set(calls.get(bot, ())))
        if missing:
            problems.append(f"{bot} never made {', '.join(missing)}")
    if not expected:
        problems.append("no bot was expected")
    detail = "; ".join(problems) or "; ".join(
        f"{bot}: identified, READY" + (", chunk" if want.get("chunk") else "") + f", {len(set(want.get('calls', ())))} call(s) made"
        for bot, want in expected.items()
    )
    return Check("discord-clients-complete", not problems, detail)


def _write_matches(action: Mapping[str, Any], write: Mapping[str, Any]) -> bool:
    native = str(action.get("target_event_id") or "").removeprefix("discord:message:")
    kind = action.get("kind")
    if kind in ("message", "reply"):
        return (
            write.get("kind") == "message"
            and write.get("content") == action.get("text")
            and (write.get("reply_to") or None) == (native if kind == "reply" else None)
        )
    if kind == "reaction":
        return (
            write.get("kind") == "reaction"
            and write.get("emoji") == action.get("reaction")
            and write.get("message_id") == native
            and write.get("removed", False) == (action.get("operation") == "remove")
        )
    return False


def discord_writes_reconciled(committed: Sequence[Mapping[str, Any]], writes: Sequence[Mapping[str, Any]]) -> Check:
    """Each committed action that reads ``sent`` is exactly one write the bot made, and each write is a committed action.

    ``writes`` are the agent's bot's 2xx writes on the stand-in's wire: a
    message with its content and reply target, or a reaction with its emoji
    and message. A committed action that does not read ``sent`` may match a
    write too (its acknowledgement was lost), but never needs one.
    """

    problems: list[str] = []
    left = [dict(write) for write in writes]
    for action in committed:
        matches = [write for write in left if _write_matches(action, write)]
        if action.get("delivery") == "sent":
            if len(matches) != 1:
                problems.append(f"turn {action.get('request_id')}'s {action.get('kind')} reads sent and matches {len(matches)} write(s)")
        if matches:
            left.remove(matches[0])
    problems += [f"the bot wrote a {write.get('kind')} that no committed action matches: {json.dumps(write, sort_keys=True)[:200]}" for write in left]
    detail = "; ".join(problems) or f"{len(committed)} committed action(s) and {len(writes)} write(s), each matched once"
    return Check("discord-writes-reconciled", not problems, detail)


def discord_continuity(start: Mapping[str, Any], reconnects: Sequence[Mapping[str, Any]], *, gaps_fail: bool) -> Check:
    """The gap a fresh process declares reached the participant, and a reconnect lost nothing.

    ``start`` is the continuity gap the column's process declares when it
    starts (``gap``, its delivery id, or None when the participant never
    saw one): it cannot know what happened before it connected, and says so.
    Each of ``reconnects`` is one bot's op 7: ``resumed`` (RESUME sent and
    RESUMED answered), ``identified_again``, ``message_reached`` (the
    message posted meanwhile), and the gaps marked after it, in the
    transport's journal (``transport_gaps``) and in the participant's
    observations (``participant_gaps``). ``gaps_fail`` is False for the
    reference, which marks a stream gap on any disconnect by design: those
    are recorded, not failed.
    """

    problems: list[str] = []
    recorded: list[str] = []
    if not start.get("gap"):
        problems.append(f"the participant never saw the gap its {start.get('process', 'process')} declares when it starts")
    for item in reconnects:
        bot = item.get("bot")
        if not item.get("resumed"):
            problems.append(f"{bot} did not resume its session after op 7")
        if item.get("identified_again"):
            problems.append(f"{bot} identified again after op 7, so its session's missed events were not replayed")
        if not item.get("message_reached"):
            problems.append(f"the message posted during {bot}'s reconnect never reached Nunchi")
        gaps = [*item.get("transport_gaps", ()), *item.get("participant_gaps", ())]
        if gaps and gaps_fail:
            problems.append(f"{bot}'s reconnect marked {len(gaps)} continuity gap(s): {', '.join(map(str, gaps))[:300]}")
        elif gaps:
            recorded.append(f"{bot} marked {len(gaps)} stream gap(s), recorded and not failed")
    if not reconnects:
        problems.append("no reconnect was played")
    detail = "; ".join(problems) or (
        f"the start gap reached the participant; {len(reconnects)} bot(s) resumed after op 7 and the message posted meanwhile "
        "reached Nunchi" + ("; " + "; ".join(recorded) if recorded else ", with no continuity gap")
    )
    return Check("discord-continuity", not problems, detail)


def discord_addressing(moments: Sequence[Mapping[str, Any]], *, agent: str, writes: Sequence[Mapping[str, Any]]) -> Check:
    """A graded message reached the agent as it was sent: whom it pinged, and the message it replied to.

    Each delivery of a graded moment (``post``, ``reply``, ``reaction``)
    records what the stand-in sent (``mentioned_actor_ids``, ``reply_to``)
    and ``received``, what the turn handed to the scripted agent or
    participant showed of that trigger (``mentioned_actor_ids``,
    ``reply_to_event_id``). The direct question and the thumbs-up request
    must ping ``agent`` (its actor id), and every ping sent must have
    arrived; the reply must have been sent as a reply to the agent's own
    last message on the wire (``writes``, the bot's 2xx writes) and arrive
    as one. The question in a thread (``thread-reply``) must ping the
    agent too, and arrive as a message in the thread it was sent in
    (``thread``, the thread's event id, against the trigger's
    ``thread_root_event_id``). A transport or reference that drops a ping, a
    reply reference or a thread fails here: the scripted agent answers a
    phrase either way, but a participant reading the room would not know it
    had been addressed.
    """

    problems: list[str] = []
    ours = [int(write["message_id"]) for write in writes if write.get("kind") == "message" and str(write.get("message_id", "")).isdigit()]
    graded: list[str] = []
    for moment in moments:
        expect, name = moment.get("expect"), moment.get("name")
        if expect not in ("post", "reply", "reaction", "thread-reply"):
            continue
        delivery = next((item for item in moment.get("deliveries", ()) if item.get("event_id") == moment.get("graded_event")), None)
        if delivery is None:
            problems.append(f"{name}: the graded message was never posted")
            continue
        received = delivery.get("received")
        if not received:
            problems.append(f"{name}: no turn showed how the message reached the agent")
            continue
        sent = list(delivery.get("mentioned_actor_ids") or ())
        seen = list(received.get("mentioned_actor_ids") or ())
        if expect in ("post", "reaction", "thread-reply") and agent not in sent:
            problems.append(f"{name}: the scene did not ping the agent")
        lost = [actor for actor in sent if actor not in seen]
        if lost:
            problems.append(f"{name}: sent pinging {', '.join(lost)}, but Nunchi saw mentioned_actor_ids={seen}")
        if expect == "reply":
            reply_to, posted = delivery.get("reply_to"), str(delivery.get("message_id", ""))
            before = [message for message in ours if posted.isdigit() and message < int(posted)]
            if not reply_to or not before or str(before[-1]) != str(reply_to):
                problems.append(f"{name}: it was not sent as a reply to the agent's own last message (reply_to {reply_to})")
            elif received.get("reply_to_event_id") != f"discord:message:{reply_to}":
                problems.append(f"{name}: sent as a reply to {reply_to}, but Nunchi saw reply_to_event_id={received.get('reply_to_event_id')}")
        if expect == "thread-reply":
            thread = delivery.get("thread")
            if not thread:
                problems.append(f"{name}: it was not sent in a thread")
            elif received.get("thread_root_event_id") != thread:
                problems.append(
                    f"{name}: sent in the thread {thread}, but Nunchi saw thread_root_event_id={received.get('thread_root_event_id')}"
                )
        graded.append(f"{name} {'replied to the agent' if expect == 'reply' else 'pinged the agent'}")
    if not graded and not problems:
        problems.append("no graded message was played")
    detail = "; ".join(problems) or f"each graded message reached the agent as sent: {', '.join(graded)}"
    return Check("discord-addressing", not problems, detail)
