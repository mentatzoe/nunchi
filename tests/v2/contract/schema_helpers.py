"""Shared dual-validator harness for the V2 contract corpus (slice 010).

One deterministic conformance corpus (``evals/v2/contract/*/cases.jsonl``)
exercises two validators:

* the portable JSON Schema Draft 2020-12 oracle — dev/test-only
  ``jsonschema==4.26.0`` — over the machine-readable contracts in
  ``schemas/v2/``; and
* the explicit Python-stdlib runtime-validation adapter in this module,
  which mirrors every schema constraint and additionally owns the
  semantic/relational rules that Draft 2020-12 cannot express.

FR-012 expressiveness partition (the class vocabulary is spec-owned; case
membership and per-class counts live only in ordinary paths):

* ``schema-expressible`` — identical expected results from both validators.
* Document-shaped relational classes — ``id-uniqueness``,
  ``timestamp-order``, ``advice-citation``, ``trigger-membership``,
  ``actor-reference-integrity`` — are runtime-adapter-only; the oracle
  validates each document in isolation and expects it valid, because each
  document is schema-valid on its own.
* Behavioral/sequence classes — ``binding-expiry``, ``receipt-sequence`` —
  are runtime-adapter-only and oracle-class-skipped, because there is no
  single document for the oracle to validate.

Two skip regimes are named and counted separately so one regime's expected
skips cannot mask the other's missing cases:

* ``baseline-oracle-absence`` — under the repository baseline
  (``python3 -m unittest``) the oracle is absent; every oracle-side check
  for the five oracle-visible classes is skipped with an explicit count.
  The stdlib adapter still runs the full corpus and must pass.
* ``oracle-class-skip`` — under the pinned dual-validator command the
  oracle explicitly skips the two behavioral classes, by class, with an
  explicit count.

The sole complete dual-validator run is the exact offline command:

    uv run --offline --with 'jsonschema==4.26.0' \
        python -m unittest discover -s tests/v2/contract -p 'test_*.py'

``--offline`` MUST fail rather than access the network; a missing oracle
therefore fails loudly at the ``uv`` layer under the pinned command, while
the baseline run records counted oracle-absence skips instead. A
``jsonschema`` import with any version other than the pin is treated as an
absent oracle (named in the skip message) so an unpinned oracle can never
masquerade as the complete run.

Non-finite sentinel decoding: strict JSON forbids non-finite literals, so
red cases encode them as the reserved strings ``"NaN"``, ``"Infinity"``,
and ``"-Infinity"`` anywhere inside a case payload. The corpus loader
decodes them exactly once, so both validators receive identical decoded
cases. That sentinel vocabulary is reserved across every corpus payload
string position and must not be used as literal content.

SC-002 preservation: for every valid single-document case the harness
asserts that parsed semantic field values survive the load pipeline —
strings compare as exact strings, numbers by exact decimal token (``1``
and ``1.0`` are distinct), and event-array order is preserved. Raw-byte
serialization (key order, whitespace, unicode escapes) is out of scope.

Evidence writer: ``python -m tests.v2.contract.schema_helpers
--write-evidence`` re-runs the corpus through both validators and writes
the aggregate JSONL evidence records (mandatory ``scene_id``, stable
``case_id``, validator identity, expected result, observed result). The
writer requires the pinned oracle so evidence always reflects the complete
dual run.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS_DIR = REPO_ROOT / "schemas" / "v2"
EVALS_DIR = REPO_ROOT / "evals" / "v2" / "contract"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "v2" / "contract"

ORACLE_PIN = "4.26.0"
ORACLE_VALIDATOR_ID = f"jsonschema=={ORACLE_PIN} Draft202012Validator"
ADAPTER_VALIDATOR_ID = "stdlib-runtime-adapter tests/v2/contract/schema_helpers.py"

SCHEMA_FILES = {
    "attention-request": "attention-request.schema.json",
    "attention-decision": "attention-decision.schema.json",
    "participant-wake": "participant-wake.schema.json",
    "context-continuation": "context-continuation.schema.json",
    "attention-receipt": "attention-receipt.schema.json",
}

INTERFACE_VERSIONS = {
    "attention-request": ("I-010A", "AttentionRequestV2", 1),
    "attention-decision": ("I-010B", "AttentionDecisionV2", 1),
    "participant-wake": ("I-010C", "ParticipantWakeV2", 1),
    "context-continuation": ("I-010D", "ContextContinuationV2", 1),
    "attention-receipt": ("I-010E", "AttentionReceiptV2", 1),
}

# FR-012 partition classes. The vocabulary is owned by the slice spec;
# membership and counts are owned here and in evals/v2/contract/.
SCHEMA_EXPRESSIBLE = "schema-expressible"
ORACLE_VALID_CLASSES = (
    "id-uniqueness",
    "timestamp-order",
    "advice-citation",
    "trigger-membership",
    "actor-reference-integrity",
)
ORACLE_SKIP_CLASSES = ("binding-expiry", "receipt-sequence")
ALL_CLASSES = (SCHEMA_EXPRESSIBLE,) + ORACLE_VALID_CLASSES + ORACLE_SKIP_CLASSES

# The two named skip regimes (kept distinct; see module docstring).
BASELINE_ORACLE_ABSENCE = "baseline-oracle-absence"
ORACLE_CLASS_SKIP = "oracle-class-skip"

CORPUS_NAMES = ("attention-request", "attention-decision", "downstream")

NON_FINITE_SENTINELS = {
    "NaN": float("nan"),
    "Infinity": float("inf"),
    "-Infinity": float("-inf"),
}

DISPOSITIONS = ("SUPPRESS", "WAKE", "DEFER")
VERDICT_KEYS = ("PASS", "ACK", "ASK", "SPEAK")
WAKE_SOURCES = ("WAKE", "DEFER", "ERROR_FALLBACK", "PREATTENTION_BYPASS")
ROUTING_VALVES = ("none", "classifier-defer", "margin-defer", "policy-defer")
OVERRIDE_CAUSES = (
    "none",
    "margin",
    "suppression-disabled",
    "recoverability-unproven",
)
MARGIN_STATUSES = ("active", "retired")
RECEIPT_STAGES = ("observation", "attention", "participant-host", "transport")
RECEIPT_WRITERS = (
    "observation-provider",
    "attention-engine",
    "participant-host",
    "transport",
)
# Staged-receipt writer map: each stage is appended only by its named owner.
RECEIPT_WRITER_MAP = dict(zip(RECEIPT_STAGES, RECEIPT_WRITERS))


# ---------------------------------------------------------------------------
# Oracle availability and construction
# ---------------------------------------------------------------------------


def oracle_status() -> tuple[bool, str]:
    """Return ``(available, detail)`` for the pinned Draft 2020-12 oracle.

    Only ``jsonschema==4.26.0`` counts as available: any other version is
    treated as absent (with the found version named) so the pinned command
    remains the sole complete dual-validator run.
    """
    try:
        import importlib.metadata as importlib_metadata

        import jsonschema  # noqa: F401
    except Exception:
        return False, "jsonschema is not importable"
    version = importlib_metadata.version("jsonschema")
    if version != ORACLE_PIN:
        return (
            False,
            f"jsonschema {version} found but the oracle is pinned to "
            f"{ORACLE_PIN}; treating the oracle as absent",
        )
    return True, f"jsonschema {version}"


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / SCHEMA_FILES[name]
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_oracle_validators() -> dict[str, Any]:
    """Build one Draft 2020-12 validator per schema over a shared registry."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = {name: load_schema(name) for name in SCHEMA_FILES}
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return {
        name: Draft202012Validator(schema, registry=registry)
        for name, schema in schemas.items()
    }


# ---------------------------------------------------------------------------
# Non-finite sentinel decoding (single decode point; both validators see
# identical decoded cases)
# ---------------------------------------------------------------------------


def decode_non_finite(value: Any) -> Any:
    if isinstance(value, str):
        return NON_FINITE_SENTINELS.get(value, value)
    if isinstance(value, list):
        return [decode_non_finite(item) for item in value]
    if isinstance(value, dict):
        return {key: decode_non_finite(item) for key, item in value.items()}
    return value


# ---------------------------------------------------------------------------
# SC-002 semantic-field preservation
# ---------------------------------------------------------------------------


class NumberToken(str):
    """The exact decimal token of a JSON number (``1`` != ``1.0``)."""


def token_parse(text: str) -> Any:
    """Parse JSON keeping every number as its exact decimal token."""
    return json.loads(
        text,
        parse_int=NumberToken,
        parse_float=NumberToken,
        parse_constant=NumberToken,
    )


def decode_non_finite_tokens(value: Any) -> Any:
    """Sentinel decode over a token tree: reserved strings become tokens."""
    if isinstance(value, NumberToken):
        return value
    if isinstance(value, str):
        if value in NON_FINITE_SENTINELS:
            return NumberToken(value)
        return value
    if isinstance(value, list):
        return [decode_non_finite_tokens(item) for item in value]
    if isinstance(value, dict):
        return {key: decode_non_finite_tokens(item) for key, item in value.items()}
    return value


def semantic_equal(left: Any, right: Any) -> bool:
    """SC-002 comparator over token trees.

    Strings compare as exact strings, numbers by exact decimal token,
    arrays in order, objects by key set. A number token never equals a
    plain string even when the characters match.
    """
    left_is_token = isinstance(left, NumberToken)
    right_is_token = isinstance(right, NumberToken)
    if left_is_token or right_is_token:
        return left_is_token and right_is_token and str(left) == str(right)
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, list) or isinstance(right, list):
        if not (isinstance(left, list) and isinstance(right, list)):
            return False
        if len(left) != len(right):
            return False
        return all(semantic_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) or isinstance(right, dict):
        if not (isinstance(left, dict) and isinstance(right, dict)):
            return False
        if set(left) != set(right):
            return False
        return all(semantic_equal(left[key], right[key]) for key in left)
    return left == right


def preservation_failure(raw_payload_tokens: Any, loaded_payload: Any) -> str | None:
    """Return a failure description if the load pipeline broke SC-002.

    ``raw_payload_tokens`` is the token-preserving parse of the payload as
    it appears on the corpus line (sentinels decoded to tokens);
    ``loaded_payload`` is the decoded object handed to both validators.
    The loaded side is re-serialized (``allow_nan=True`` keeps decoded
    sentinels representable) and both sides are compared as token trees,
    which also forces corpus numbers to be written in their canonical
    shortest decimal token.
    """
    round_trip = token_parse(json.dumps(loaded_payload, allow_nan=True))
    if not semantic_equal(raw_payload_tokens, round_trip):
        return (
            "semantic fields were not preserved through the corpus load "
            "pipeline (SC-002): exact string/number-token equality or "
            "event-array order was lost"
        )
    return None


# ---------------------------------------------------------------------------
# Corpus loading with loud per-class count assertions
# ---------------------------------------------------------------------------

_PAYLOAD_KEYS = ("document", "documents", "fetch", "stream")


class CorpusError(AssertionError):
    """A corpus integrity failure (malformed envelope or count mismatch)."""


