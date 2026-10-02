"""Regression and in-memory mutation proof for reconstructed deadline fixtures."""
import inspect
import io
from pathlib import Path
import sys
import textwrap
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.v2.test_shared_foundation import AttentionAndHostTests
from nunchi import participant, pipeline

NAMES = (
    "test_host_total_deadline_bounds_native_transport_wait",
    "test_host_total_deadline_spans_attention_participant_and_transport",
)


def run(names):
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output).run(
        unittest.TestSuite(AttentionAndHostTests(name) for name in names)
    )
    return result, output.getvalue()


def mutate(function, module, old, new):
    source = textwrap.dedent(inspect.getsource(function))
    assert old in source
    # Compile into the real globals: module-time patches in fixtures
    # must still be observed by the compiled function.
    source = source.replace(old, new)
    namespace = {}
    exec(compile(source, "<deadline-fixture-mutant>", "exec"), module.__dict__, namespace)
    return namespace[function.__name__]


result, output = run(NAMES * 150)
assert result.wasSuccessful(), output
print(f"candidate: {result.testsRun} fixture executions passed")

restart = mutate(
    pipeline.NunchiV2Pipeline.run_opportunities,
    pipeline,
    "error_wake=self.attention.policy.error_action == \"WAKE\",\n                deadline=deadline,",
    "error_wake=self.attention.policy.error_action == \"WAKE\",\n                deadline=time.monotonic() + self.host.host_timeout_seconds,",
)
with mock.patch.object(pipeline.NunchiV2Pipeline, "run_opportunities", restart):
    result, output = run(NAMES[1:])
    assert len(result.failures) == 1 and not result.errors, output
    assert "'unknown' != 'sent'" in output, output
    print("budget-reset mutant rejected: unknown != sent")

# Both deadline guards must be removed; the post-queue check independently
# blocks a late successful native result.
source = textwrap.dedent(inspect.getsource(participant.ParticipantTurnHost.run))
source = source.replace(
    "remaining = effective_deadline - time.monotonic()\n            if remaining <= 0:",
    "remaining = 0.05\n            if False:",
).replace(
    "if time.monotonic() >= effective_deadline:\n                token.cancel_event.set()",
    "if False:\n                token.cancel_event.set()",
)
namespace = {}
exec(compile(source, "<late-native-mutant>", "exec"), participant.__dict__, namespace)
with mock.patch.object(participant.ParticipantTurnHost, "run", namespace["run"]):
    result, output = run(NAMES)
    assert len(result.failures) == 2 and not result.errors, output
    assert output.count("'unknown' != 'sent'") == 2, output
    print("both native-wait/late-result mutants rejected: unknown != sent")

leaked = [t.name for t in threading.enumerate() if t.name.startswith(("nunchi-transport-", "nunchi-participant-"))]
assert not leaked, leaked
print("no native/participant worker leaks")
