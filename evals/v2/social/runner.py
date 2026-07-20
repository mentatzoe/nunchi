"""Run repeated live-provider trials over participant-shaped V2 scenes.

This is an evidence runner, never a runtime oracle.  It records the raw
validated model judgment, the effective one-way routing result, outcome
distributions, and flicker.  Only explicit safety constraints such as "do not
confidently suppress this exact direct request" are machine-checked; nuanced
conversation quality remains a separate post-hoc review.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Callable

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from nunchi.classifiers import attention_v2_prompt_digest, classify_attention_v2
from nunchi.core import classifier_projection, evaluate_v2
from nunchi.observation import (
    check_actor_reference_integrity,
    check_id_uniqueness,
    check_timestamp_order,
    check_trigger_membership,
    validate_attention_request,
)
from nunchi.policy import OperatorPolicy, PolicyLoadError, load_operator_policy


DETERMINISTIC_TIME = "1970-01-01T00:00:00Z"
MIN_TRIALS = 5
MAX_TRIALS = 50


class SocialEvaluationError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def load_catalog() -> dict[str, Any]:
    resource = resources.files("evals.v2.social").joinpath("catalog.json")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SocialEvaluationError("social evaluation catalog is unreadable") from exc
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "defaults",
        "cases",
    }:
        raise SocialEvaluationError("social evaluation catalog root is invalid")
    if document["schema_version"] != 1 or not isinstance(document["defaults"], dict):
        raise SocialEvaluationError("social evaluation catalog version is invalid")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SocialEvaluationError("social evaluation catalog has no cases")
    expected_fields = {
        "case_id",
        "title",
        "tags",
        "events",
        "trigger_event_id",
        "minimum_classifier_non_suppress_fraction",
        "minimum_effective_non_suppress_fraction",
        "maximum_error_fraction",
        "review_question",
    }
    observed_ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict) or set(case) not in (
            expected_fields,
            expected_fields | {"coverage"},
        ):
            raise SocialEvaluationError("social evaluation case shape is invalid")
        if (
            not isinstance(case["case_id"], str)
            or not case["case_id"]
            or not isinstance(case["title"], str)
            or not case["title"]
            or not isinstance(case["review_question"], str)
            or not case["review_question"]
            or not isinstance(case["tags"], list)
            or not case["tags"]
            or any(not isinstance(tag, str) or not tag for tag in case["tags"])
            or len(set(case["tags"])) != len(case["tags"])
            or not isinstance(case["events"], list)
            or not case["events"]
            or not isinstance(case["trigger_event_id"], str)
            or not case["trigger_event_id"]
        ):
            raise SocialEvaluationError("social evaluation case values are invalid")
        classifier_minimum = case["minimum_classifier_non_suppress_fraction"]
        effective_minimum = case["minimum_effective_non_suppress_fraction"]
        maximum_error = case["maximum_error_fraction"]
        if any(
            minimum is not None
            and (
                isinstance(minimum, bool)
                or not isinstance(minimum, (int, float))
                or not 0 <= float(minimum) <= 1
            )
            for minimum in (classifier_minimum, effective_minimum)
        ) or (
            isinstance(maximum_error, bool)
            or not isinstance(maximum_error, (int, float))
            or not 0 <= float(maximum_error) <= 1
        ):
            raise SocialEvaluationError("social evaluation thresholds are invalid")
        observed_ids.append(case["case_id"])
    if len(set(observed_ids)) != len(observed_ids):
        raise SocialEvaluationError("social evaluation case IDs are not unique")
    return copy.deepcopy(document)


def _materialize_request(
    defaults: dict[str, Any],
    case: dict[str, Any],
    policy: OperatorPolicy,
) -> dict[str, Any]:
    try:
        self_fact = copy.deepcopy(defaults["self"])
        room = copy.deepcopy(defaults["room"])
        actors = copy.deepcopy(defaults["actors"])
        coverage = copy.deepcopy(defaults["coverage"])
        if "coverage" in case:
            coverage.update(copy.deepcopy(case["coverage"]))
        self_fact["participant_id"] = policy.attention.participant_id
        room["continuity_scope_id"] = policy.recoverability.continuity_scope_id
        request = {
            "schema_version": 2,
            "request_id": f"social-eval:{case['case_id']}",
            "self": self_fact,
            "room": room,
            "actors": actors,
            "events": copy.deepcopy(case["events"]),
            "trigger_event_id": case["trigger_event_id"],
            "coverage": coverage,
        }
    except (KeyError, TypeError) as exc:
        raise SocialEvaluationError("social evaluation defaults are invalid") from exc
    errors = validate_attention_request(request)
    errors.extend(check_id_uniqueness(request.get("events") or []))
    errors.extend(check_timestamp_order(request.get("events") or []))
    errors.extend(check_trigger_membership(request))
    errors.extend(check_actor_reference_integrity(request))
    if errors:
        raise SocialEvaluationError(
            f"social evaluation case {case['case_id']} is not a valid V2 request"
        )
    return request


def _repository_root() -> Path:
    return _REPOSITORY_ROOT


def _git_value(root: Path, *arguments: str, allow_empty: bool = False) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    if completed.returncode != 0 or (not value and not allow_empty):
        return None
    return value


def _candidate_provenance(root: Path) -> dict[str, Any]:
    status = _git_value(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
        allow_empty=True,
    )
    return {
        "commit": _git_value(root, "rev-parse", "HEAD") or "unavailable",
        "worktree_clean": status == "" if status is not None else None,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


def _classifier_provenance(policy: OperatorPolicy) -> dict[str, Any]:
    config = policy.classifier
    endpoint_digest = "sha256:" + hashlib.sha256(
        config.endpoint.encode("utf-8")
    ).hexdigest()
    non_secret = {
        "provider": config.provider,
        "model": config.model,
        "endpoint_digest": endpoint_digest,
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
        "requested_temperature": 0,
    }
    return {
        **non_secret,
        "non_secret_configuration_digest": _digest(non_secret),
        "credential_configured": config.api_key is not None,
        "prompt_digest": attention_v2_prompt_digest(),
        "policy_provenance": policy.provenance,
    }


def _distribution(labels: list[str], trials: int) -> dict[str, Any]:
    counts = Counter(labels)
    transitions = sum(
        left != right for left, right in zip(labels, labels[1:])
    )
    dominant = max(counts.values()) / len(labels) if labels else 0.0
    return {
        "counts": dict(sorted(counts.items())),
        "distinct": sorted(counts),
        "flickered": len(counts) > 1,
        "consecutive_transitions": transitions,
        "dominant_fraction": dominant,
        "observed_trials": len(labels),
        "requested_trials": trials,
    }


def _run_case(
    case: dict[str, Any],
    request: dict[str, Any],
    policy: OperatorPolicy,
    *,
    trials: int,
    classifier_transport: Callable[[dict[str, Any], Any], Any],
    deterministic_time: bool,
) -> dict[str, Any]:
    trial_records: list[dict[str, Any]] = []
    classifier_labels: list[str] = []
    effective_labels: list[str] = []
    error_count = 0
    for index in range(1, trials + 1):
        raw_box: dict[str, Any] = {}

        def capture(projection, config):
            raw = classifier_transport(projection, config)
            raw_box["judgment"] = copy.deepcopy(raw)
            return raw

        receipts: list[dict[str, Any]] = []
        started = time.perf_counter()
        decision = evaluate_v2(
            request,
            policy=policy.attention,
            recoverability=policy.recoverability,
            classifier_config=policy.classifier,
            receipt_sink=receipts.append,
            classifier_transport=capture,
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        if deterministic_time:
            duration_ms = 0.0
        record: dict[str, Any] = {
            "trial": index,
            "duration_ms": duration_ms,
            "decision": copy.deepcopy(decision),
        }
        if receipts:
            record["attention_receipt"] = copy.deepcopy(receipts[-1])
        if "judgment" in raw_box:
            record["raw_judgment"] = copy.deepcopy(raw_box["judgment"])
        if decision.get("status") == "ok":
            classifier_labels.append(decision["classifier_disposition"])
            effective_labels.append(decision["effective_disposition"])
        else:
            error_count += 1
        trial_records.append(record)

    valid_count = len(effective_labels)
    classifier_non_suppress = sum(
        label != "SUPPRESS" for label in classifier_labels
    )
    effective_non_suppress = sum(label != "SUPPRESS" for label in effective_labels)
    classifier_non_suppress_fraction = (
        classifier_non_suppress / valid_count if valid_count else 0.0
    )
    effective_non_suppress_fraction = (
        effective_non_suppress / valid_count if valid_count else 0.0
    )
    error_fraction = error_count / trials
    failures: list[str] = []
    if error_fraction > float(case["maximum_error_fraction"]):
        failures.append("provider-or-output-error-rate")
    classifier_minimum = case["minimum_classifier_non_suppress_fraction"]
    if classifier_minimum is not None and (
        not valid_count
        or classifier_non_suppress_fraction < float(classifier_minimum)
    ):
        failures.append("classifier-false-suppression-rate")
    effective_minimum = case["minimum_effective_non_suppress_fraction"]
    if effective_minimum is not None and (
        not valid_count
        or effective_non_suppress_fraction < float(effective_minimum)
    ):
        failures.append("effective-false-suppression-rate")
    return {
        "case_id": case["case_id"],
        "title": case["title"],
        "tags": copy.deepcopy(case["tags"]),
        "projection_digest": _digest(classifier_projection(request)),
        "constraints": {
            "minimum_classifier_non_suppress_fraction": classifier_minimum,
            "minimum_effective_non_suppress_fraction": effective_minimum,
            "maximum_error_fraction": case["maximum_error_fraction"],
        },
        "observed": {
            "classifier_non_suppress_fraction": classifier_non_suppress_fraction,
            "effective_non_suppress_fraction": effective_non_suppress_fraction,
            "error_fraction": error_fraction,
            "classifier_distribution": _distribution(classifier_labels, trials),
            "effective_distribution": _distribution(effective_labels, trials),
        },
        "constraint_status": "passed" if not failures else "failed",
        "constraint_failures": failures,
        "review_question": case["review_question"],
        "post_hoc_review_required": True,
        "trials": trial_records,
    }


def run(
    policy: OperatorPolicy,
    *,
    trials: int = 7,
    selected_ids: tuple[str, ...] = (),
    classifier_transport: Callable[[dict[str, Any], Any], Any] = classify_attention_v2,
    deterministic_time: bool = False,
) -> dict[str, Any]:
    if not isinstance(policy, OperatorPolicy):
        raise SocialEvaluationError("operator policy is invalid")
    if (
        isinstance(trials, bool)
        or not isinstance(trials, int)
        or not MIN_TRIALS <= trials <= MAX_TRIALS
    ):
        raise SocialEvaluationError(
            f"trials must be between {MIN_TRIALS} and {MAX_TRIALS}"
        )
    if not callable(classifier_transport):
        raise SocialEvaluationError("classifier transport is invalid")
    if not policy.attention.preattention_enabled:
        raise SocialEvaluationError("live social evaluation requires preattention enabled")
    catalog = load_catalog()
    known_ids = {case["case_id"] for case in catalog["cases"]}
    selected = set(selected_ids)
    if selected - known_ids:
        raise SocialEvaluationError("unknown social evaluation case ID")
    cases = [
        case
        for case in catalog["cases"]
        if not selected or case["case_id"] in selected
    ]
    results = [
        _run_case(
            case,
            _materialize_request(catalog["defaults"], case, policy),
            policy,
            trials=trials,
            classifier_transport=classifier_transport,
            deterministic_time=deterministic_time,
        )
        for case in cases
    ]
    failures = [
        result["case_id"]
        for result in results
        if result["constraint_status"] == "failed"
    ]
    measurement_only = [
        result["case_id"]
        for result in results
        if result["constraints"]["minimum_classifier_non_suppress_fraction"] is None
        and result["constraints"]["minimum_effective_non_suppress_fraction"] is None
    ]
    root = _repository_root()
    return {
        "schema_version": 1,
        "evaluation": "nunchi-v2-live-social-judgment",
        "recorded_at": (
            DETERMINISTIC_TIME
            if deterministic_time
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "candidate": _candidate_provenance(root),
        "classifier": _classifier_provenance(policy),
        "trials_per_case": trials,
        "cases": results,
        "summary": {
            "selected_cases": len(results),
            "constraint_failures": failures,
            "measurement_only_cases": measurement_only,
            "machine_constraints_passed": not failures,
            "post_hoc_review_required": True,
            "product_completion_claimed": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.v2.social.runner",
        description=(
            "Run repeated live-provider V2 social judgments and report distributions; "
            "this never becomes a runtime send filter."
        ),
    )
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--trials", type=int, default=7)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--deterministic-time", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        catalog = load_catalog()
        if arguments.list:
            for case in catalog["cases"]:
                constraint = case["minimum_classifier_non_suppress_fraction"]
                grade = "measurement" if constraint is None else f"non-suppress>={constraint:g}"
                print(f"{case['case_id']}\t{case['title']}\t{grade}")
            return 0
        if arguments.policy is None:
            raise SocialEvaluationError("--policy is required for a live run")
        policy = load_operator_policy(arguments.policy)
        record = run(
            policy,
            trials=arguments.trials,
            selected_ids=tuple(arguments.case),
            deterministic_time=arguments.deterministic_time,
        )
    except (SocialEvaluationError, PolicyLoadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(serialized)
    else:
        try:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            with arguments.output.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
        except FileExistsError:
            print("social evaluation output already exists", file=sys.stderr)
            return 2
        except OSError:
            print("could not create social evaluation output", file=sys.stderr)
            return 2
    return 1 if record["summary"]["constraint_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