class CorpusCase:
    def __init__(self, corpus: str, line_number: int, raw_line: str, data: dict[str, Any]):
        self.corpus = corpus
        self.line_number = line_number
        self.raw_line = raw_line
        self.case_id = data["case_id"]
        self.scene_id = data["scene_id"]
        self.title = data["title"]
        self.partition = data["partition"]
        self.expected = data["expected"]
        self.schema = data.get("schema")
        self.document = data.get("document")
        self.documents = data.get("documents")
        self.fetch = data.get("fetch")
        self.stream = data.get("stream")

    @property
    def payload_kind(self) -> str:
        for key in _PAYLOAD_KEYS:
            if getattr(self, key.replace("-", "_")) is not None:
                return key
        raise CorpusError(f"{self.corpus}:{self.case_id} has no payload")

    def oracle_documents(self) -> list[tuple[str, Any]]:
        """The (schema, document) pairs the oracle validates in isolation."""
        if self.document is not None:
            return [(self.schema, self.document)]
        if self.documents is not None:
            return [(entry["schema"], entry["document"]) for entry in self.documents]
        return []


def _validate_envelope(corpus: str, line_number: int, data: Any) -> None:
    if not isinstance(data, dict):
        raise CorpusError(f"{corpus} line {line_number}: envelope must be an object")
    for field in ("case_id", "scene_id", "title", "partition", "expected"):
        value = data.get(field)
        if not isinstance(value, str) or not value:
            raise CorpusError(
                f"{corpus} line {line_number}: envelope field {field!r} must be a "
                "non-empty string"
            )
    if data["partition"] not in ALL_CLASSES:
        raise CorpusError(
            f"{corpus} line {line_number}: unknown partition class "
            f"{data['partition']!r}; the closed FR-012 set is {ALL_CLASSES}"
        )
    if data["expected"] not in ("valid", "invalid"):
        raise CorpusError(
            f"{corpus} line {line_number}: expected must be 'valid' or 'invalid'"
        )
    present = [key for key in _PAYLOAD_KEYS if key in data]
    if len(present) != 1:
        raise CorpusError(
            f"{corpus} line {line_number}: exactly one payload of {_PAYLOAD_KEYS} "
            f"is required, found {present or 'none'}"
        )
    if "document" in data and data.get("schema") not in SCHEMA_FILES:
        raise CorpusError(
            f"{corpus} line {line_number}: single-document cases require a "
            f"'schema' naming one of {sorted(SCHEMA_FILES)}"
        )
    if "documents" in data:
        entries = data["documents"]
        if not isinstance(entries, list) or len(entries) < 2:
            raise CorpusError(
                f"{corpus} line {line_number}: 'documents' must list at least two entries"
            )
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or entry.get("schema") not in SCHEMA_FILES
                or "document" not in entry
            ):
                raise CorpusError(
                    f"{corpus} line {line_number}: each documents[] entry needs "
                    "'schema' and 'document'"
                )


def load_expected_counts(corpus: str) -> dict[str, dict[str, int]]:
    path = EVALS_DIR / corpus / "expected-counts.json"
    with path.open(encoding="utf-8") as handle:
        counts = json.load(handle)
    for klass in ALL_CLASSES:
        entry = counts.get(klass)
        if (
            not isinstance(entry, dict)
            or set(entry) != {"valid", "invalid"}
            or not all(isinstance(entry[key], int) for key in entry)
        ):
            raise CorpusError(
                f"{corpus}/expected-counts.json must pin {{'valid', 'invalid'}} "
                f"integers for every class; {klass!r} is missing or malformed"
            )
    extra = set(counts) - set(ALL_CLASSES)
    if extra:
        raise CorpusError(
            f"{corpus}/expected-counts.json names unknown classes: {sorted(extra)}"
        )
    return counts


def assert_corpus_inventory(evals_dir: Path = EVALS_DIR) -> None:
    """Assert the closed on-disk corpus inventory (CHK067).

    The set of subdirectories of ``evals/v2/contract/`` must equal exactly
    the registered ``CORPUS_NAMES``, and each registered directory must hold
    ``cases.jsonl`` and its authoritative ``expected-counts.json``. A wholly
    missing or unregistered corpus directory therefore fails loudly here —
    on every corpus load — rather than passing vacuously under per-directory
    count assertions that iterate only over directories found.
    """
    if not evals_dir.is_dir():
        raise CorpusError(f"corpus root {evals_dir} is not a directory")
    observed = sorted(entry.name for entry in evals_dir.iterdir() if entry.is_dir())
    registered = sorted(CORPUS_NAMES)
    if observed != registered:
        missing = sorted(set(registered) - set(observed))
        unregistered = sorted(set(observed) - set(registered))
        raise CorpusError(
            "the on-disk corpus inventory must equal exactly the registered "
            f"corpus set {registered}; missing: {missing or 'none'}, "
            f"unregistered: {unregistered or 'none'}"
        )
    for name in registered:
        for filename in ("cases.jsonl", "expected-counts.json"):
            if not (evals_dir / name / filename).is_file():
                raise CorpusError(
                    f"registered corpus {name!r} is missing its required "
                    f"{filename}; each corpus directory must hold cases.jsonl "
                    "and its authoritative expected-counts.json"
                )


def load_corpus(corpus: str) -> list[CorpusCase]:
    """Load one corpus directory, decode sentinels once, and assert counts.

    The full on-disk inventory is asserted closed first (CHK067), then the
    per-class counts in ``expected-counts.json`` are authoritative and
    must be updated in the same change as any corpus edit; a mismatch fails
    loudly here, naming the corpus, class, and both counts, so neither
    partition can silently shrink.
    """
    assert_corpus_inventory()
    path = EVALS_DIR / corpus / "cases.jsonl"
    expected_counts = load_expected_counts(corpus)
    cases: list[CorpusCase] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            data = json.loads(raw_line)
            _validate_envelope(corpus, line_number, data)
            for key in _PAYLOAD_KEYS:
                if key in data:
                    data[key] = decode_non_finite(data[key])
            case = CorpusCase(corpus, line_number, raw_line, data)
            if case.case_id in seen_ids:
                raise CorpusError(f"{corpus}: duplicate case_id {case.case_id!r}")
            seen_ids.add(case.case_id)
            cases.append(case)

    observed: dict[str, dict[str, int]] = {
        klass: {"valid": 0, "invalid": 0} for klass in ALL_CLASSES
    }
    for case in cases:
        observed[case.partition][case.expected] += 1
    for klass in ALL_CLASSES:
        for verdict in ("valid", "invalid"):
            want = expected_counts[klass][verdict]
            got = observed[klass][verdict]
            if want != got:
                raise CorpusError(
                    f"corpus {corpus!r} class {klass!r} expected {want} "
                    f"{verdict} case(s) per its authoritative "
                    "expected-counts.json but the corpus contains "
                    f"{got}; update the counts file in the same change as "
                    "any corpus edit"
                )
    return cases


def class_skip_count(cases: list[CorpusCase]) -> int:
    """Cases the oracle skips by explicit class in every regime."""
    return sum(1 for case in cases if case.partition in ORACLE_SKIP_CLASSES)


def oracle_visible_count(cases: list[CorpusCase]) -> int:
    """Cases with an oracle-side check under the pinned command."""
    return len(cases) - class_skip_count(cases)


# ---------------------------------------------------------------------------
# Stdlib runtime-validation adapter: schema-constraint mirrors
#
# Each function mirrors the corresponding schemas/v2/*.schema.json exactly,
# keyword for keyword, so schema-expressible cases yield identical results
# from both validators. Comparison semantics intentionally follow JSON
# Schema (for example ``5.0`` satisfies ``"type": "integer"``).
# ---------------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value) and value.is_integer()


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and len(value) >= 1


class _Errors(list):
    def add(self, path: str, message: str) -> None:
        self.append(f"{path}: {message}")


def _check_closed_object(
    errors: _Errors, path: str, value: Any, required: tuple[str, ...], allowed: tuple[str, ...]
) -> bool:
    if not isinstance(value, dict):
        errors.add(path, "must be an object")
        return False
    for name in required:
        if name not in value:
            errors.add(path, f"missing required property {name!r}")
    for name in value:
        if name not in allowed:
            errors.add(path, f"unexpected property {name!r} (closed contract)")
    return True


def _check_nes(errors: _Errors, path: str, value: Any) -> None:
    if not _non_empty_string(value):
        errors.add(path, "must be a non-empty string")


def _check_enum(errors: _Errors, path: str, value: Any, allowed: tuple[str, ...]) -> None:
    if value not in allowed or not isinstance(value, str):
        errors.add(path, f"must be one of {allowed}")


def _check_actor(errors: _Errors, path: str, value: Any) -> None:
    if not _check_closed_object(errors, path, value, (), ("display_name", "kind")):
        return
    if "display_name" in value and not isinstance(value["display_name"], str):
        errors.add(f"{path}.display_name", "must be a string")
    if "kind" in value:
        _check_enum(errors, f"{path}.kind", value["kind"], ("human", "bot", "unknown"))


def _check_actor_map(errors: _Errors, path: str, value: Any) -> None:
    if not isinstance(value, dict):
        errors.add(path, "must be an object mapping actor ID to actor")
        return
    for actor_id, actor in value.items():
        if not _non_empty_string(actor_id):
            errors.add(f"{path}[{actor_id!r}]", "actor ID key must be a non-empty string")
        _check_actor(errors, f"{path}[{actor_id!r}]", actor)


def _check_message_event(errors: _Errors, path: str, event: dict[str, Any]) -> None:
    allowed = (
        "id", "type", "author_id", "timestamp", "text",
        "reply_to_event_id", "thread_root_event_id", "mentioned_actor_ids", "mentions_room",
    )
    required = ("id", "type", "author_id", "text", "mentioned_actor_ids", "mentions_room")
    if not _check_closed_object(errors, path, event, required, allowed):
        return
    _check_nes(errors, f"{path}.id", event.get("id"))
    _check_nes(errors, f"{path}.author_id", event.get("author_id"))
    if "timestamp" in event:
        _check_nes(errors, f"{path}.timestamp", event["timestamp"])
    if "text" in event and not isinstance(event["text"], str):
        errors.add(f"{path}.text", "must be a string")
    if "reply_to_event_id" in event:
        _check_nes(errors, f"{path}.reply_to_event_id", event["reply_to_event_id"])
    if "thread_root_event_id" in event:
        _check_nes(errors, f"{path}.thread_root_event_id", event["thread_root_event_id"])
    if "mentioned_actor_ids" in event:
        mentioned = event["mentioned_actor_ids"]
        if not isinstance(mentioned, list):
            errors.add(f"{path}.mentioned_actor_ids", "must be an array of actor IDs")
        else:
            for index, actor_id in enumerate(mentioned):
                _check_nes(errors, f"{path}.mentioned_actor_ids[{index}]", actor_id)
    if "mentions_room" in event and not isinstance(event["mentions_room"], bool):
        errors.add(f"{path}.mentions_room", "must be a boolean")


def _check_reaction_event(errors: _Errors, path: str, event: dict[str, Any]) -> None:
    allowed = ("id", "type", "author_id", "timestamp", "target_event_id", "reaction", "operation")
    required = ("id", "type", "author_id", "target_event_id", "reaction", "operation")
    if not _check_closed_object(errors, path, event, required, allowed):
        return
    _check_nes(errors, f"{path}.id", event.get("id"))
    _check_nes(errors, f"{path}.author_id", event.get("author_id"))
    if "timestamp" in event:
        _check_nes(errors, f"{path}.timestamp", event["timestamp"])
    _check_nes(errors, f"{path}.target_event_id", event.get("target_event_id"))
    _check_nes(errors, f"{path}.reaction", event.get("reaction"))
    if "operation" in event:
        _check_enum(errors, f"{path}.operation", event["operation"], ("add", "remove"))


