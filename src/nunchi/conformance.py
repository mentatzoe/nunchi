"""Installed deterministic conformance for the shared V2 lifecycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from .attention import AttentionEngine, AttentionPolicy, ParticipantProfile
from .observation import ObservationProvider, ParticipantBinding
from .participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
    TransportResult,
)
from .pipeline import NunchiV2Pipeline
from .receipts import ReceiptJournal


SCENARIOS = {
    "suppress": "participant-bound classifier SUPPRESS with active recovery",
    "wake-contribution": "WAKE followed by one host-owned contribution",
    "wake-silence": "WAKE followed by participant silence",
    "classifier-defer": "direct model DEFER wakes advice-free",
    "margin-defer": "uncertain SUPPRESS becomes audited margin DEFER",
    "bypass": "trusted preattention bypass invokes zero classifier calls",
    "error-fallback": "provider error wakes under explicit default policy",
    "error-no-wake": "provider error does not wake under explicit NO_WAKE policy",
}


class _Model:
    name = "v2-conformance-attention"
    provider = "offline-fixture"
    model_id = "deterministic-v2"

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.calls = 0

    def judge(self, *, projection, **_):
        self.calls += 1
        if self.scenario.startswith("error-"):
            raise RuntimeError("attributable fixture provider failure")
        disposition = {
            "suppress": "SUPPRESS",
            "margin-defer": "SUPPRESS",
            "classifier-defer": "DEFER",
        }.get(self.scenario, "WAKE")
        vector = (
            {"PASS": 0.52, "ACK": 0.1, "ASK": 0.18, "SPEAK": 0.48}
            if self.scenario == "margin-defer"
            else {"PASS": 0.91, "ACK": 0.03, "ASK": 0.02, "SPEAK": 0.04}
        )
        if disposition == "WAKE":
            vector = {"PASS": 0.03, "ACK": 0.12, "ASK": 0.2, "SPEAK": 0.9}
        return {
            "disposition": disposition,
            "reasons": ["offline lifecycle fixture"],
            "evidence_event_ids": [projection["trigger_event_id"]],
            "legacy_verdict_confidences": vector,
        }


class _Transport:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, **_):
        self.calls += 1
        return TransportResult("sent", "offline-conformance")


def run_scenario(scenario: str) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown V2 conformance scenario {scenario!r}")
    binding = ParticipantBinding(
        participant_id="conformance-participant",
        actor_id="discord:actor:9",
        platform="discord",
        room_id="42",
        continuity_scope_id="discord:channel:42",
    )
    profile = ParticipantProfile(
        profile_id="conformance-profile",
        participant_id=binding.participant_id,
        actor_id=binding.actor_id,
        instructions="Participate directly and preserve uncertainty.",
        provenance="conformance:offline",
        sha256="0" * 64,
    )
    model = _Model(scenario)
    policy = AttentionPolicy(
        preattention_enabled=scenario != "bypass",
        error_action="NO_WAKE" if scenario == "error-no-wake" else "WAKE",
    )
    with tempfile.TemporaryDirectory(prefix="nunchi-v2-conformance-") as directory:
        receipts = ReceiptJournal(Path(directory) / "receipts.jsonl")
        observation = ObservationProvider(binding, receipts=receipts)
        scheduler = ConversationOpportunityScheduler("conformance:42")
        transport = _Transport()

        def participant(**_):
            if scenario == "wake-silence":
                return None
            return {
                "kind": "message",
                "origin_event_id": "discord:message:100",
                "text": "Conformance contribution.",
            }

        host = ParticipantTurnHost(
            observation=observation,
            participant=participant,
            transport=transport,
            scheduler=scheduler,
            receipts=receipts,
        )
        pipeline = NunchiV2Pipeline(
            observation=observation,
            attention=AttentionEngine(
                profile=profile,
                model=None if scenario == "bypass" else model,
                policy=policy,
                receipts=receipts,
            ),
            host=host,
            scheduler=scheduler,
        )
        outcome = pipeline.handle_delivery(
            delivery_id="discord:gateway:1:MESSAGE_CREATE:100",
            event={
                "id": "discord:message:100",
                "type": "message",
                "author_id": "discord:actor:7",
                "text": "Room observation",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            },
            actors={"discord:actor:7": {"kind": "human"}},
        )
        opportunity = outcome.opportunities[0]
        stages = [
            record["stage"]
            for record in receipts.records(opportunity.request_id)
        ]
        expected = {
            "suppress": ("SUPPRESS", 0, 0, ["observation", "attention"]),
            "wake-contribution": (
                "WAKE",
                1,
                1,
                ["observation", "attention", "participant-host", "transport"],
            ),
            "wake-silence": (
                "WAKE",
                1,
                0,
                ["observation", "attention", "participant-host"],
            ),
            "classifier-defer": (
                "DEFER",
                1,
                1,
                ["observation", "attention", "participant-host", "transport"],
            ),
            "margin-defer": (
                "DEFER",
                1,
                1,
                ["observation", "attention", "participant-host", "transport"],
            ),
            "bypass": (
                "PREATTENTION_BYPASS",
                1,
                1,
                ["observation", "attention", "participant-host", "transport"],
            ),
            "error-fallback": (
                "ERROR_FALLBACK",
                1,
                1,
                ["observation", "attention", "participant-host", "transport"],
            ),
            "error-no-wake": (
                None,
                0,
                0,
                ["observation", "attention"],
            ),
        }[scenario]
        observed = (
            opportunity.effective_disposition,
            host.invocation_count,
            transport.calls,
            stages,
        )
        return {
            "schema_version": 2,
            "scenario": scenario,
            "status": "pass" if observed == expected else "fail",
            "observed": {
                "effective_disposition": opportunity.effective_disposition,
                "classifier_calls": model.calls,
                "participant_invocations": host.invocation_count,
                "transport_calls": transport.calls,
                "receipt_stages": stages,
            },
            "expected": {
                "effective_disposition": expected[0],
                "participant_invocations": expected[1],
                "transport_calls": expected[2],
                "receipt_stages": expected[3],
            },
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nunchi-conformance")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all")
    parser.add_argument("--format", choices=("text", "jsonl"), default="text")
    args = parser.parse_args(argv)
    if args.list:
        print(f"{len(SCENARIOS)} V2 lifecycle scenario(s):")
        for name, description in SCENARIOS.items():
            print(f"  {name:20s} {description}")
        return 0
    selected = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    results = [run_scenario(name) for name in selected]
    if args.format == "jsonl":
        for result in results:
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        for result in results:
            print(f"{result['status'].upper():4s} {result['scenario']}")
        print(
            f"{sum(item['status'] == 'pass' for item in results)}/"
            f"{len(results)} V2 lifecycle scenarios passed"
        )
    return 0 if all(item["status"] == "pass" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
