"""Slice 020's own stdlib validation-adapter driver over the exact
attempt-6 corpus revision (T004, T037).

Loads the identical, frozen ``evals/v2/contract/{attention-request,
attention-decision,downstream}/cases.jsonl`` corpus (202 cases, corpus
revision ``bff6b463a44c1b9066fc654691042f9550da6c64``, the accepted 010
attempt-6 candidate) with a minimal loader independent of
``tests/v2/contract/schema_helpers.py`` (010-owned test code; FR-013's
"own" adapter). Every case is explicitly accounted for as either
*consumed* — validated against ``src/nunchi/observation.py``'s own
I-010A/I-010D/I-010E adapter and its runtime-adapter-only relational
checks — or *non-consumed* (I-010B ``attention-decision`` and I-010C
``participant-wake``, never validated, only counted).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nunchi.observation import (
    check_actor_reference_integrity,
    check_binding_expiry,
    check_id_uniqueness,
    check_receipt_sequence,
    check_timestamp_order,
    check_trigger_membership,
    validate_attention_receipt_record,
    validate_attention_request,
    validate_context_continuation,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EVALS_DIR = REPO_ROOT / "evals" / "v2" / "contract"
CORPUS_NAMES = ("attention-request", "attention-decision", "downstream")

# Pinned per plan/spec: the exact accepted 010 attempt-6 candidate commit
# whose corpus revision this driver must reproduce byte-for-byte.
EXPECTED_CORPUS_REVISION = "bff6b463a44c1b9066fc654691042f9550da6c64"
EXPECTED_CORPUS_SHA256 = "1ce18c9e9fc3b5aa820adcb1aad649c635fcb2ed64a7e644d4d5bba6aeb5d91f"
EXPECTED_TOTAL_CASES = 202

# I-010B (attention-decision) and I-010C (participant-wake) are never
# consumed by slice 020; every relational class is accounted for even
# where its full count lives entirely on the non-consumed side.
NON_CONSUMED_SCHEMAS = {"attention-decision", "participant-wake"}
ALL_SEVEN_CLASSES = (
    "id-uniqueness", "timestamp-order", "advice-citation",
    "trigger-membership", "actor-reference-integrity",
    "binding-expiry", "receipt-sequence",
)


class CorpusError(AssertionError):
    pass


def corpus_digest(root: Path = EVALS_DIR) -> str:
    """Framed SHA-256 over the exact three accepted attempt-6 corpus files."""
    digest = hashlib.sha256()
    for name in sorted(CORPUS_NAMES):
        relative = f"evals/v2/contract/{name}/cases.jsonl"
        data = (root / name / "cases.jsonl").read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


@dataclass
class CaseResult:
    corpus: str
    case_id: str
    scene_id: str
    partition: str
    expected: str
    consumed: bool
    observed: str | None  # "valid" | "invalid" | None (non-consumed)
    errors: list[str]

    @property
    def matched(self) -> bool:
        return (not self.consumed) or self.observed == self.expected


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def load_corpus(name: str) -> list[dict[str, Any]]:
    path = EVALS_DIR / name / "cases.jsonl"
    if not path.is_file():
        raise CorpusError(f"missing corpus file {path}")
    return _load_jsonl(path)


def _validate_single(schema: str, document: Any) -> tuple[bool, list[str]]:
    """``(consumed, errors)`` for one schema-tagged document."""
    if schema == "attention-request":
        return True, validate_attention_request(document)
    if schema == "context-continuation":
        return True, validate_context_continuation(document)
    if schema == "attention-receipt":
        return True, validate_attention_receipt_record(document)
    if schema in NON_CONSUMED_SCHEMAS:
        return False, []
    raise CorpusError(f"unrecognized schema {schema!r}")


def _relational_errors(partition: str, document: Any, schema: str) -> list[str]:
    if partition == "id-uniqueness" and schema == "attention-request":
        return check_id_uniqueness(document.get("events") or [])
    if partition == "timestamp-order":
        return check_timestamp_order(document.get("events") or [])
    if partition == "trigger-membership":
        return check_trigger_membership(document)
    if partition == "actor-reference-integrity" and schema in ("attention-request",):
        return check_actor_reference_integrity(document)
    return []


def evaluate_case(case: dict[str, Any]) -> CaseResult:
    corpus_case_id = case["case_id"]
    scene_id = case["scene_id"]
    partition = case["partition"]
    expected = case["expected"]

    # Multi-document "documents" cases (id-uniqueness across a request +
    # continuation page, or an advice-citation pair non-consumed here).
    if "documents" in case:
        entries = case["documents"]
        schemas = [entry["schema"] for entry in entries]
        if partition == "advice-citation" or set(schemas) & NON_CONSUMED_SCHEMAS:
            return CaseResult("", corpus_case_id, scene_id, partition, expected, False, None, [])
        errors: list[str] = []
        for entry in entries:
            consumed, doc_errors = _validate_single(entry["schema"], entry["document"])
            errors.extend(doc_errors)
        if partition == "id-uniqueness":
            event_lists = [entry["document"].get("events", []) for entry in entries]
            errors.extend(check_id_uniqueness(*event_lists))
        observed = "invalid" if errors else "valid"
        return CaseResult("", corpus_case_id, scene_id, partition, expected, True, observed, errors)

    # Fetch cases (binding-expiry): I-010D fetch-time validation.
    if "fetch" in case:
        errors = check_binding_expiry(case["fetch"])
        observed = "invalid" if errors else "valid"
        return CaseResult("", corpus_case_id, scene_id, partition, expected, True, observed, errors)

    # Stream cases (receipt-sequence): I-010E multi-record sequence rules.
    if "stream" in case:
        for record in case["stream"]:
            errors = validate_attention_receipt_record(record)
            if errors:
                return CaseResult("", corpus_case_id, scene_id, partition, expected, True, "invalid", errors)
        errors = check_receipt_sequence(case["stream"])
        observed = "invalid" if errors else "valid"
        return CaseResult("", corpus_case_id, scene_id, partition, expected, True, observed, errors)

    # Single-document cases.
    schema = case["schema"]
    document = case["document"]
    if schema == "attention-receipt" and isinstance(document, dict) and document.get("stage") in (
        "attention", "participant-host", "transport",
    ):
        # 020 owns only the observation stage; a non-observation stage body's
        # content correctness is that stage's own writer's contract (FR-015).
        # 020's adapter validates only the record envelope/writer-binding for
        # these stages (already reflected in validate_attention_receipt_record),
        # so a case whose redness/greenness turns on body content is
        # non-consumed rather than mis-scored against a rule 020 does not own.
        return CaseResult("", corpus_case_id, scene_id, partition, expected, False, None, [])
    consumed, errors = _validate_single(schema, document)
    if not consumed:
        return CaseResult("", corpus_case_id, scene_id, partition, expected, False, None, [])
    errors = list(errors)
    if not errors:
        errors = _relational_errors(partition, case["document"], schema)
    observed = "invalid" if errors else "valid"
    return CaseResult("", corpus_case_id, scene_id, partition, expected, True, observed, errors)


def run_corpus(name: str) -> list[CaseResult]:
    results = []
    for case in load_corpus(name):
        result = evaluate_case(case)
        result.corpus = name
        results.append(result)
    return results


def run_all() -> dict[str, list[CaseResult]]:
    return {name: run_corpus(name) for name in CORPUS_NAMES}


def summarize(results_by_corpus: dict[str, list[CaseResult]]) -> dict[str, Any]:
    all_results = [r for results in results_by_corpus.values() for r in results]
    consumed = [r for r in all_results if r.consumed]
    non_consumed = [r for r in all_results if not r.consumed]
    mismatches = [r for r in consumed if not r.matched]
    by_class = {klass: {"consumed": 0, "non_consumed": 0} for klass in ALL_SEVEN_CLASSES}
    by_class["schema-expressible"] = {"consumed": 0, "non_consumed": 0}
    for r in all_results:
        bucket = by_class.setdefault(r.partition, {"consumed": 0, "non_consumed": 0})
        bucket["consumed" if r.consumed else "non_consumed"] += 1
    return {
        "total_cases": len(all_results),
        "consumed_count": len(consumed),
        "non_consumed_count": len(non_consumed),
        "mismatch_count": len(mismatches),
        "mismatches": [(r.corpus, r.case_id) for r in mismatches],
        "by_class": by_class,
    }