def _check_membership_event(errors: _Errors, path: str, event: dict[str, Any]) -> None:
    allowed = ("id", "type", "timestamp", "scope", "subject_actor_id", "caused_by_actor_id", "change")
    required = ("id", "type", "scope", "subject_actor_id", "change")
    if not _check_closed_object(errors, path, event, required, allowed):
        return
    _check_nes(errors, f"{path}.id", event.get("id"))
    if "timestamp" in event:
        _check_nes(errors, f"{path}.timestamp", event["timestamp"])
    scope = event.get("scope")
    if "scope" in event and _check_closed_object(
        errors, f"{path}.scope", scope, ("kind", "id"), ("kind", "id")
    ):
        if "kind" in scope:
            _check_enum(
                errors, f"{path}.scope.kind", scope["kind"], ("room", "thread", "space", "unknown")
            )
        if "id" in scope:
            _check_nes(errors, f"{path}.scope.id", scope["id"])
    _check_nes(errors, f"{path}.subject_actor_id", event.get("subject_actor_id"))
    if "caused_by_actor_id" in event:
        _check_nes(errors, f"{path}.caused_by_actor_id", event["caused_by_actor_id"])
    if "change" in event:
        _check_enum(errors, f"{path}.change", event["change"], ("join", "leave"))


def _check_self(errors: _Errors, path: str, value: Any) -> None:
    """Shared ``self`` validator (FR-002), reused by every materializing
    schema (AttentionRequestV2 and ParticipantWakeV2 carry the identical
    field shape verbatim; rejection R9 requires one shared mirror)."""
    if not _check_closed_object(
        errors, path, value,
        ("participant_id", "actor_id"),
        ("participant_id", "actor_id", "names", "role", "description"),
    ):
        return
    if "participant_id" in value:
        _check_nes(errors, f"{path}.participant_id", value["participant_id"])
    if "actor_id" in value:
        _check_nes(errors, f"{path}.actor_id", value["actor_id"])
    if "names" in value:
        names = value["names"]
        if not isinstance(names, list):
            errors.add(f"{path}.names", "must be an array")
        else:
            for index, name in enumerate(names):
                if not isinstance(name, str):
                    errors.add(f"{path}.names[{index}]", "must be a string")
    if "role" in value and not isinstance(value["role"], str):
        errors.add(f"{path}.role", "must be a string")
    if "description" in value and not isinstance(value["description"], str):
        errors.add(f"{path}.description", "must be a string")


def _check_room(errors: _Errors, path: str, value: Any) -> None:
    """Shared ``room`` validator, reused by every materializing schema
    (rejection R9)."""
    if not _check_closed_object(
        errors, path, value,
        ("platform", "id", "continuity_scope_id"),
        ("platform", "id", "continuity_scope_id", "name", "kind"),
    ):
        return
    if "platform" in value:
        _check_nes(errors, f"{path}.platform", value["platform"])
    if "id" in value:
        _check_nes(errors, f"{path}.id", value["id"])
    if "continuity_scope_id" in value:
        _check_nes(errors, f"{path}.continuity_scope_id", value["continuity_scope_id"])
    if "name" in value and not isinstance(value["name"], str):
        errors.add(f"{path}.name", "must be a string")
    if "kind" in value:
        _check_enum(errors, f"{path}.kind", value["kind"], ("group", "direct", "unknown"))


def _check_event(errors: _Errors, path: str, event: Any) -> None:
    if not isinstance(event, dict):
        errors.add(path, "must be an object")
        return
    event_type = event.get("type")
    if event_type == "message":
        _check_message_event(errors, path, event)
    elif event_type == "reaction":
        _check_reaction_event(errors, path, event)
    elif event_type == "membership":
        _check_membership_event(errors, path, event)
    else:
        errors.add(f"{path}.type", "must be one of ('message', 'reaction', 'membership')")


def _check_coverage(errors: _Errors, path: str, value: Any) -> None:
    required = (
        "has_more_before", "has_more_after", "has_gaps",
        "truncated_by", "continuity", "has_restart_gap",
    )
    allowed = required + ("max_events", "max_bytes", "max_age_seconds", "event_visibility")
    if not _check_closed_object(errors, path, value, required, allowed):
        return
    for name in ("max_events", "max_bytes", "max_age_seconds"):
        if name in value:
            amount = value[name]
            if not _is_integer(amount):
                errors.add(f"{path}.{name}", "must be an integer")
            elif amount < 1:
                errors.add(f"{path}.{name}", "must be a positive budget (>= 1)")
    for name in ("has_more_before", "has_more_after", "has_restart_gap"):
        if name in value and value[name] is not None and not isinstance(value[name], bool):
            errors.add(f"{path}.{name}", "must be a boolean or null")
    if "has_gaps" in value and not isinstance(value["has_gaps"], bool):
        errors.add(f"{path}.has_gaps", "must be a boolean")
    if "truncated_by" in value:
        truncated_by = value["truncated_by"]
        if not isinstance(truncated_by, list):
            errors.add(f"{path}.truncated_by", "must be an array")
        else:
            for index, item in enumerate(truncated_by):
                _check_enum(errors, f"{path}.truncated_by[{index}]", item, ("events", "bytes", "age"))
    if "continuity" in value:
        _check_enum(
            errors, f"{path}.continuity", value["continuity"],
            ("restart-safe", "session-only", "unknown"),
        )
    if "event_visibility" in value:
        visibility = value["event_visibility"]
        if not isinstance(visibility, dict):
            errors.add(f"{path}.event_visibility", "must be an object mapping event type to visibility")
        else:
            for key, item in visibility.items():
                _check_enum(
                    errors, f"{path}.event_visibility[{key!r}]", item,
                    ("history-and-live", "live-only", "unavailable", "unknown"),
                )


def _check_continuation_binding(errors: _Errors, path: str, value: Any) -> None:
    fields = ("participant_id", "room_id", "continuity_scope_id", "trigger_event_id")
    if not _check_closed_object(errors, path, value, fields, fields):
        return
    for name in fields:
        if name in value:
            _check_nes(errors, f"{path}.{name}", value[name])


def _check_continuation(errors: _Errors, path: str, value: Any) -> None:
    required = (
        "handle_id", "bound_to", "can_fetch_before", "can_fetch_after",
        "can_fetch_around_event", "max_events_per_fetch", "max_bytes_per_fetch",
    )
    allowed = required + ("expires_at",)
    if not _check_closed_object(errors, path, value, required, allowed):
        return
    if "handle_id" in value:
        _check_nes(errors, f"{path}.handle_id", value["handle_id"])
    if "bound_to" in value:
        _check_continuation_binding(errors, f"{path}.bound_to", value["bound_to"])
    for name in ("can_fetch_before", "can_fetch_after", "can_fetch_around_event"):
        if name in value and not isinstance(value[name], bool):
            errors.add(f"{path}.{name}", "must be a boolean")
    for name in ("max_events_per_fetch", "max_bytes_per_fetch"):
        if name in value:
            amount = value[name]
            if not _is_integer(amount):
                errors.add(f"{path}.{name}", "must be an integer")
            elif amount < 1:
                errors.add(f"{path}.{name}", "must be a positive budget (>= 1)")
    if "expires_at" in value:
        _check_nes(errors, f"{path}.expires_at", value["expires_at"])


def validate_attention_request(doc: Any) -> list[str]:
    """Mirror of schemas/v2/attention-request.schema.json (I-010A)."""
    errors = _Errors()
    required = (
        "schema_version", "request_id", "self", "room",
        "actors", "events", "trigger_event_id", "coverage",
    )
    allowed = required + ("continuation",)
    if not _check_closed_object(errors, "request", doc, required, allowed):
        return list(errors)
    if doc.get("schema_version") != 2:
        errors.add("schema_version", "must be the number 2")
    _check_nes(errors, "request_id", doc.get("request_id"))

    if "self" in doc:
        _check_self(errors, "self", doc.get("self"))
    if "room" in doc:
        _check_room(errors, "room", doc.get("room"))

    if "actors" in doc:
        _check_actor_map(errors, "actors", doc["actors"])

    events = doc.get("events")
    if "events" in doc:
        if not isinstance(events, list):
            errors.add("events", "must be an array of typed events")
        elif len(events) < 1:
            errors.add("events", "must contain at least one event")
        else:
            for index, event in enumerate(events):
                _check_event(errors, f"events[{index}]", event)

    if "trigger_event_id" in doc:
        _check_nes(errors, "trigger_event_id", doc["trigger_event_id"])
    if "coverage" in doc:
        _check_coverage(errors, "coverage", doc["coverage"])
    if "continuation" in doc:
        _check_continuation(errors, "continuation", doc["continuation"])
    return list(errors)


def _check_confidence(errors: _Errors, path: str, value: Any) -> None:
    # Mirrors the schema's finite [0, 1] rule: the schema pairs plain
    # bounds with a contradictory-bounds not-clause that only a value
    # incomparable to every bound (NaN) can satisfy.
    if not _is_number(value):
        errors.add(path, "must be a number")
        return
    if not math.isfinite(value) or not (0.0 <= float(value) <= 1.0):
        errors.add(path, "must be a finite number within [0, 1]")


def _check_attention_advice(errors: _Errors, path: str, value: Any) -> None:
    if not _check_closed_object(
        errors, path, value, ("note", "evidence_event_ids"), ("note", "evidence_event_ids")
    ):
        return
    if "note" in value:
        _check_nes(errors, f"{path}.note", value["note"])
    if "evidence_event_ids" in value:
        cited = value["evidence_event_ids"]
        if not isinstance(cited, list) or len(cited) < 1:
            errors.add(f"{path}.evidence_event_ids", "must be a non-empty array of event IDs")
        else:
            for index, event_id in enumerate(cited):
                _check_nes(errors, f"{path}.evidence_event_ids[{index}]", event_id)


def _check_attention_advice_list(errors: _Errors, path: str, value: Any) -> None:
    if not isinstance(value, list):
        errors.add(path, "must be an array of attention-advice objects")
        return
    for index, advice in enumerate(value):
        _check_attention_advice(errors, f"{path}[{index}]", advice)


def _check_classifier_audit(errors: _Errors, path: str, value: Any) -> None:
    if not _check_closed_object(errors, path, value, ("name",), ("name", "provider", "model")):
        return
    if "name" in value:
        _check_nes(errors, f"{path}.name", value["name"])
    if "provider" in value:
        _check_nes(errors, f"{path}.provider", value["provider"])
    if "model" in value:
        _check_nes(errors, f"{path}.model", value["model"])


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# The closed ok-transition matrix (FR-006) with each pair's allowed valves
# and whether the pair may carry advice (FR-013: classifier WAKE only).
# WAKE->WAKE and SUPPRESS->SUPPRESS carry valve "none" (no widening valve
# applied); valve/override-cause/margin cross-field legality is enforced
# separately by the routing-audit rules (FR-005).
_OK_TRANSITIONS = {
    ("WAKE", "WAKE"): {"valves": ("none",), "advice": True},
    ("DEFER", "DEFER"): {"valves": ("classifier-defer",), "advice": False},
    ("SUPPRESS", "DEFER"): {
        "valves": ("margin-defer", "policy-defer"),
        "advice": False,
    },
    ("SUPPRESS", "SUPPRESS"): {"valves": ("none",), "advice": False},
}


