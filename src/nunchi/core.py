"""Public Nunchi V2 attention API.

There is no V1 request translation or verdict fallback.  Callers supply a
validated participant profile, one delegated attention model, trusted policy,
and the same receipt journal that already contains the observation stage.
"""

from __future__ import annotations

from collections.abc import Mapping
import threading
from typing import Any

from .attention import (
    AttentionEngine,
    AttentionModel,
    AttentionPolicy,
    ParticipantProfile,
)
from .receipts import ReceiptJournal
from .v2_contracts import validate_attention_request


def evaluate(
    request: Mapping[str, Any],
    *,
    profile: ParticipantProfile,
    model: AttentionModel | None,
    policy: AttentionPolicy | None = None,
    receipts: ReceiptJournal,
    cancel: threading.Event | None = None,
) -> dict[str, Any]:
    """Return one I-010B decision for one I-010A request.

    ``model=None`` is valid only when trusted policy disables pre-attention;
    otherwise the operational error branch is returned.  The function never
    invokes a second classifier and never returns V1 PASS/ACK/ASK/SPEAK as the
    social result.
    """
    checked = validate_attention_request(request)
    engine = AttentionEngine(
        profile=profile,
        model=model,
        policy=policy,
        receipts=receipts,
    )
    return engine.judge(checked, cancel=cancel)
