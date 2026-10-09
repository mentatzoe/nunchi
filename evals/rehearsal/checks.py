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