def validate_attention_decision(doc: Any) -> list[str]:
    """Mirror of schemas/v2/attention-decision.schema.json (I-010B)."""
    errors = _Errors()
    if not isinstance(doc, dict):
        return ["decision: must be an object"]
    status = doc.get("status")
    if status == "ok":
        return _validate_decision_ok(doc)
    if status == "bypass":
        return _validate_decision_bypass(doc)
    if status == "error":
        return _validate_decision_error(doc)
    errors.add("status", "must be exactly one of 'ok', 'bypass', 'error'")
    return list(errors)


def _check_routing_audit(errors: _Errors, routing: Any) -> str | None:
    """The closed FR-005 routing audit with its per-combination rules.

    A margin counts as applied exactly on valve ``margin-defer``: the
    effective margin (finite, in (0, 1]) is then required and forbidden on
    every other valve, the override cause must be ``margin``, and the
    margin status must be ``active`` (a retired margin cannot apply). The
    trusted margin source may appear only on that margin-applied decision.
    Valves ``none``/``classifier-defer`` pair with override cause ``none``;
    valve ``policy-defer`` pairs with ``suppression-disabled`` or
    ``recoverability-unproven``.
    """
    if not _check_closed_object(
        errors,
        "routing_audit",
        routing,
        ("valve", "override_cause", "margin_status"),
        ("valve", "override_cause", "margin_status", "effective_margin", "margin_source"),
    ):
        return None
    valve = routing.get("valve")
    if "valve" in routing:
        _check_enum(errors, "routing_audit.valve", valve, ROUTING_VALVES)
    if "override_cause" in routing:
        _check_enum(errors, "routing_audit.override_cause", routing["override_cause"], OVERRIDE_CAUSES)
    if "margin_status" in routing:
        _check_enum(errors, "routing_audit.margin_status", routing["margin_status"], MARGIN_STATUSES)
    if "effective_margin" in routing:
        margin = routing["effective_margin"]
        if not _is_number(margin):
            errors.add("routing_audit.effective_margin", "must be a number")
        elif not math.isfinite(margin) or not (0.0 < float(margin) <= 1.0):
            errors.add(
                "routing_audit.effective_margin", "must be a finite number within (0, 1]"
            )
    if "margin_source" in routing:
        _check_nes(errors, "routing_audit.margin_source", routing["margin_source"])

    if valve == "margin-defer":
        if routing.get("override_cause") in OVERRIDE_CAUSES and routing["override_cause"] != "margin":
            errors.add(
                "routing_audit.override_cause",
                "valve margin-defer requires override cause 'margin'",
            )
        if routing.get("margin_status") in MARGIN_STATUSES and routing["margin_status"] != "active":
            errors.add(
                "routing_audit.margin_status",
                "valve margin-defer requires margin status 'active'; a retired "
                "margin cannot apply",
            )
        if "effective_margin" not in routing:
            errors.add(
                "routing_audit.effective_margin",
                "required: a margin applied exactly when the valve is "
                "margin-defer, and the applied margin must record its "
                "effective width",
            )
    elif valve in ("none", "classifier-defer"):
        if routing.get("override_cause") in OVERRIDE_CAUSES and routing["override_cause"] != "none":
            errors.add(
                "routing_audit.override_cause",
                f"valve {valve!r} requires override cause 'none'",
            )
    elif valve == "policy-defer":
        if routing.get("override_cause") in OVERRIDE_CAUSES and routing["override_cause"] not in (
            "suppression-disabled",
            "recoverability-unproven",
        ):
            errors.add(
                "routing_audit.override_cause",
                "valve policy-defer requires override cause "
                "'suppression-disabled' or 'recoverability-unproven'",
            )
    if valve != "margin-defer":
        if "effective_margin" in routing:
            errors.add(
                "routing_audit.effective_margin",
                "forbidden: no margin applied unless the valve is margin-defer",
            )
        if "margin_source" in routing:
            errors.add(
                "routing_audit.margin_source",
                "forbidden: the trusted margin source may appear only on a "
                "margin-applied (valve margin-defer) decision",
            )
    return valve if valve in ROUTING_VALVES else None


def _validate_decision_ok(doc: dict[str, Any]) -> list[str]:
    errors = _Errors()
    required = (
        "status",
        "request_id",
        "classifier_disposition",
        "effective_disposition",
        "routing_audit",
        "reasons",
        "evidence_event_ids",
        "classifier",
    )
    allowed = required + ("legacy_verdict_confidences", "attention_advice")
    if not _check_closed_object(errors, "decision", doc, required, allowed):
        return list(errors)
    _check_nes(errors, "request_id", doc.get("request_id"))

    classifier = doc.get("classifier_disposition")
    effective = doc.get("effective_disposition")
    if "classifier_disposition" in doc:
        _check_enum(errors, "classifier_disposition", classifier, DISPOSITIONS)
    if "effective_disposition" in doc:
        _check_enum(errors, "effective_disposition", effective, DISPOSITIONS)

    routing = doc.get("routing_audit")
    valve = None
    if "routing_audit" in doc:
        valve = _check_routing_audit(errors, routing)

    if "reasons" in doc:
        reasons = doc["reasons"]
        if not isinstance(reasons, list):
            errors.add("reasons", "must be an array of audit strings")
        else:
            for index, reason in enumerate(reasons):
                _check_nes(errors, f"reasons[{index}]", reason)

    if "evidence_event_ids" in doc:
        cited = doc["evidence_event_ids"]
        if not isinstance(cited, list):
            errors.add("evidence_event_ids", "must be an array of event IDs")
        else:
            for index, event_id in enumerate(cited):
                _check_nes(errors, f"evidence_event_ids[{index}]", event_id)

    if "classifier" in doc:
        _check_classifier_audit(errors, "classifier", doc["classifier"])

    confidences = doc.get("legacy_verdict_confidences")
    if "legacy_verdict_confidences" in doc and _check_closed_object(
        errors, "legacy_verdict_confidences", confidences, VERDICT_KEYS, VERDICT_KEYS
    ):
        for key in VERDICT_KEYS:
            if key in confidences:
                _check_confidence(errors, f"legacy_verdict_confidences.{key}", confidences[key])

    if "attention_advice" in doc:
        _check_attention_advice_list(errors, "attention_advice", doc["attention_advice"])

    # FR-007 conditional requirement: the legacy vector is required exactly
    # when the classifier disposition is SUPPRESS while the routing audit
    # reports the margin active; it stays optional (and permitted) on WAKE,
    # DEFER, and a margin-retired SUPPRESS.
    if (
        classifier == "SUPPRESS"
        and isinstance(routing, dict)
        and routing.get("margin_status") == "active"
        and "legacy_verdict_confidences" not in doc
    ):
        errors.add(
            "legacy_verdict_confidences",
            "required: a margin-active candidate SUPPRESS must carry the "
            "legacy verdict confidence vector (FR-007)",
        )

    # Closed ok-transition matrix: only four classifier/effective pairs are
    # successful; every other pairing must take the operational-error path.
    if classifier in DISPOSITIONS and effective in DISPOSITIONS:
        rule = _OK_TRANSITIONS.get((classifier, effective))
        if rule is None:
            errors.add(
                "effective_disposition",
                f"ok transition {classifier}->{effective} is not one of the four "
                "permitted pairs; report it on the error branch instead",
            )
        else:
            if valve is not None and valve not in rule["valves"]:
                errors.add(
                    "routing_audit.valve",
                    f"transition {classifier}->{effective} requires the applied "
                    f"valve in {rule['valves']}",
                )
            if not rule["advice"] and "attention_advice" in doc:
                errors.add(
                    "attention_advice",
                    "only allowed when the classifier disposition is WAKE (FR-013)",
                )
    return list(errors)


def _validate_decision_bypass(doc: dict[str, Any]) -> list[str]:
    errors = _Errors()
    fields = ("status", "request_id", "cause")
    if not _check_closed_object(errors, "decision", doc, fields, fields):
        return list(errors)
    _check_nes(errors, "request_id", doc.get("request_id"))
    if "cause" in doc and doc["cause"] != "preattention-disabled":
        errors.add("cause", "must be exactly 'preattention-disabled'")
    return list(errors)


def _validate_decision_error(doc: dict[str, Any]) -> list[str]:
    errors = _Errors()
    required = ("status", "error")
    allowed = required + ("request_id", "classifier")
    if not _check_closed_object(errors, "decision", doc, required, allowed):
        return list(errors)
    if "request_id" in doc:
        _check_nes(errors, "request_id", doc["request_id"])
    error = doc.get("error")
    if "error" in doc and _check_closed_object(
        errors, "error", error, ("code", "detail"), ("code", "detail")
    ):
        if "code" in error:
            _check_nes(errors, "error.code", error["code"])
        if "detail" in error and not isinstance(error["detail"], str):
            errors.add("error.detail", "must be a string")
    if "classifier" in doc:
        _check_classifier_audit(errors, "classifier", doc["classifier"])
    return list(errors)


def validate_participant_wake(doc: Any) -> list[str]:
    """Mirror of schemas/v2/participant-wake.schema.json (I-010C)."""
    errors = _Errors()
    required = ("request_id", "self", "room", "actors", "events", "trigger_event_id", "coverage", "attention")
    allowed = required + ("continuation",)
    if not _check_closed_object(errors, "wake", doc, required, allowed):
        return list(errors)
    _check_nes(errors, "request_id", doc.get("request_id"))

    if "self" in doc:
        _check_self(errors, "self", doc.get("self"))
    if "room" in doc:
        _check_room(errors, "room", doc.get("room"))
    if "actors" in doc:
        _check_actor_map(errors, "actors", doc["actors"])
    events = doc.get("events")
    if "events" in doc:
        if not isinstance(events, list):
            errors.add("events", "must be an array of typed events")
        elif len(events) < 1:
            errors.add("events", "must contain at least one event")
        else:
            for index, event in enumerate(events):
                _check_event(errors, f"events[{index}]", event)
    if "trigger_event_id" in doc:
        _check_nes(errors, "trigger_event_id", doc["trigger_event_id"])
    if "coverage" in doc:
        _check_coverage(errors, "coverage", doc["coverage"])
    if "continuation" in doc:
        _check_continuation(errors, "continuation", doc["continuation"])

    attention = doc.get("attention")
    source = None
    if "attention" in doc and _check_closed_object(
        errors, "attention", attention, ("source",), ("source", "advice", "evidence_event_ids")
    ):
        source = attention.get("source")
        if "source" in attention:
            _check_enum(errors, "attention.source", source, WAKE_SOURCES)
        if "advice" in attention:
            _check_attention_advice_list(errors, "attention.advice", attention["advice"])
        if "evidence_event_ids" in attention:
            cited = attention["evidence_event_ids"]
            if not isinstance(cited, list):
                errors.add("attention.evidence_event_ids", "must be an array of event IDs")
            else:
                for index, event_id in enumerate(cited):
                    _check_nes(errors, f"attention.evidence_event_ids[{index}]", event_id)
        if source != "WAKE" and ("advice" in attention or "evidence_event_ids" in attention):
            errors.add(
                "attention.advice",
                "only allowed when source is 'WAKE' (FR-013): DEFER, "
                "ERROR_FALLBACK, and PREATTENTION_BYPASS wakes are advice-free",
            )
    return list(errors)


