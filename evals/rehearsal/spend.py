"""The spend watchdog on the OpenRouter key (step 9f, PR 1).

Claude Code and Hermes give client-side cost estimates (``total_cost_usd``,
``estimated_cost_usd``), and Codex token counts only; none of them is what
the key was charged. So the probe reads the key's usage from OpenRouter
(``GET /api/v1/key``) before the first moment and between moments, and
stops before the next moment once the run has spent ``budget_usd``. After
the last moment it reads the figure every few seconds up to a bound
(`SpendWatch.settle`), keeps each read, and takes the last figure as the
settled one; charges posted after the bound are missed.

The reading is a record, and a soft limit between moments, never a limit
inside one; the record says so. OpenRouter's usage figure lags behind the
calls: in the first live run (2026-10-09) every reading between moments
read $0 spent, in every job. A moment already under way runs to its end,
and other runs on the same key (a behavior eval, say) count in the same
figure. Only a key with a credit limit is a hard limit.

Only the numbers are kept from OpenRouter's answer, never its ``label``,
which can show part of the key.

A live scene (PR 4d) reads the key as above and also counts the model calls
each column made (`probe.Leg.model_calls`), since the usage figure lags. The
summary shows the cost two ways: **recorded**, the key's usage, and
**estimated**, those counts times `ESTIMATED_USD_PER_CALL` (`estimate_usd`),
which are assumptions that no run has measured yet.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import time
from typing import Any
import urllib.error
import urllib.request

from .routes import KEY_URL

# The numeric fields of OpenRouter's key document worth keeping.
_FIELDS = ("usage", "usage_daily", "usage_weekly", "usage_monthly", "limit", "limit_remaining")
SOFT_LIMIT_NOTE = (
    "a record, and a soft limit between moments, never a limit inside one: OpenRouter's usage figure lags "
    "(the last reading reads it up to a bound and keeps the last figure; charges posted after the bound are "
    "missed), a moment under way runs to its end, and other runs on the same key count in the same figure; "
    "only a key with a credit limit is a hard limit"
)
# How long the reading after the last moment reads the usage figure, and how often.
SETTLE_SECONDS = 75.0
SETTLE_INTERVAL_SECONDS = 5.0
# One read's own timeout; the last moment's reading cuts it to the time left.
READ_TIMEOUT_SECONDS = 20.0
# The first reading is the base of everything the run spent: a transient failure of that one read would leave the run with no
# figure at all, so it is tried again (each try kept), up to this many times, this many seconds apart.
FIRST_READ_TRIES = 3
FIRST_READ_PAUSE_SECONDS = 2.0

NOT_READ = "no key: a scripted run reads no spend"

# What one model call is assumed to cost, in US dollars, for the estimate beside the recorded figure. Nothing here is measured:
# the first live scene run replaces them. How they were chosen (docs/rehearsal.md, Cost):
#   attention: the behavior eval reported $1.92 for eight attention routes over all scenes, three runs each (evals/behavior/README.md,
#     "Which run to use"), about $0.001 a call; doubled for the default model's reasoning tokens and the longer room of a scene.
#   reference: one plain-call turn on the agent's model, a snapshot of the room (about 5,000 tokens in, 200 out) at $1 and $5 per
#     million tokens in and out, which is the default agent model's list price as the workflow's default input has it: about $0.006,
#     rounded up.
#   claude-code, codex: one model request of a harness, its system prompt and tools beside the room (about 18,000 tokens in, 300 out),
#     at the same prices, no cache credit: about $0.02. A turn is two or three requests.
ESTIMATED_USD_PER_CALL = {"attention": 0.002, "reference": 0.01, "claude-code": 0.02, "codex": 0.02}

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
        if not 0 < budget_usd < float("inf"):  # nan and inf compare as neither: a budget that stops nothing is no budget
            raise ValueError("the budget must be a positive, finite number")
        self.api_key = api_key
        self.budget_usd = float(budget_usd)
        self.opener = opener or urllib.request.urlopen
        self.readings: list[dict[str, Any]] = []
        self.stopped_before: str | None = None

    def read(self, when: str) -> dict[str, Any]:
        """One reading of the key's usage, named for when it was taken (``before <moment>``)."""

        entry = self._fetch(when)
        self.readings.append(entry)
        return entry

    first_read_pause = FIRST_READ_PAUSE_SECONDS

    def read_first(self, when: str, *, tries: int = FIRST_READ_TRIES) -> dict[str, Any]:
        """The first reading, tried again while it gives no figure, up to ``tries`` times; every try is kept.

        Without a key nothing is read again. The run's spend is the latest
        figure less the first, so a first read that failed once, and nothing
        else wrong, must not leave the whole run without one.
        """

        entry = self.read(when)
        for _ in range(max(0, tries - 1)):
            if "usage" in entry or not self.api_key:
                break
            time.sleep(self.first_read_pause)
            entry = self.read(f"{when} (again)")
        return entry

    def settle(
        self, when: str, *, wait_seconds: float = SETTLE_SECONDS, interval_seconds: float = SETTLE_INTERVAL_SECONDS
    ) -> dict[str, Any]:
        """The last reading: read the lagging usage figure up to a bound, and keep each read.

        OpenRouter's figure lags behind the calls, so a reading right after the
        last moment can still show nothing of it. This reads at once and then
        every ``interval_seconds`` until the next read would start past
        ``wait_seconds``; each read's timeout is cut to the time left. The
        reading is a record, not a limit, so it never stops early. It keeps
        one entry, the last read that gave a figure (the settled one; the
        last read when none did), with
        ``series``, each read as [seconds after the last moment, usage]
        (None for a failed read), ``waited_seconds`` and
        ``wait_bound_seconds``. Charges posted after the bound are missed;
        the series shows how the figure lagged. With no key (a scripted run)
        nothing is read and nothing waits.
        """

        if not self.api_key:
            return self.read(when)
        started = time.monotonic()
        deadline = started + wait_seconds
        kept: dict[str, Any] = {}
        series: list[list[float | None]] = []
        while True:
            at = round(time.monotonic() - started, 1)
            entry = self._fetch(when, timeout=min(READ_TIMEOUT_SECONDS, max(1.0, deadline - time.monotonic())))
            series.append([at, entry.get("usage")])
            if "usage" in entry or "usage" not in kept:
                kept = entry
            if time.monotonic() + interval_seconds > deadline:
                break
            time.sleep(interval_seconds)
        kept.update(
            {"series": series, "waited_seconds": round(time.monotonic() - started, 1), "wait_bound_seconds": wait_seconds}
        )
        self.readings.append(kept)
        return kept

    def _fetch(self, when: str, *, timeout: float = READ_TIMEOUT_SECONDS) -> dict[str, Any]:
        entry: dict[str, Any] = {"when": when, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if not self.api_key:
            entry["error"] = f"not read: {NOT_READ}"
            return entry
        request = urllib.request.Request(KEY_URL, headers={"Authorization": f"Bearer {self.api_key}"}, method="GET")
        try:
            with self.opener(request, timeout=timeout) as response:
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


def estimate_usd(column: str, calls: Mapping[str, Any] | None) -> float | None:
    """What a column's counted model calls would cost at `ESTIMATED_USD_PER_CALL`; None when they were not counted.

    ``calls`` is ``{"agent": n, "attention": m, ...}`` (`probe.Leg.model_calls`).
    An estimate, not the key's figure: it is the same for any model the run
    names, since it is a guess at how big a call is and what it costs.
    """

    if not isinstance(calls, Mapping) or not all(isinstance(calls.get(name), int) for name in ("agent", "attention")):
        return None
    return round(calls["agent"] * ESTIMATED_USD_PER_CALL.get(column, 0.0) + calls["attention"] * ESTIMATED_USD_PER_CALL["attention"], 4)
