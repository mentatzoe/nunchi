"""Internal callable admission core.

There is deliberately NO deterministic pre-classifier layer here. The room's
baseline (2026-07-10): suppression may be deterministic only where mechanically
provable from the envelope — and the current envelope carries no transport-bound
identity, so nothing qualifies. The former fast-path's mention rule suppressed
the operator's direct correction of an agent (referential mention read as floor
assignment), and its self-echo rule accepted name-equality and text-equality as
proof of self-causation, which they are not (a human repeating "Thanks." is not
the agent's echo). Every admission is judged by the classifier; deterministic
short-circuits may return only when the message contract carries an
adapter-asserted, transport-bound runtime identity (schema-v2).
"""

from .classifiers import classify
from .models import result_to_dict
from .schema import validate_request, validate_result


def evaluate(request, *, classifier: str | None = None, classifier_config: dict | None = None):
    """Evaluate one admission request through the selected classifier path."""

    admission_request = validate_request(request)
    result = classify(admission_request, classifier=classifier, classifier_config=classifier_config)
    payload = result_to_dict(result)
    validate_result(payload)
    return payload