def validate_context_continuation(doc: Any) -> list[str]:
    """Mirror of schemas/v2/context-continuation.schema.json (I-010D)."""
    errors = _Errors()
    if not isinstance(doc, dict):
        return ["continuation: must be an object"]
    if "actors" in doc or "coverage" in doc:
        # ContextPage: identity-bearing, carries actors/events/coverage.
        required = (
            "request_id", "handle_id", "room_id", "continuity_scope_id",
            "direction", "anchor_event_id", "actors", "events", "coverage",
        )
        allowed = required + ("next_cursor",)
        if not _check_closed_object(errors, "continuation", doc, required, allowed):
            return list(errors)
        if "request_id" in doc:
            _check_nes(errors, "request_id", doc["request_id"])
        if "handle_id" in doc:
            _check_nes(errors, "handle_id", doc["handle_id"])
        if "room_id" in doc:
            _check_nes(errors, "room_id", doc["room_id"])
        if "continuity_scope_id" in doc:
            _check_nes(errors, "continuity_scope_id", doc["continuity_scope_id"])
        if "direction" in doc:
            _check_enum(errors, "direction", doc["direction"], ("before", "after", "around"))
        if "anchor_event_id" in doc:
            _check_nes(errors, "anchor_event_id", doc["anchor_event_id"])
        if "actors" in doc:
            _check_actor_map(errors, "actors", doc["actors"])
        if "events" in doc:
            events = doc["events"]
            if not isinstance(events, list):
                errors.add("events", "must be an array of typed events")
            else:
                for index, event in enumerate(events):
                    _check_event(errors, f"events[{index}]", event)
        if "coverage" in doc:
            _check_coverage(errors, "coverage", doc["coverage"])
        if "next_cursor" in doc:
            _check_nes(errors, "next_cursor", doc["next_cursor"])
        return list(errors)
    # ContextFetch: directional anchor-bearing fetch request.
    required = ("request_id", "handle_id", "direction", "max_events", "max_bytes")
    allowed = required + ("anchor_event_id", "cursor")
    if not _check_closed_object(errors, "continuation", doc, required, allowed):
        return list(errors)
    if "request_id" in doc:
        _check_nes(errors, "request_id", doc["request_id"])
    if "handle_id" in doc:
        _check_nes(errors, "handle_id", doc["handle_id"])
    direction = doc.get("direction")
    if "direction" in doc:
        _check_enum(errors, "direction", direction, ("before", "after", "around"))
    if "anchor_event_id" in doc:
        _check_nes(errors, "anchor_event_id", doc["anchor_event_id"])
    elif direction == "around":
        errors.add("anchor_event_id", "required when direction is 'around'")
    if "cursor" in doc:
        _check_nes(errors, "cursor", doc["cursor"])
    for name in ("max_events", "max_bytes"):
        if name in doc:
            amount = doc[name]
            if not _is_integer(amount):
                errors.add(name, "must be an integer")
            elif amount < 1:
                errors.add(name, "must be a positive budget (>= 1)")
    return list(errors)


def _check_observation_body(errors: _Errors, path: str, value: Any) -> None:
    required = ("schema_version", "trigger_event_id", "continuity_scope_id", "event_count", "byte_count", "coverage", "included_event_ids")
    if not _check_closed_object(errors, path, value, required, required):
        return
    if value.get("schema_version") != 2:
        errors.add(f"{path}.schema_version", "must be the number 2")
    if "trigger_event_id" in value:
        _check_nes(errors, f"{path}.trigger_event_id", value["trigger_event_id"])
    if "continuity_scope_id" in value:
        _check_nes(errors, f"{path}.continuity_scope_id", value["continuity_scope_id"])
    for name in ("event_count", "byte_count"):
        if name in value:
            count = value[name]
            if not _is_integer(count):
                errors.add(f"{path}.{name}", "must be an integer")
            elif count < 0:
                errors.add(f"{path}.{name}", "must be >= 0")
    if "coverage" in value:
        _check_coverage(errors, f"{path}.coverage", value["coverage"])
    if "included_event_ids" in value:
        cited = value["included_event_ids"]
        if not isinstance(cited, list):
            errors.add(f"{path}.included_event_ids", "must be an array of event IDs")
        else:
            for index, event_id in enumerate(cited):
                _check_nes(errors, f"{path}.included_event_ids[{index}]", event_id)


def _attention_body_variant(value: Any) -> str | None:
    """Which of the three mutually exclusive attention outcomes this is."""
    if not isinstance(value, dict):
        return None
    if "error" in value:
        return "error"
    if "classifier_not_invoked" in value:
        return "bypass"
    return "classifier"


def _check_attention_body(errors: _Errors, path: str, value: Any) -> None:
    variant = _attention_body_variant(value)
    if variant is None:
        errors.add(path, "must be an object")
        return
    if variant == "classifier":
        fields = ("classifier_disposition", "effective_disposition", "classifier", "evidence_event_ids", "routing_audit")
        if not _check_closed_object(errors, path, value, fields, fields):
            return
        if "classifier_disposition" in value:
            _check_enum(
                errors, f"{path}.classifier_disposition", value["classifier_disposition"], DISPOSITIONS
            )
        if "effective_disposition" in value:
            _check_enum(
                errors, f"{path}.effective_disposition", value["effective_disposition"], DISPOSITIONS
            )
        if "classifier" in value:
            _check_classifier_audit(errors, f"{path}.classifier", value["classifier"])
        if "evidence_event_ids" in value:
            cited = value["evidence_event_ids"]
            if not isinstance(cited, list):
                errors.add(f"{path}.evidence_event_ids", "must be an array of event IDs")
            else:
                for index, event_id in enumerate(cited):
                    _check_nes(errors, f"{path}.evidence_event_ids[{index}]", event_id)
        if "routing_audit" in value:
            _check_routing_audit(errors, value["routing_audit"])
        return
    if variant == "error":
        if not _check_closed_object(errors, path, value, ("error",), ("error",)):
            return
        error = value.get("error")
        if _check_closed_object(errors, f"{path}.error", error, ("code", "detail"), ("code", "detail")):
            if "code" in error:
                _check_nes(errors, f"{path}.error.code", error["code"])
            if "detail" in error and not isinstance(error["detail"], str):
                errors.add(f"{path}.error.detail", "must be a string")
        return
    fields = ("classifier_not_invoked", "cause", "policy_provenance")
    if not _check_closed_object(errors, path, value, fields, fields):
        return
    if "classifier_not_invoked" in value and value["classifier_not_invoked"] is not True:
        errors.add(f"{path}.classifier_not_invoked", "must be exactly true on a bypass record")
    if "cause" in value and value["cause"] != "preattention-disabled":
        errors.add(f"{path}.cause", "must be exactly 'preattention-disabled'")
    if "policy_provenance" in value:
        _check_nes(errors, f"{path}.policy_provenance", value["policy_provenance"])


def _check_participant_host_body(errors: _Errors, path: str, value: Any) -> None:
    fields = ("wake_source", "packet_event_count", "packet_byte_count", "delivered_event_ids", "expansion_calls", "invoked", "outcome")
    if not _check_closed_object(errors, path, value, fields, fields):
        return
    if "wake_source" in value:
        _check_enum(errors, f"{path}.wake_source", value["wake_source"], WAKE_SOURCES)
    for name in ("packet_event_count", "packet_byte_count", "expansion_calls"):
        if name in value:
            amount = value[name]
            if not _is_integer(amount):
                errors.add(f"{path}.{name}", "must be an integer")
            elif amount < 0:
                errors.add(f"{path}.{name}", "must be >= 0")
    if "delivered_event_ids" in value:
        cited = value["delivered_event_ids"]
        if not isinstance(cited, list):
            errors.add(f"{path}.delivered_event_ids", "must be an array of event IDs")
        else:
            for index, event_id in enumerate(cited):
                _check_nes(errors, f"{path}.delivered_event_ids[{index}]", event_id)
    if "invoked" in value and not isinstance(value["invoked"], bool):
        errors.add(f"{path}.invoked", "must be a boolean")
    if "outcome" in value:
        _check_enum(errors, f"{path}.outcome", value["outcome"], ("sent", "silent", "unknown"))


def _check_transport_body(errors: _Errors, path: str, value: Any) -> None:
    if not _check_closed_object(errors, path, value, ("delivery",), ("delivery", "detail")):
        return
    if "delivery" in value:
        _check_enum(
            errors, f"{path}.delivery", value["delivery"], ("sent", "failed", "unknown", "unavailable")
        )
    if "detail" in value and not isinstance(value["detail"], str):
        errors.add(f"{path}.detail", "must be a string")


_STAGE_BODY_CHECKS: dict[str, Callable[[_Errors, str, Any], None]] = {
    "observation": _check_observation_body,
    "attention": _check_attention_body,
    "participant-host": _check_participant_host_body,
    "transport": _check_transport_body,
}


def validate_attention_receipt(doc: Any) -> list[str]:
    """Mirror of schemas/v2/attention-receipt.schema.json (I-010E).

    The FR-010 stage-to-writer binding is part of the public per-record
    contract (rejection R3): each stage names its single directly
    observing owner per ``RECEIPT_WRITER_MAP``, so a record attributing
    one stage to another stage's owner — for example ``stage:
    observation`` written by ``transport`` — is invalid as a single
    document, independent of the stream-level checks in
    ``validate_receipt_stream``.
    """
    errors = _Errors()
    fields = ("request_id", "stage", "writer", "body")
    if not _check_closed_object(errors, "receipt", doc, fields, fields):
        return list(errors)
    _check_nes(errors, "request_id", doc.get("request_id"))
    stage = doc.get("stage")
    if "stage" in doc:
        _check_enum(errors, "stage", stage, RECEIPT_STAGES)
    if "writer" in doc:
        _check_enum(errors, "writer", doc["writer"], RECEIPT_WRITERS)
        if stage in RECEIPT_WRITER_MAP and doc["writer"] in RECEIPT_WRITERS:
            owner = RECEIPT_WRITER_MAP[stage]
            if doc["writer"] != owner:
                errors.add(
                    "writer",
                    f"stage {stage!r} is owned by {owner!r}; {doc['writer']!r} "
                    "must not attest another owner's stage (FR-010 per-record "
                    "stage-to-writer binding)",
                )
    if "body" in doc and stage in _STAGE_BODY_CHECKS:
        _STAGE_BODY_CHECKS[stage](errors, "body", doc["body"])
    elif "body" in doc and not isinstance(doc["body"], dict):
        errors.add("body", "must be an object")
    return list(errors)


DOCUMENT_VALIDATORS: dict[str, Callable[[Any], list[str]]] = {
    "attention-request": validate_attention_request,
    "attention-decision": validate_attention_decision,
    "participant-wake": validate_participant_wake,
    "context-continuation": validate_context_continuation,
    "attention-receipt": validate_attention_receipt,
}


# ---------------------------------------------------------------------------
# Runtime-adapter-only semantic/relational checks (the closed FR-012 set)
# ---------------------------------------------------------------------------


def _event_ids(doc: dict[str, Any]) -> list[str]:
    events = doc.get("events")
    if not isinstance(events, list):
        return []
    return [
        event["id"]
        for event in events
        if isinstance(event, dict) and isinstance(event.get("id"), str)
    ]


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp; an omitted or unparseable value is
    treated as unknown and exempted from the order rule."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_id_uniqueness(doc: dict[str, Any]) -> list[str]:
    """Cross-item ID uniqueness: stable event IDs are unique within one
    request/continuity scope (FR-003); duplicates reject."""
    errors: list[str] = []
    seen: set[str] = set()
    for event_id in _event_ids(doc):
        if event_id in seen:
            errors.append(f"events: duplicate event_id {event_id!r} within one request")
        seen.add(event_id)
    return errors


