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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from typing import Any, Callable, Mapping
import urllib.error

from nunchi import __version__
from nunchi.ack import AckPolicy, ReactionCapability
from nunchi.attention import (
    AttentionEngine,
    AttentionPolicy,
    OpenAICompatibleAttentionModel,
    ParticipantProfile,
)
from nunchi.observation import ObservationProvider, ParticipantBinding
from nunchi.receipts import ReceiptJournal

from .scene import SCENES, Moment, Scene, load_scenes, parse_offset, profile_sha256
from .score import cell, collective_silence, grade, visible_result


DEFAULT_MODELS = (
    "google/gemini-3.8-flash",
    "openai/gpt-6-luna",
    "qwen/qwen3.8-flash",
    "anthropic/claude-haiku-4.5",
    "z-ai/glm-5.3-flash",
    "deepseek/deepseek-v4.1-flash",
)
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_KEY_ENV = "NUNCHI_OPENROUTER"
DRY_RUN_MODEL = "offline/always-wake"
ACK_REACTION = "👂"


class OfflineModel:
    """Always wakes; checks the plumbing without a network."""

    name = "participant-attention"
    provider = "offline"

    def __init__(self, model_id: str = DRY_RUN_MODEL) -> None:
        self.model_id = model_id

    def judge(self, *, instructions, projection, timeout_seconds):
        return {
            "disposition": "WAKE",
            "reasons": ["offline dry run"],
            "evidence_event_ids": [projection["trigger_event_id"]],
            "legacy_verdict_confidences": {"PASS": 0, "ACK": 0, "ASK": 0, "SPEAK": 1},
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
        self.latency_ms: int | None = None

    def judge(self, **kwargs: Any) -> Mapping[str, Any]:
        started = time.monotonic()
        try:
            self.raw = self.inner.judge(**kwargs)
            return self.raw
        except BaseException as exc:
            self.error = _describe_error(exc)
            raise
        finally:
            self.latency_ms = int((time.monotonic() - started) * 1000)


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


def openai_compatible_factory(
    *, api_key: str, base_url: str, temperature: float | None
) -> ModelFactory:
    def build(model_id: str) -> Any:
        return OpenAICompatibleAttentionModel(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            provider="openrouter" if "openrouter.ai" in base_url else "openai-compatible",
            temperature=temperature,
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


def judge_moment(job: Job, factory: ModelFactory, *, timeout_seconds: float, now: datetime | None = None) -> dict[str, Any]:
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
    receipts = ReceiptJournal()
    provider = ObservationProvider(binding, receipts=receipts)
    eligible = None
    for raw in observed:
        at = None
        if "at" in raw:
            at = now - timedelta(seconds=parse_offset(raw["at"]) - end_offset)
        result = provider.observe(
            delivery_id=f"d-{raw['id']}",
            event=canonical_event(raw, at=at),
            actors=_event_actors(scene, raw),
        )
        if raw["id"] == moment.event:
            eligible = result.wake_eligible
    if not eligible:
        # The transport keeps the participant's own events from waking it.
        record.update(
            result="stay_quiet",
            grade=grade(moment, "stay_quiet"),
            detail="own event: the transport does not wake the participant",
        )
        return record

    request = provider.build_snapshot(moment.event)
    record["snapshot_event_ids"] = [event["id"] for event in request["events"]]
    model = RecordingModel(factory(job.model))
    engine = AttentionEngine(
        profile=ParticipantProfile(
            profile_id=f"eval-{participant}",
            participant_id=participant,
            actor_id=participant,
            instructions=profile_doc["instructions"],
            provenance="trusted:behavior-eval",
            sha256=profile_sha256(profile_doc),
        ),
        model=model,
        policy=AttentionPolicy(timeout_seconds=timeout_seconds),
        receipts=receipts,
        ack_policy=AckPolicy(reaction=ACK_REACTION),
        reaction_capability_provider=ReactionCapability(
            supported=True,
            authenticated=True,
            operations=("add", "remove"),
            reactions=(ACK_REACTION,),
            permissions_revision="behavior-eval",
        ),
    )
    decision = engine.judge(request)
    outcome = visible_result(decision)
    evidence = set(decision.get("evidence_event_ids", []))
    record.update(
        result=outcome,
        grade=grade(moment, outcome),
        provider_error=decision.get("status") == "error",
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
                "legacy_verdict_confidences",
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
    findings = []
    for scene in scenes:
        if "not-all-quiet" not in scene.together:
            continue
        for (scene_id, moment, model, run), results in sorted(by_key.items()):
            if scene_id == scene.id and len(results) == len(scene.participants) and collective_silence(results):
                findings.append({"scene": scene_id, "moment": moment, "model": model, "run": run})
    return findings


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, cwd=Path(__file__).parent
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


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
        f"- Scenes: {len(scenes)}; calls: {meta['calls']}; provider errors: {meta['provider_errors']}",
        f"- Command: `{meta['command']}`",
        "",
        "Today's V2 makes one attention decision per moment, so a woken agent's own",
        "move is not simulated yet; those runs count as *agent decides*. See",
        "`evals/behavior/score.py` for the grades.",
        "",
        "## Per model",
        "",
        "| Model | Moments | Fits | Miss | Unlisted | Agent decides | Step 1 over-suppress | Step 1 over-wake | Nunchi-sent mhm | Cited facts | Errors | Median ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model in models:
        mine = [record for record in records if record["model"] == model and record["result"] != "unsupported"]
        visible = Counter(record["grade"]["visible"] for record in mine)
        step1 = Counter(record["grade"]["step1"] for record in mine)
        cited = [flag for record in mine for flag in record.get("cited", [])]
        latencies = [record["latency_ms"] for record in mine if record.get("latency_ms") is not None]
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                model,
                len(mine),
                visible["fits"],
                visible["miss"],
                visible["unlisted"],
                visible["agent-decides"],
                step1["over-suppress"],
                step1["over-wake"],
                sum(1 for record in mine if record["result"] == "mhm"),
                f"{sum(cited)}/{len(cited)}" if cited else "-",
                sum(1 for record in mine if record["provider_error"]),
                int(statistics.median(latencies)) if latencies else "-",
            )
        )
    if together:
        lines += ["", "## Collective silence", ""]
        for item in together:
            lines.append(f"- {item['scene']} moment {item['moment'] + 1}, `{item['model']}` run {item['run'] + 1}: every participant stayed quiet")
    lines += [
        "",
        "## Moments",
        "",
        "Each cell has one letter per run: Q quiet, M mhm (sent by Nunchi), W woken,",
        "E provider error (woken), and a dash where today's V2 has no route. A",
        "trailing `!` marks a clear miss in some run; `?` marks an unlisted move.",
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
    parser.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=8)
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
    if args.runs < 1 or args.workers < 1:
        parser.error("--runs and --workers must be positive")

    if args.dry_run:
        models = [DRY_RUN_MODEL]
        factory: ModelFactory = OfflineModel
    else:
        models = [item.strip() for item in args.models.split(",") if item.strip()]
        api_key = os.environ.get(args.key_env)
        if not api_key:
            parser.error(f"set {args.key_env} to the provider key, or use --dry-run")
        factory = openai_compatible_factory(
            api_key=api_key, base_url=args.base_url, temperature=args.temperature
        )

    jobs = plan(scenes, models, args.runs)
    started = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(lambda job: judge_moment(job, factory, timeout_seconds=args.timeout), jobs))
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
        "runs": args.runs,
        "temperature": None if args.dry_run else args.temperature,
        "timeout_seconds": args.timeout,
        "base_url": "offline" if args.dry_run else args.base_url,
        "key_env": None if args.dry_run else args.key_env,
        "scenes": [scene.id for scene in scenes],
        "calls": sum(1 for record in records if record["result"] != "unsupported" and "decision" in record),
        "provider_errors": sum(1 for record in records if record["provider_error"]),
        "collective_silence": together,
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = summarize(scenes, models, records, together, meta)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
