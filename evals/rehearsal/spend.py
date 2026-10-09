"""The spend watchdog on the OpenRouter key (step 9f, PR 1).

Claude Code and Hermes give client-side cost estimates (``total_cost_usd``,
``estimated_cost_usd``), and Codex token counts only; none of them is what
the key was charged. So the probe reads the key's usage from OpenRouter
(``GET /api/v1/key``) before the first moment, between moments and after
the last, and stops before the next moment once the run has spent
``budget_usd``.

This is a soft limit, and the record says so. OpenRouter's usage figure can
lag behind the calls, a moment already under way runs to its end, and other
runs on the same key (a behavior eval, say) count in the same figure. Only a
key with a credit limit is a hard limit.

Only the numbers are kept from OpenRouter's answer, never its ``label``,
which can show part of the key.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import time
from typing import Any
import urllib.error
import urllib.request

from .routes import KEY_URL

# The numeric fields of OpenRouter's key document worth keeping.
_FIELDS = ("usage", "usage_daily", "usage_weekly", "usage_monthly", "limit", "limit_remaining")
SOFT_LIMIT_NOTE = (
    "soft limit: OpenRouter's usage figure can lag, a moment under way runs to its end, "
    "and other runs on the same key count in the same figure; only a key with a credit limit is a hard limit"
)

NOT_READ = "no key: a scripted run reads no spend"

Opener = Callable[..., Any]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class SpendWatch:
    """Reads the key's usage and says when the run has passed its budget.

    With no key (a scripted run) nothing is read. ``opener`` is
    ``urllib.request.urlopen`` by default; tests pass their own. A failed
    read is recorded and never stops the run by itself.
    """

    def __init__(self, api_key: str | None, budget_usd: float, *, opener: Opener | None = None) -> None:
        if budget_usd <= 0:
            raise ValueError("the budget must be positive")
        self.api_key = api_key
        self.budget_usd = float(budget_usd)
        self.opener = opener or urllib.request.urlopen
        self.readings: list[dict[str, Any]] = []
        self.stopped_before: str | None = None

    def read(self, when: str) -> dict[str, Any]:
        """One reading of the key's usage, named for when it was taken (``before <moment>``)."""

        entry: dict[str, Any] = {"when": when, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if not self.api_key:
            entry["error"] = f"not read: {NOT_READ}"
            self.readings.append(entry)
            return entry
        request = urllib.request.Request(KEY_URL, headers={"Authorization": f"Bearer {self.api_key}"}, method="GET")
        try:
            with self.opener(request, timeout=20) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            entry["error"] = f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            entry["error"] = f"{type(exc).__name__}"
        else:
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                entry["error"] = "the answer has no data"
            else:
                for name in _FIELDS:
                    value = _number(data.get(name))
                    if value is not None:
                        entry[name] = value
                if "usage" not in entry:
                    entry["error"] = "the answer has no usage"
        self.readings.append(entry)
        return entry

    def _first_usage(self) -> float | None:
        for entry in self.readings:
            if "usage" in entry:
                return entry["usage"]
        return None

    def spent(self) -> float | None:
        """What the run has spent so far, from the first and the latest usable readings."""

        first = self._first_usage()
        latest = next((entry["usage"] for entry in reversed(self.readings) if "usage" in entry), None)
        if first is None or latest is None:
            return None
        return round(latest - first, 6)

    def may_continue(self, next_moment: str) -> bool:
        """Read again, and whether the next moment may start: False once the budget is passed."""

        self.read(f"before {next_moment}")
        spent = self.spent()
        if spent is not None and spent >= self.budget_usd:
            self.stopped_before = next_moment
            return False
        return True

    def document(self) -> dict[str, Any]:
        return {
            "budget_usd": self.budget_usd,
            "limit": SOFT_LIMIT_NOTE,
            "read": bool(self.api_key),
            **({} if self.api_key else {"not_read_because": NOT_READ}),
            "url": KEY_URL,
            "readings": list(self.readings),
            "spent_usd": self.spent(),
            "stopped_before": self.stopped_before,
        }