def check_cross_document_id_uniqueness(
    request_doc: dict[str, Any], page_doc: dict[str, Any]
) -> list[str]:
    """Continuity-scope uniqueness across documents: a continuation page
    whose event IDs collide with its originating request rejects at fetch
    time under the exact merge-identity rule (FR-003/FR-009)."""
    errors = check_id_uniqueness(page_doc)
    request_ids = set(_event_ids(request_doc))
    for event_id in _event_ids(page_doc):
        if event_id in request_ids:
            errors.append(
                f"events: continuation-page event_id {event_id!r} collides with "
                "the originating request within one continuity scope"
            )
    return errors


def check_timestamp_order(doc: dict[str, Any]) -> list[str]:
    """Timestamp-versus-order agreement: authoritative array order is the
    truth; non-null timestamps must not contradict it (non-decreasing)."""
    errors: list[str] = []
    events = doc.get("events")
    if not isinstance(events, list):
        return errors
    previous: datetime | None = None
    previous_index = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        parsed = _parse_timestamp(event.get("timestamp"))
        if parsed is None:
            continue
        if previous is not None and parsed < previous:
            errors.append(
                f"events[{index}].timestamp disagrees with authoritative array "
                f"order (earlier than events[{previous_index}].timestamp)"
            )
        previous = parsed
        previous_index = index
    return errors


def check_trigger_membership(doc: dict[str, Any]) -> list[str]:
    """Trigger membership: the one included trigger must be in ``events``."""
    trigger = doc.get("trigger_event_id")
    if isinstance(trigger, str) and trigger not in _event_ids(doc):
        return [f"trigger_event_id: trigger {trigger!r} is absent from events"]
    return []


def _event_actor_references(event: dict[str, Any]) -> list[tuple[str, Any]]:
    """Every typed actor-ID field an event may carry, by exact field name
    (FR-014): message/reaction ``author_id`` and message
    ``mentioned_actor_ids``; membership ``subject_actor_id`` and optional
    ``caused_by_actor_id``."""
    event_type = event.get("type")
    refs: list[tuple[str, Any]] = []
    if event_type in ("message", "reaction"):
        refs.append(("author_id", event.get("author_id")))
    if event_type == "message":
        mentioned = event.get("mentioned_actor_ids")
        if isinstance(mentioned, list):
            for index, actor_id in enumerate(mentioned):
                refs.append((f"mentioned_actor_ids[{index}]", actor_id))
    if event_type == "membership":
        refs.append(("subject_actor_id", event.get("subject_actor_id")))
        if "caused_by_actor_id" in event:
            refs.append(("caused_by_actor_id", event.get("caused_by_actor_id")))
    return refs


def check_actor_reference_integrity(doc: dict[str, Any]) -> list[str]:
    """Actor-map reference integrity (rejection R8): ``self.actor_id`` and
    every typed event's actor references — author, structured mention
    target, reaction author, membership subject/causal actor — must resolve
    to a key present in ``actors``. The selected design's actor map is the
    observed/referenced cast; a reference absent from it is a dangling
    opaque string, not a valid binding. Document-shaped and runtime-adapter
    -only: Draft 2020-12 cannot express dynamic key membership against a
    sibling object."""
    errors: list[str] = []
    actors = doc.get("actors")
    if not isinstance(actors, dict):
        return errors
    self_binding = doc.get("self")
    if isinstance(self_binding, dict):
        actor_id = self_binding.get("actor_id")
        if isinstance(actor_id, str) and actor_id not in actors:
            errors.append(f"self.actor_id: {actor_id!r} is absent from actors")
    events = doc.get("events")
    if not isinstance(events, list):
        return errors
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        for field, actor_id in _event_actor_references(event):
            if isinstance(actor_id, str) and actor_id not in actors:
                errors.append(f"events[{index}].{field}: {actor_id!r} is absent from actors")
    return errors


def _advice_citations(advice_doc: dict[str, Any]) -> list[str]:
    """Collect every evidence-event-ID citation from either advice shape:
    a decision's ``attention_advice`` array, or a wake's ``attention.advice``
    array plus its sibling ``attention.evidence_event_ids``."""
    cited: list[str] = []
    for item in advice_doc.get("attention_advice") or []:
        if isinstance(item, dict) and isinstance(item.get("evidence_event_ids"), list):
            cited.extend(e for e in item["evidence_event_ids"] if isinstance(e, str))
    attention = advice_doc.get("attention")
    if isinstance(attention, dict):
        for item in attention.get("advice") or []:
            if isinstance(item, dict) and isinstance(item.get("evidence_event_ids"), list):
                cited.extend(e for e in item["evidence_event_ids"] if isinstance(e, str))
        cited.extend(e for e in attention.get("evidence_event_ids") or [] if isinstance(e, str))
    return cited


def check_advice_citations(
    advice_doc: dict[str, Any], request_doc: dict[str, Any]
) -> list[str]:
    """Cross-document advice citations: every advice evidence citation must
    reference an event ID supplied in the request (FR-013)."""
    known = set(_event_ids(request_doc))
    return [
        f"advice.evidence_event_ids: citation {event_id!r} references no event "
        "supplied in the request"
        for event_id in _advice_citations(advice_doc)
        if event_id not in known
    ]


def validate_continuation_fetch(payload: dict[str, Any]) -> list[str]:
    """Fetch-time binding/expiry state (runtime-adapter-only, behavioral).

    ``payload`` carries the host's fetch context: ``fetch_time``, the
    ``host_context`` this fetch call is actually being made under
    (``participant_id``, ``room_id``, ``continuity_scope_id``,
    ``trigger_event_id``), the ``issued`` handle states — each carrying its
    full continuation capability (``handle_id``, exact ``bound_to``,
    ``can_fetch_before``/``can_fetch_after``/``can_fetch_around_event``,
    ``max_events_per_fetch``/``max_bytes_per_fetch``, ``expires_at``, and the
    ``cursors`` minted under that handle) — and the incoming fetch
    ``request`` document. The request document itself must be schema-valid;
    its handle must be known and unexpired at fetch time; the capability's
    exact ``bound_to`` must match the host's actual call context; the
    requested direction must be authorized by that capability; the requested
    ``max_events``/``max_bytes`` must not exceed the capability's issued
    caps; and any cursor must be minted under that same handle (cross-binding
    cursor reuse rejects). A known, unexpired handle alone does not establish
    correct binding or bounded authorization (rejection R10) — every one of
    those facts is checked explicitly against the issued capability.
    """
    errors: list[str] = []
    request = payload.get("request")
    errors.extend(validate_context_continuation(request))
    if not isinstance(request, dict) or "max_events" not in request:
        errors.append("fetch.request: must be a fetch-request document")
        return errors
    issued_states = payload.get("issued")
    if not isinstance(issued_states, list):
        return errors + ["fetch.issued: must list the host's issued handle states"]
    fetch_time = _parse_timestamp(payload.get("fetch_time"))
    if fetch_time is None:
        return errors + ["fetch.fetch_time: must be an ISO 8601 timestamp"]

    by_handle = {
        state.get("handle_id"): state
        for state in issued_states
        if isinstance(state, dict)
    }
    handle_id = request.get("handle_id")
    state = by_handle.get(handle_id)
    if state is None:
        errors.append(f"handle_id: {handle_id!r} was never issued for this continuity scope")
        return errors

    host_context = payload.get("host_context")
    bound_to = state.get("bound_to")
    if not isinstance(bound_to, dict) or not isinstance(host_context, dict) or host_context != bound_to:
        errors.append(
            f"handle_id: {handle_id!r} is bound to {bound_to!r} but the host "
            f"call context is {host_context!r} (exact-binding mismatch)"
        )

    expires_at = _parse_timestamp(state.get("expires_at"))
    if expires_at is None:
        errors.append("fetch.issued.expires_at: must be an ISO 8601 timestamp")
    elif fetch_time > expires_at:
        errors.append(
            f"handle_id: {handle_id!r} expired at {state.get('expires_at')} and is "
            "rejected at fetch time (binding-validation failure)"
        )

    direction = request.get("direction")
    direction_capability = {
        "before": "can_fetch_before",
        "after": "can_fetch_after",
        "around": "can_fetch_around_event",
    }.get(direction)
    if direction_capability is not None and not state.get(direction_capability):
        errors.append(
            f"direction: {direction!r} is not authorized by handle_id "
            f"{handle_id!r}'s issued capability ({direction_capability} is not true)"
        )

    for field, cap_field in (
        ("max_events", "max_events_per_fetch"),
        ("max_bytes", "max_bytes_per_fetch"),
    ):
        requested = request.get(field)
        cap = state.get(cap_field)
        if isinstance(requested, int) and isinstance(cap, int) and requested > cap:
            errors.append(
                f"{field}: requested {requested} exceeds handle_id {handle_id!r}'s "
                f"issued cap of {cap} ({cap_field})"
            )

    cursor = request.get("cursor")
    if cursor is not None:
        minted = state.get("cursors")
        minted = minted if isinstance(minted, list) else []
        if cursor not in minted:
            other = sorted(
                str(other_state.get("handle_id"))
                for other_state in issued_states
                if isinstance(other_state, dict)
                and other_state is not state
                and isinstance(other_state.get("cursors"), list)
                and cursor in other_state["cursors"]
            )
            if other:
                errors.append(
                    f"cursor: {cursor!r} was minted under handle "
                    f"{other[0]!r}; cursor reuse across bindings is rejected"
                )
            else:
                errors.append(f"cursor: {cursor!r} was never minted for handle {handle_id!r}")
    return errors


def validate_receipt_stream(records: Any) -> list[str]:
    """Receipt-stage sequence rules (runtime-adapter-only, behavioral).

    A receipt stream is the append-only record sequence for one request:
    every record schema-valid, all correlated by the same request ID, the
    stages in canonical order (observation -> attention -> participant-host
    -> transport) as a prefix (a prefix-partial receipt is
    valid-in-progress), no stage appended twice (append-only immutability),
    and each stage written only by its owning writer per the staged-receipt
    writer map.
    """
    errors: list[str] = []
    if not isinstance(records, list) or not records:
        return ["stream: a receipt stream must contain at least one stage record"]
    for index, record in enumerate(records):
        for message in validate_attention_receipt(record):
            errors.append(f"stream[{index}].{message}")
    if errors:
        return errors
    request_ids = {record["request_id"] for record in records}
    if len(request_ids) != 1:
        errors.append(
            "stream: stage records must all be correlated by one request ID, "
            f"found {sorted(request_ids)}"
        )
    stages = [record["stage"] for record in records]
    expected_prefix = list(RECEIPT_STAGES[: len(stages)])
    if len(stages) > len(RECEIPT_STAGES):
        errors.append("stream: more stage records than canonical stages")
    elif stages != expected_prefix:
        duplicated = {stage for stage in stages if stages.count(stage) > 1}
        if duplicated:
            errors.append(
                f"stream: stage(s) {sorted(duplicated)} appended more than once; "
                "stage records are immutable and append-only"
            )
        else:
            errors.append(
                f"stream: stages {stages} must follow the canonical order "
                f"{list(RECEIPT_STAGES)} as a prefix"
            )
    for index, record in enumerate(records):
        owner = RECEIPT_WRITER_MAP[record["stage"]]
        if record["writer"] != owner:
            errors.append(
                f"stream[{index}].writer: stage {record['stage']!r} is owned by "
                f"{owner!r}; {record['writer']!r} must not fill another owner's stage"
            )
    return errors


