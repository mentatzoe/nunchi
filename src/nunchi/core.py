"""Internal callable admission core."""

import os

from .classifiers import TEST_RESULT_ENV, classify
from .fastpath import fast_verdict
from .models import result_to_dict
from .schema import validate_request, validate_result

FASTPATH_ENV = "NUNCHI_FASTPATH"


def _fastpath_active() -> bool:
    """Whether the deterministic fast-path should be consulted this call.

    The fast-path is enabled by default but INACTIVE when:
      - ``NUNCHI_CLASSIFIER_TEST_RESULT`` is set — deterministic test/injection
        mode must reach the injected provider result, not be short-circuited; or
      - ``NUNCHI_FASTPATH`` is explicitly ``"0"`` (operator opt-out).
    """
    if os.environ.get(TEST_RESULT_ENV) is not None:
        return False
    if os.environ.get(FASTPATH_ENV) == "0":
        return False
    return True


def evaluate(request, *, classifier: str | None = None, classifier_config: dict | None = None):
    """Evaluate one admission request through the selected classifier path."""

    admission_request = validate_request(request)

    if _fastpath_active():
        shortcut = fast_verdict(admission_request)
        if shortcut is not None:
            validate_result(shortcut)
            return shortcut

    result = classify(admission_request, classifier=classifier, classifier_config=classifier_config)
    payload = result_to_dict(result)
    validate_result(payload)
    return payload