# ---------------------------------------------------------------------------
# Case runner: adapter and oracle verdicts plus fixed oracle expectations
# ---------------------------------------------------------------------------


def adapter_errors(case: CorpusCase) -> list[str]:
    """Full stdlib-adapter validation for one corpus case."""
    errors: list[str] = []
    for schema_name, document in case.oracle_documents():
        errors.extend(DOCUMENT_VALIDATORS[schema_name](document))
    if case.partition == SCHEMA_EXPRESSIBLE:
        return errors
    if case.partition == "id-uniqueness":
        if case.document is not None:
            errors.extend(check_id_uniqueness(case.document))
        else:
            docs = {entry["schema"]: entry["document"] for entry in case.documents}
            errors.extend(
                check_cross_document_id_uniqueness(
                    docs["attention-request"], docs["context-continuation"]
                )
            )
    elif case.partition == "timestamp-order":
        errors.extend(check_timestamp_order(case.document))
    elif case.partition == "trigger-membership":
        errors.extend(check_trigger_membership(case.document))
    elif case.partition == "actor-reference-integrity":
        errors.extend(check_actor_reference_integrity(case.document))
    elif case.partition == "advice-citation":
        if case.document is not None:
            # A wake packet materializes its own events, so the citation
            # rule is checked against its own top-level event array.
            errors.extend(check_advice_citations(case.document, case.document))
        else:
            docs = {entry["schema"]: entry["document"] for entry in case.documents}
            errors.extend(
                check_advice_citations(docs["attention-decision"], docs["attention-request"])
            )
    elif case.partition == "binding-expiry":
        errors.extend(validate_continuation_fetch(case.fetch))
    elif case.partition == "receipt-sequence":
        errors.extend(validate_receipt_stream(case.stream))
    return errors


def adapter_verdict(case: CorpusCase) -> str:
    return "invalid" if adapter_errors(case) else "valid"


def oracle_expectation(case: CorpusCase) -> str:
    """The fixed per-class oracle treatment (FR-012).

    Schema-expressible cases expect the case verdict; document-shaped
    relational classes expect valid (each document is schema-valid in
    isolation); behavioral classes are skipped by explicit class.
    """
    if case.partition == SCHEMA_EXPRESSIBLE:
        return case.expected
    if case.partition in ORACLE_VALID_CLASSES:
        return "valid"
    return ORACLE_CLASS_SKIP


def oracle_verdict(case: CorpusCase, oracle_validators: dict[str, Any]) -> str:
    if case.partition in ORACLE_SKIP_CLASSES:
        return ORACLE_CLASS_SKIP
    for schema_name, document in case.oracle_documents():
        if not oracle_validators[schema_name].is_valid(document):
            return "invalid"
    return "valid"


def case_payload_for_preservation(case: CorpusCase) -> tuple[Any, Any] | None:
    """Raw payload tokens and loaded payload for valid single-document cases."""
    if case.document is None or case.expected != "valid":
        return None
    envelope_tokens = token_parse(case.raw_line)
    raw_tokens = decode_non_finite_tokens(envelope_tokens["document"])
    return raw_tokens, case.document


# ---------------------------------------------------------------------------
# Evidence writer (aggregate JSONL records; requires the pinned oracle)
# ---------------------------------------------------------------------------

EVIDENCE_FILES = {
    "attention-request": "attention-request.jsonl",
    "attention-decision": "attention-decision.jsonl",
    "downstream": "downstream.jsonl",
}

# The five mandatory aggregate-record fields (plan §Acceptance Scenes and
# Evidence; CHK070): scene_id, stable case_id, validator identity, expected
# result, and observed result. The writer refuses any record missing one.
MANDATORY_EVIDENCE_FIELDS = ("scene_id", "case_id", "validator", "expected", "observed")


class EvidenceError(AssertionError):
    """An aggregate evidence record violates the mandatory-field shape."""


def enforce_evidence_record(record: Any, context: str) -> None:
    """Refuse any aggregate evidence record missing a mandatory field."""
    if not isinstance(record, dict):
        raise EvidenceError(f"{context}: evidence record must be an object")
    missing = [
        field
        for field in MANDATORY_EVIDENCE_FIELDS
        if not isinstance(record.get(field), str) or not record.get(field)
    ]
    if missing:
        raise EvidenceError(
            f"{context}: evidence record is missing mandatory field(s) "
            f"{missing}; every aggregate JSONL record must carry all of "
            f"{list(MANDATORY_EVIDENCE_FIELDS)}"
        )


def verify_evidence_file(path: Path) -> int:
    """Enforce the mandatory shape on every record of one landed evidence
    file, returning the number of records verified."""
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            record = json.loads(raw_line)
            enforce_evidence_record(record, f"{path.name}:{line_number}")
            count += 1
    if count == 0:
        raise EvidenceError(f"{path.name}: evidence file contains no records")
    return count


def verify_evidence() -> int:
    """Re-verify every landed aggregate evidence file (T021)."""
    status = 0
    for filename in EVIDENCE_FILES.values():
        path = EVIDENCE_DIR / filename
        try:
            count = verify_evidence_file(path)
        except (OSError, ValueError, EvidenceError) as failure:
            print(f"{filename}: FAIL — {failure}", file=sys.stderr)
            status = 1
        else:
            print(f"{filename}: {count} records carry all mandatory fields")
    return status


def evidence_records(corpus: str, oracle_validators: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in load_corpus(corpus):
        observed_oracle = oracle_verdict(case, oracle_validators)
        expected_oracle = oracle_expectation(case)
        observed_adapter = adapter_verdict(case)
        records.append(
            {
                "case_id": case.case_id,
                "scene_id": case.scene_id,
                "title": case.title,
                "partition": case.partition,
                "validator": ORACLE_VALIDATOR_ID,
                "expected": expected_oracle,
                "observed": observed_oracle,
                "match": observed_oracle == expected_oracle,
            }
        )
        records.append(
            {
                "case_id": case.case_id,
                "scene_id": case.scene_id,
                "title": case.title,
                "partition": case.partition,
                "validator": ADAPTER_VALIDATOR_ID,
                "expected": case.expected,
                "observed": observed_adapter,
                "match": observed_adapter == case.expected,
            }
        )
    return records


def write_evidence() -> int:
    available, detail = oracle_status()
    if not available:
        print(
            "evidence writer requires the pinned oracle; run it through the "
            f"pinned offline command ({detail})",
            file=sys.stderr,
        )
        return 1
    oracle_validators = build_oracle_validators()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for corpus, filename in EVIDENCE_FILES.items():
        records = evidence_records(corpus, oracle_validators)
        for record in records:
            enforce_evidence_record(record, f"{filename} ({record.get('case_id')})")
        path = EVIDENCE_DIR / filename
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        mismatched = [record for record in records if not record["match"]]
        failures += len(mismatched)
        print(
            f"{path.relative_to(REPO_ROOT)}: {len(records)} records "
            f"({len(mismatched)} mismatched)"
        )
        for record in mismatched:
            print(
                f"  MISMATCH {record['case_id']} [{record['validator']}] "
                f"expected={record['expected']} observed={record['observed']}",
                file=sys.stderr,
            )
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Control-plane read boundary (CHK076): the suite and corpus embed their own
# copy of the FR-012 class vocabulary and never read a SpecKit-managed file
# ---------------------------------------------------------------------------

TESTS_DIR = REPO_ROOT / "tests" / "v2" / "contract"


def scan_control_plane_references(
    prefixes: tuple[str, ...],
    roots: tuple[Path, ...] = (TESTS_DIR, EVALS_DIR),
) -> list[str]:
    """Scan the test and corpus trees for control-plane path references.

    Returns ``path:line: content`` for every line under ``roots`` whose
    text contains one of the forbidden ``prefixes``. The covering test owns
    the prefix tuple; it builds each prefix by compile-time concatenation
    so its own declaration is never a contiguous forbidden token.
    """
    hits: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if any(prefix in line for prefix in prefixes):
                    relative = path.relative_to(REPO_ROOT)
                    hits.append(f"{relative}:{line_number}: {line.strip()}")
    return hits


# ---------------------------------------------------------------------------
# Deterministic fixture factories (used by the inline red/green tests and by
# corpus authoring; every factory returns a fresh deep copy)
# ---------------------------------------------------------------------------

_BASE_REQUEST = {
    "schema_version": 2,
    "request_id": "req-0001",
    "self": {
        "participant_id": "vigil",
        "actor_id": "discord:9001",
        "names": ["Vigil", "Aether"],
        "role": "developer",
        "description": "resident coding agent",
    },
    "room": {"platform": "discord", "id": "42", "continuity_scope_id": "discord:room:42#2026-07"},
    "actors": {
        "discord:9001": {"display_name": "Vigil", "kind": "bot"},
        "discord:1001": {"display_name": "Zoe", "kind": "human"},
        "discord:2002": {"display_name": "Vigil", "kind": "bot"},
        "discord:3003": {"display_name": "Sol", "kind": "bot"},
    },
    "events": [
        {
            "id": "e1",
            "type": "message",
            "author_id": "discord:1001",
            "timestamp": "2026-07-17T01:00:00Z",
            "text": "hey @Vigil can you take the deploy?",
            "mentioned_actor_ids": ["discord:9001"],
            "mentions_room": False,
        },
        {
            "id": "e2",
            "type": "message",
            "author_id": "discord:2002",
            "timestamp": "2026-07-17T01:00:05Z",
            "text": "I can take it",
            "mentioned_actor_ids": [],
            "mentions_room": False,
        },
        {
            "id": "e3",
            "type": "message",
            "author_id": "discord:1001",
            "timestamp": "2026-07-17T01:00:10Z",
            "text": "@here deploy starting",
            "mentioned_actor_ids": [],
            "mentions_room": True,
        },
    ],
    "trigger_event_id": "e3",
    "coverage": {
        "has_more_before": False,
        "has_more_after": False,
        "has_gaps": False,
        "truncated_by": [],
        "continuity": "session-only",
        "has_restart_gap": False,
        "max_events": 50,
        "max_bytes": 65536,
    },
}

_BASE_ADVICE = {
    "note": "Zoe addressed the participant directly about the deploy.",
    "evidence_event_ids": ["e1"],
}


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def make_request(**overrides: Any) -> dict[str, Any]:
    doc = _deep_copy(_BASE_REQUEST)
    doc.update(overrides)
    return doc


def make_advice(**overrides: Any) -> dict[str, Any]:
    advice = _deep_copy(_BASE_ADVICE)
    advice.update(overrides)
    return advice


def make_routing(valve: str = "none", **overrides: Any) -> dict[str, Any]:
    """A legal closed routing audit for the given applied valve.

    ``margin-defer`` carries the margin cross-field facts (override cause
    ``margin``, margin status ``active``, the effective margin) and
    ``policy-defer`` a policy override cause; ``none``/``classifier-defer``
    carry override cause ``none``. The default margin status is ``active``
    because the uncertainty margin remains active at initial V2 cutover.
    """
    routing: dict[str, Any] = {
        "valve": valve,
        "override_cause": "none",
        "margin_status": "active",
    }
    if valve == "margin-defer":
        routing["override_cause"] = "margin"
        routing["effective_margin"] = 0.12
    elif valve == "policy-defer":
        routing["override_cause"] = "suppression-disabled"
    routing.update(overrides)
    return routing


def make_decision_ok(
    classifier: str = "WAKE",
    effective: str = "WAKE",
    valve: str = "none",
    **overrides: Any,
) -> dict[str, Any]:
    doc = {
        "status": "ok",
        "request_id": "req-0001",
        "classifier_disposition": classifier,
        "effective_disposition": effective,
        "routing_audit": make_routing(valve),
        "reasons": ["directly addressed about the deploy"],
        "evidence_event_ids": ["e1", "e3"],
        "classifier": {
            "name": "nunchi-classifier",
            "provider": "openrouter",
            "model": "test-model",
        },
        "legacy_verdict_confidences": {"PASS": 0.05, "ACK": 0.1, "ASK": 0.15, "SPEAK": 0.7},
    }
    doc.update(overrides)
    return doc


def make_decision_bypass(**overrides: Any) -> dict[str, Any]:
    doc = {
        "status": "bypass",
        "request_id": "req-0002",
        "cause": "preattention-disabled",
    }
    doc.update(overrides)
    return doc


def make_decision_error(code: str = "malformed-model-output", **overrides: Any) -> dict[str, Any]:
    doc = {
        "status": "error",
        "request_id": "req-0003",
        "error": {"code": code, "detail": "classifier output failed validation"},
    }
    doc.update(overrides)
    return doc


def make_wake(source: str = "WAKE", advice: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    request = make_request()
    attention: dict[str, Any] = {"source": source}
    if advice is not None:
        attention["advice"] = advice
        attention["evidence_event_ids"] = sorted(
            {event_id for item in advice for event_id in item.get("evidence_event_ids", [])}
        )
    doc = {
        "request_id": request["request_id"],
        "self": request["self"],
        "room": request["room"],
        "actors": request["actors"],
        "events": request["events"],
        "trigger_event_id": request["trigger_event_id"],
        "coverage": request["coverage"],
        "attention": attention,
    }
    doc.update(overrides)
    return doc


def make_fetch_request(**overrides: Any) -> dict[str, Any]:
    doc = {
        "request_id": "req-0001",
        "handle_id": "cont-7f3a",
        "direction": "before",
        "max_events": 20,
        "max_bytes": 16384,
    }
    doc.update(overrides)
    return doc


def make_fetch_page(**overrides: Any) -> dict[str, Any]:
    doc = {
        "request_id": "req-0001",
        "handle_id": "cont-7f3a",
        "room_id": "42",
        "continuity_scope_id": "discord:room:42#2026-07",
        "direction": "before",
        "anchor_event_id": "e3",
        "actors": {"discord:1001": {"display_name": "Zoe", "kind": "human"}},
        "events": [
            {
                "id": "e0",
                "type": "message",
                "author_id": "discord:1001",
                "timestamp": "2026-07-17T00:59:00Z",
                "text": "earlier context before the bounded tail",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            }
        ],
        "coverage": {
            "has_more_before": True,
            "has_more_after": False,
            "has_gaps": True,
            "truncated_by": ["events"],
            "continuity": "session-only",
            "has_restart_gap": False,
        },
        "next_cursor": "cur-2",
    }
    doc.update(overrides)
    return doc


_FETCH_BOUND_TO = {
    "participant_id": "vigil",
    "room_id": "42",
    "continuity_scope_id": "discord:room:42#2026-07",
    "trigger_event_id": "e3",
}


def make_fetch_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "fetch_time": "2026-07-17T01:30:00Z",
        "host_context": dict(_FETCH_BOUND_TO),
        "issued": [
            {
                "handle_id": "cont-7f3a",
                "bound_to": dict(_FETCH_BOUND_TO),
                "can_fetch_before": True,
                "can_fetch_after": False,
                "can_fetch_around_event": True,
                "max_events_per_fetch": 20,
                "max_bytes_per_fetch": 16384,
                "expires_at": "2026-07-17T02:00:00Z",
                "cursors": ["cur-1", "cur-2"],
            },
            {
                "handle_id": "cont-9b2c",
                "bound_to": {
                    "participant_id": "vigil",
                    "room_id": "999",
                    "continuity_scope_id": "discord:room:999#2026-07",
                    "trigger_event_id": "e-other",
                },
                "can_fetch_before": True,
                "can_fetch_after": True,
                "can_fetch_around_event": True,
                "max_events_per_fetch": 50,
                "max_bytes_per_fetch": 65536,
                "expires_at": "2026-07-17T04:00:00Z",
                "cursors": ["cur-x1"],
            },
        ],
        "request": make_fetch_request(),
    }
    payload.update(overrides)
    return payload


_STAGE_BODIES = {
    "observation": {
        "schema_version": 2,
        "trigger_event_id": "e3",
        "continuity_scope_id": "discord:room:42#2026-07",
        "event_count": 3,
        "byte_count": 512,
        "coverage": {
            "has_more_before": False,
            "has_more_after": False,
            "has_gaps": False,
            "truncated_by": [],
            "continuity": "session-only",
            "has_restart_gap": False,
        },
        "included_event_ids": ["e1", "e2", "e3"],
    },
    "attention": {
        "classifier_disposition": "WAKE",
        "effective_disposition": "WAKE",
        "classifier": {"name": "nunchi-classifier"},
        "evidence_event_ids": ["e1", "e3"],
        "routing_audit": {"valve": "none", "override_cause": "none", "margin_status": "active"},
    },
    "participant-host": {
        "wake_source": "WAKE",
        "packet_event_count": 3,
        "packet_byte_count": 512,
        "delivered_event_ids": ["e1", "e2", "e3"],
        "expansion_calls": 0,
        "invoked": True,
        "outcome": "sent",
    },
    "transport": {"delivery": "sent", "detail": "discord:msg:555"},
}


def make_receipt(stage: str, writer: str | None = None, body: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    doc = {
        "request_id": "req-0001",
        "stage": stage,
        "writer": writer if writer is not None else RECEIPT_WRITER_MAP[stage],
        "body": _deep_copy(body if body is not None else _STAGE_BODIES[stage]),
    }
    doc.update(overrides)
    return doc


def make_receipt_stream(upto: int = 4) -> list[dict[str, Any]]:
    return [make_receipt(stage) for stage in RECEIPT_STAGES[:upto]]


# ---------------------------------------------------------------------------
# unittest support: shared oracle cache, dual-verdict assertion, and the
# corpus-runner mixin used by the four contract suites
# ---------------------------------------------------------------------------

_SHARED_ORACLE: dict[str, Any] | None = None


def shared_oracle_validators() -> dict[str, Any] | None:
    """The oracle validators, built once, or None under the baseline."""
    global _SHARED_ORACLE
    if _SHARED_ORACLE is None and oracle_status()[0]:
        _SHARED_ORACLE = build_oracle_validators()
    return _SHARED_ORACLE


def assert_schema_verdict(testcase: Any, schema_name: str, doc: Any, expected: str) -> None:
    """Assert one schema-expressible document verdict on both validators.

    The stdlib adapter always runs; the oracle side runs only when the
    pinned oracle is available (its absence is the counted
    baseline-oracle-absence regime, surfaced by the corpus suites).
    """
    errors = DOCUMENT_VALIDATORS[schema_name](doc)
    verdict = "invalid" if errors else "valid"
    testcase.assertEqual(
        expected,
        verdict,
        f"stdlib adapter verdict for {schema_name}: {errors or 'no errors'}",
    )
    validators = shared_oracle_validators()
    if validators is not None:
        oracle_ok = validators[schema_name].is_valid(doc)
        testcase.assertEqual(
            expected == "valid",
            oracle_ok,
            f"Draft 2020-12 oracle disagrees with expected {expected!r} for {schema_name}",
        )


class ContractCorpusMixin:
    """The corpus runner: mixed into one unittest.TestCase per corpus."""

    CORPUS = ""
    REQUIRED_SCENES: frozenset[str] = frozenset()

    @classmethod
    def setUpClass(cls) -> None:  # noqa: N802 (unittest API)
        cls.cases = load_corpus(cls.CORPUS)
        cls.oracle_available, cls.oracle_detail = oracle_status()

    def test_corpus_covers_its_required_scenes(self):
        scenes = {case.scene_id for case in self.cases}
        missing = self.REQUIRED_SCENES - scenes
        self.assertFalse(
            missing,
            f"corpus {self.CORPUS!r} is missing required scene coverage: {sorted(missing)}",
        )

    def test_runtime_adapter_matches_expected_verdicts(self):
        for case in self.cases:
            with self.subTest(case_id=case.case_id, scene=case.scene_id, partition=case.partition):
                errors = adapter_errors(case)
                verdict = "invalid" if errors else "valid"
                self.assertEqual(
                    case.expected,
                    verdict,
                    f"stdlib adapter: {errors or 'no errors'} — {case.title}",
                )

    def test_oracle_matches_fixed_partition_expectations(self):
        if not self.oracle_available:
            skipped = oracle_visible_count(self.cases)
            self.skipTest(
                f"{BASELINE_ORACLE_ABSENCE}: {skipped} oracle-side check(s) "
                f"skipped ({self.oracle_detail}); the pinned offline command "
                "is the sole complete dual-validator run"
            )
        validators = shared_oracle_validators()
        for case in self.cases:
            with self.subTest(case_id=case.case_id, scene=case.scene_id, partition=case.partition):
                self.assertEqual(
                    oracle_expectation(case),
                    oracle_verdict(case, validators),
                    f"Draft 2020-12 oracle verdict diverged — {case.title}",
                )

    def test_valid_documents_preserve_semantic_fields(self):
        checked = 0
        for case in self.cases:
            payload = case_payload_for_preservation(case)
            if payload is None:
                continue
            checked += 1
            with self.subTest(case_id=case.case_id):
                self.assertIsNone(preservation_failure(*payload), case.title)
        self.assertGreater(checked, 0, "no valid single-document case exercised SC-002")

    def test_skip_regimes_are_separately_named_and_counted(self):
        counts = load_expected_counts(self.CORPUS)
        pinned_class_skips = sum(
            counts[klass]["valid"] + counts[klass]["invalid"] for klass in ORACLE_SKIP_CLASSES
        )
        observed_class_skips = class_skip_count(self.cases)
        self.assertEqual(
            pinned_class_skips,
            observed_class_skips,
            f"{ORACLE_CLASS_SKIP} count must match the authoritative per-class counts",
        )
        oracle_side = oracle_visible_count(self.cases)
        self.assertEqual(
            len(self.cases),
            observed_class_skips + oracle_side,
            "every case is either oracle-visible or an explicit class skip",
        )
        baseline_absence_skips = 0 if self.oracle_available else oracle_side
        if self.oracle_available:
            self.assertEqual(
                0,
                baseline_absence_skips,
                f"{BASELINE_ORACLE_ABSENCE} skips must be zero under the pinned command",
            )
        else:
            self.assertEqual(
                oracle_side,
                baseline_absence_skips,
                f"{BASELINE_ORACLE_ABSENCE} must count every oracle-visible check",
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write-evidence",
        action="store_true",
        help="run the corpus through both validators and write the aggregate "
        "JSONL evidence records under evidence/v2/contract/",
    )
    parser.add_argument(
        "--verify-evidence",
        action="store_true",
        help="re-verify every landed aggregate evidence file against the "
        "mandatory five-field record shape (T021/CHK070)",
    )
    args = parser.parse_args(argv)
    if args.write_evidence:
        return write_evidence()
    if args.verify_evidence:
        return verify_evidence()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
