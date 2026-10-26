"""Offline tests for reference rehearsal records, checks and secret scanning.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
import urllib.error
import urllib.request
from unittest import mock

import nunchi
from nunchi.attention import OpenAICompatibleAttentionModel
from nunchi.integrations.discord_participant_transport import MCPDiscordTransport
from nunchi.integrations.discord_room import DiscordRoomConnection
from nunchi.observation import ParticipantBinding

from evals.rehearsal import checks, probe, record, routes, scan, spend, standin

REPO = Path(__file__).resolve().parents[2]
SLUG = "anthropic/claude-haiku-4.5"


# -- routes -------------------------------------------------------------------------------------------


class RoutesTest(unittest.TestCase):
    SECRET = "sk-or-v1-" + "f" * 40


    def test_attention_is_the_chat_route_at_the_requested_effort(self):
        config = routes.attention_config("openai/gpt-6-luna@low")
        self.assertEqual("openai/gpt-6-luna", config["model"])
        self.assertEqual("NUNCHI_ATTENTION_API_KEY", config["api_key_env"])
        self.assertEqual({"effort": "low"}, config["extra_body"]["reasoning"])
        self.assertEqual({"include": True}, config["extra_body"]["usage"])
        self.assertNotIn("reasoning", routes.attention_config("openai/gpt-6-luna")["extra_body"])
        # The behavior eval's labels: the probe builds the chat route only.
        for label in ("openai/gpt-6-luna@loud", "responses:openai/gpt-6-luna@low", "messages:anthropic/claude-haiku-4.5@low"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                routes.attention_config(label)


# -- scan ---------------------------------------------------------------------------------------------


class ScanTest(unittest.TestCase):
    KEY = "sk-or-v1-" + secrets.token_hex(24)
    CANARY = "canary-" + secrets.token_urlsafe(18)

    def _outputs(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return root

    def test_clean_outputs_pass(self):
        root = self._outputs({"run.json": '{"ok": true}', "transcript/a.jsonl": "nothing here\n"})
        result = scan.scan(root, {"KEY": self.KEY, "REHEARSAL_CANARY": self.CANARY})
        self.assertTrue(result["clean"])
        self.assertEqual(2, result["files_scanned"])
        self.assertEqual(["KEY", "REHEARSAL_CANARY"], result["variables"])

    def test_the_raw_key_is_found(self):
        root = self._outputs({"transcript/a.jsonl": f'{{"auth": "Bearer {self.KEY}"}}'})
        result = scan.scan(root, {"KEY": self.KEY})
        self.assertFalse(result["clean"])
        self.assertEqual([{"file": "transcript/a.jsonl", "variable": "KEY", "form": "raw"}], result["hits"])

    def test_the_key_is_found_base64_encoded_at_every_alignment_and_alphabet(self):
        for prefix in (b"", b"a", b"ab", b"abc"):
            for encode in (base64.b64encode, base64.urlsafe_b64encode):
                with self.subTest(prefix=prefix, encode=encode.__name__):
                    blob = encode(prefix + b"Authorization: Bearer " + self.KEY.encode() + b"\r\nmore")
                    root = self._outputs({"blob.txt": b"data=" + blob})
                    result = scan.scan(root, {"KEY": self.KEY})
                    self.assertFalse(result["clean"])
                    self.assertEqual("base64", result["hits"][0]["form"])

    def test_wrapped_split_hex_and_escaped_forms_are_found(self):
        env = f"HOME=/x\nOPENROUTER_API_KEY={self.KEY}\nREHEARSAL_CANARY={self.CANARY}\n".encode()
        encoded = base64.b64encode(env).decode()
        hexed = env.hex()
        half = len(self.KEY) // 2
        cases = {
            # `base64` wraps at 76 columns, and a JSON transcript writes each newline as \n.
            "wrapped base64 in JSON": json.dumps({"output": "\n".join(encoded[i : i + 76] for i in range(0, len(encoded), 76))}),
            "hex in lines (xxd -p)": "\n".join(hexed[i : i + 60] for i in range(0, len(hexed), 60)),
            "upper-case hex in bytes (od)": " ".join(hexed[i : i + 2].upper() for i in range(0, len(hexed), 2)),
            "split by a newline": f"{self.KEY[:half]}\n{self.KEY[half:]} {self.CANARY[:9]} {self.CANARY[9:]}",
            "JSON inside JSON": json.dumps({"result": json.dumps({"text": env.decode()})}),
            "split and JSON-escaped": json.dumps({"r": f"{self.KEY[:half]}\r\n  {self.KEY[half:]}\t{self.CANARY}"}).replace("/", "\\/"),
        }
        for name, text in cases.items():
            with self.subTest(name):
                result = scan.scan(self._outputs({"t.jsonl": text}), {"KEY": self.KEY, "REHEARSAL_CANARY": self.CANARY})
                self.assertEqual({"KEY", "REHEARSAL_CANARY"}, {hit["variable"] for hit in result["hits"]}, result)
        hex_hit = scan.scan(self._outputs({"t": hexed}), {"KEY": self.KEY})["hits"]
        self.assertEqual("hex", hex_hit[0]["form"])

    def test_a_symlink_among_the_outputs_is_not_clean(self):
        root = self._outputs({"run.json": "{}"})
        (root / "link").symlink_to(root / "run.json")
        result = scan.scan(root, {"KEY": self.KEY})
        self.assertFalse(result["clean"])
        self.assertEqual(["link (a symlink)"], result["unreadable"])

    def test_the_canary_is_found(self):
        root = self._outputs({"room.json": f"the agent said {self.CANARY}"})
        result = scan.scan(root, {"KEY": self.KEY, "REHEARSAL_CANARY": self.CANARY})
        self.assertEqual("REHEARSAL_CANARY", result["hits"][0]["variable"])

    def test_an_unreadable_output_is_not_clean(self):
        root = self._outputs({"run.json": "{}"})
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("denied")):
            result = scan.scan(root, {"KEY": self.KEY})
        self.assertFalse(result["clean"])
        self.assertEqual(["run.json"], result["unreadable"])

    def test_a_short_value_is_not_looked_for(self):
        root = self._outputs({"a.txt": "abc"})
        result = scan.scan(root, {"SHORT": "abc"})
        self.assertEqual(["SHORT"], result["skipped_variables"])
        self.assertEqual([], result["variables"])

    def test_the_command_deletes_every_output_after_a_hit(self):
        root = self._outputs({"run.json": "{}", "transcript/x.jsonl": self.CANARY, "receipts/r.jsonl": "{}"})
        with mock.patch.dict(os.environ, {"REHEARSAL_CANARY": self.CANARY, "KEY": self.KEY}):
            with contextlib.redirect_stderr(io.StringIO()):
                code = scan.main(["--out", str(root), "--env", "KEY", "--env", "REHEARSAL_CANARY"])
        self.assertEqual(1, code)
        self.assertEqual({"scan.json", "summary.md"}, {path.name for path in root.iterdir()})
        result = json.loads((root / "scan.json").read_text())
        self.assertFalse(result["clean"])
        # Checked again after deleting: nothing is left but the notice.
        self.assertEqual([], result["left_after_deleting"])
        notice = (root / "summary.md").read_text()
        self.assertIn("REHEARSAL_CANARY", notice)
        self.assertNotIn(self.CANARY, notice + (root / "scan.json").read_text())

    def test_the_command_passes_clean_outputs_and_needs_a_value(self):
        root = self._outputs({"run.json": "{}"})
        with mock.patch.dict(os.environ, {"KEY": self.KEY}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, scan.main(["--out", str(root), "--env", "KEY"]))
        self.assertTrue(json.loads((root / "scan.json").read_text())["clean"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, scan.main(["--out", str(root), "--env", "NOT_SET_ANYWHERE_REHEARSAL"]))
        self.assertTrue((root / "run.json").exists())


# -- record -------------------------------------------------------------------------------------------


class RecordTest(unittest.TestCase):
    def test_a_config_is_recorded_with_its_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "config" / "c.json"
            path.parent.mkdir()
            raw = b'{"api_key_env": "NUNCHI_ATTENTION_API_KEY"}'
            path.write_bytes(raw)
            entry = record.config_entry("c", path, base=base)
        self.assertEqual("config/c.json", entry["path"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
        self.assertEqual(raw.decode(), entry["content"])


    def test_providers_are_found_wherever_a_transcript_names_them(self):
        found = record.served_providers({"choices": [], "provider": "Anthropic", "model": SLUG, "nested": [{"provider": "Google"}]})
        self.assertEqual([{"provider": "Anthropic", "model": SLUG}, {"provider": "Google"}], found)

    def test_the_summary_leads_with_the_truth(self):
        page = record.summary_markdown({"harness": "reference", "mode": "live", "status": "could-not-run", "errors": ["Codex is not installed"]})
        self.assertIn("**Could not run:**", page)
        self.assertIn("Codex is not installed", page)

    def test_a_pass_without_a_delivered_post_says_the_room_tools_were_not_exercised(self):
        quiet = record.summary_markdown({"harness": "reference", "mode": "live", "status": "pass", "moments": [
            {"name": "direct-question", "posts": []}]})
        self.assertIn("**Passed, without a room action:**", quiet)
        posted = record.summary_markdown({"harness": "reference", "mode": "live", "status": "pass", "moments": [
            {"name": "direct-question", "posts": [{"delivered": True, "text": "On it."}]}]})
        self.assertIn("**Passed:** every hard check held", posted)

    def test_an_arm_is_named_in_the_summarys_title(self):
        page = record.summary_markdown({"harness": "reference", "mode": "live", "arm": "OpenAI-model arm for R3", "status": "pass"})
        self.assertTrue(page.startswith("# Rehearsal probe: reference (live, OpenAI-model arm for R3)\n"))

    def test_a_failed_runs_summary_opens_with_every_reason_and_each_verdict_in_full(self):
        verdict = "blocked on a model route (R3): " + "x" * 700
        run = {
            "harness": "reference",
            "mode": "live",
            "status": "fail",
            "checks": [
                {"name": "pins-and-isolation", "ok": True, "detail": "discord.py 2.7.1"},
                {"name": "turns-bound-and-ended", "ok": False, "detail": "turn r1 on e1 failed: TurnError: the agent's turn ended"},
                {"name": "attention-judged", "ok": True, "detail": "3 of 3 attention call(s) returned a judgment"},
            ],
            "reports": {"reference": {"verdict": verdict, "room_tool_called": False, "tool_calls": [{"tool": "x"}], "turns": [{"error": "e"}] * 9}},
        }
        head = record.summary_markdown(run).splitlines()[:7]
        self.assertEqual("**Failed:** turns-bound-and-ended did not hold.", head[2])
        self.assertEqual("- **turns-bound-and-ended:** turn r1 on e1 failed: TurnError: the agent's turn ended", head[4])
        self.assertEqual("- Attention: 3 of 3 attention call(s) returned a judgment", head[5])
        self.assertEqual(f"- reference: {verdict}", head[6])
        self.assertIn("- reference.room_tool_called: false", record.summary_markdown(run))

    def test_a_stop_at_the_budget_is_named_among_the_first_reasons(self):
        run = {
            "harness": "reference",
            "mode": "live",
            "status": "fail",
            "checks": [{"name": "turns-bound-and-ended", "ok": False, "detail": "no wake reached the harness"}],
            "spend": {"budget_usd": 2.0, "stopped_before": "direct-question", "read": True},
        }
        head = record.summary_markdown(run).splitlines()[:6]
        self.assertEqual("- **turns-bound-and-ended:** no wake reached the harness", head[4])
        self.assertEqual("- The spend watchdog stopped the run at the budget before direct-question.", head[5])

    def test_the_spend_says_it_is_a_record_and_how_its_last_reading_settled(self):
        def page(**last):
            reading = {"when": "after the last moment", "usage": 10.06, "waited_seconds": 10.0, "wait_bound_seconds": 10.0,
                       "series": [[0.0, 10.0], [5.0, None], [10.0, 10.06]], **last}
            spend_document = {"budget_usd": 2.0, "limit": spend.SOFT_LIMIT_NOTE, "read": True, "spent_usd": 0.06,
                              "readings": [{"when": "before the first moment", "usage": 10.0}, reading]}
            return record.summary_markdown({"harness": "reference", "mode": "live", "status": "pass", "spend": spend_document})

        self.assertIn("a record, and a soft limit between moments, never a limit inside one", page())
        self.assertIn("charges posted after the bound are missed", spend.SOFT_LIMIT_NOTE)
        self.assertIn(
            "- Last reading, after the last moment: 3 read(s) over 10.0 s, up to the bound of 10.0 s; the settled figure "
            "is the last one read (10.06), and charges posted after the bound are missed\n"
            "- Each read, as seconds after the last moment: usage (the lag shows here): 0.0: 10.0; 5.0: not read; 10.0: 10.06\n",
            page(),
        )
        self.assertIn("the settled figure is the last one read (none: no read gave a figure)", page(usage=None))


class TurnsOnOthersMessagesTest(unittest.TestCase):
    """A turn the agent's own message started fails the run."""

    def test_only_a_turn_on_someone_elses_message_passes(self):
        from evals.rehearsal import checks

        turns = [{"request_id": "r1", "trigger": "e1"}]
        self.assertTrue(checks.turns_on_others_messages(turns, ["e0", "e1"]).ok)
        own = checks.turns_on_others_messages([*turns, {"request_id": "r2", "trigger": "own-post"}], ["e0", "e1"])
        self.assertFalse(own.ok)
        self.assertIn("turn r2 on own-post", own.detail)


# -- spend ---------------------------------------------------------------------------------------------


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SpendTest(unittest.TestCase):
    KEY = "sk-or-v1-" + "s" * 40

    def _opener(self, usages):
        seen = []

        def opener(request, timeout):
            seen.append(request)
            usage = usages.pop(0)
            if isinstance(usage, Exception):
                raise usage
            body = {"data": {"usage": usage, "limit": None, "limit_remaining": None, "label": "sk-or-v1-abc...xyz"}}
            return _Answer(json.dumps(body).encode())

        return opener, seen

    def test_the_watchdog_stops_before_the_next_moment_once_the_budget_is_passed(self):
        opener, seen = self._opener([10.0, 11.5, 12.25])
        watch = spend.SpendWatch(self.KEY, 2.0, opener=opener)
        watch.read("before the first moment")
        self.assertTrue(watch.may_continue("moment 2"))
        self.assertFalse(watch.may_continue("moment 3"))
        self.assertEqual("moment 3", watch.stopped_before)
        self.assertEqual(2.25, watch.spent())
        document = watch.document()
        self.assertIn("soft limit", document["limit"])
        self.assertNotIn("sk-or-v1-abc", json.dumps(document))
        self.assertNotIn(self.KEY, json.dumps(document))
        self.assertEqual(f"Bearer {self.KEY}", seen[0].get_header("Authorization"))
        self.assertEqual("https://openrouter.ai/api/v1/key", seen[0].full_url)

    def test_a_failed_reading_is_recorded_and_never_stops_the_run(self):
        error = urllib.error.HTTPError(routes.KEY_URL, 401, "no", {}, None)
        opener, _ = self._opener([error, OSError("down")])
        watch = spend.SpendWatch(self.KEY, 2.0, opener=opener)
        watch.read("before")
        self.assertTrue(watch.may_continue("next"))
        self.assertEqual(["HTTP 401", "OSError"], [entry["error"] for entry in watch.readings])
        self.assertIsNone(watch.spent())

    def test_a_scripted_run_reads_nothing(self):
        opener, seen = self._opener([1.0])
        watch = spend.SpendWatch(None, 2.0, opener=opener)
        watch.read("before")
        self.assertTrue(watch.may_continue("next"))
        watch.settle("after the last moment", wait_seconds=60, interval_seconds=30)
        self.assertEqual([], seen)
        self.assertFalse(watch.document()["read"])
        self.assertNotIn("series", watch.readings[-1])

    def _settle(self, usages, *, read_seconds=0.0, **wait):
        """Read before the first moment and before the direct question, then the last reading, on a fake clock.

        Each read takes ``read_seconds``; the clock moves only by reads and sleeps.
        """

        clock = _Clock()
        opener, seen = self._opener(list(usages))
        timeouts = []

        def timed(request, timeout):
            timeouts.append(timeout)
            clock.sleep(read_seconds)
            return opener(request, timeout)

        watch = spend.SpendWatch(self.KEY, 2.0, opener=timed)
        with mock.patch.object(spend, "time", clock):
            watch.read("before the first moment")
            self.assertTrue(watch.may_continue("direct-question"))
            entry = watch.settle("after the last moment", **wait)
        return watch, entry, seen, timeouts

    def test_the_last_reading_reads_up_to_the_bound_and_settles_on_the_last_figure(self):
        # As in the first live run, nothing shows between moments. The first moment's charges post
        # 10 s after the last moment and the agent turn's 25 s after: the wait never stops on the first.
        later = [10.0, 10.0, 10.004, 10.004, 10.004] + [10.06] * 11
        watch, entry, seen, _ = self._settle([10.0, 10.0, *later])
        self.assertEqual(2 + 16, len(seen))
        self.assertEqual([[5.0 * index, usage] for index, usage in enumerate(later)], entry["series"])
        self.assertEqual((10.06, 75.0, 75.0), (entry["usage"], entry["waited_seconds"], entry["wait_bound_seconds"]))
        for gone in ("moved", "held", "compared_with"):
            self.assertNotIn(gone, entry)
        # One entry for the last reading, and the run's spend is read from it.
        self.assertEqual(["before the first moment", "before direct-question", "after the last moment"], [r["when"] for r in watch.readings])
        self.assertEqual(0.06, watch.spent())
        document = watch.document()
        self.assertEqual(0.06, document["spent_usd"])
        self.assertIn("a record, and a soft limit between moments, never a limit inside one", document["limit"])
        self.assertIn("charges posted after the bound are missed", document["limit"])

    def test_a_failed_read_is_in_the_series_and_the_settled_figure_is_the_last_one_read(self):
        watch, entry, _, _ = self._settle([10.0, 10.0, 10.0, 10.25, OSError("down")], wait_seconds=10)
        self.assertEqual([[0.0, 10.0], [5.0, 10.25], [10.0, None]], entry["series"])
        self.assertEqual(10.25, entry["usage"])
        self.assertNotIn("error", entry)
        self.assertEqual(0.25, watch.spent())
        # No read gives a figure: the entry is the last failed read, and nothing is spent by the record.
        error = urllib.error.HTTPError(routes.KEY_URL, 401, "no", {}, None)
        watch, entry, _, _ = self._settle([OSError("down"), OSError("down"), OSError("down"), error], wait_seconds=5)
        self.assertEqual(([[0.0, None], [5.0, None]], "HTTP 401"), (entry["series"], entry["error"]))
        self.assertIsNone(watch.spent())

    def test_no_read_starts_past_the_bound_and_each_is_cut_to_the_time_left(self):
        # Each read takes 2 s: reads start at 0 and 7 s; one at 14 s would start past the 12 s bound.
        watch, entry, seen, timeouts = self._settle([3.0, 3.0, 3.0, 3.5], read_seconds=2.0, wait_seconds=12)
        self.assertEqual([[0.0, 3.0], [7.0, 3.5]], entry["series"])
        self.assertEqual(9.0, entry["waited_seconds"])
        # Between moments a read may take its full timeout; in the bounded wait, only the time left (1 s at least).
        self.assertEqual([spend.READ_TIMEOUT_SECONDS, spend.READ_TIMEOUT_SECONDS, 12.0, 5.0], timeouts)
        self.assertEqual(0.5, watch.spent())
        _, entry, _, timeouts = self._settle([3.0, 3.0, 3.0, 3.0], read_seconds=4.5, wait_seconds=10, interval_seconds=1.0)
        self.assertEqual([[0.0, 3.0], [5.5, 3.0]], entry["series"])
        self.assertEqual([10.0, 4.5], timeouts[2:])


class _Clock:
    """A clock for the spend watch: time moves only when something sleeps."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    strftime = staticmethod(time.strftime)
    gmtime = staticmethod(time.gmtime)


# -- checks -------------------------------------------------------------------------------------------


class ChecksTest(unittest.TestCase):
    BASE = "/tmp/nunchi-rehearsal-x"

    def _pins(self, **changes):
        arguments = dict(
            harness_version="discord.py 2.7.1",
            expected="2.7.1",
            actual_homes={"HOME": f"{self.BASE}/home", "XDG_CONFIG_HOME": f"{self.BASE}/reference-home"},
            base=self.BASE,
            user_homes_before=[{"path": "/root/.reference", "exists": False}],
            user_homes_after=[{"path": "/root/.reference", "exists": False}],
        )
        arguments.update(changes)
        return checks.pins_and_isolation(**arguments)

    def test_pins_and_isolation(self):
        self.assertTrue(self._pins().ok)
        self.assertIn("never created", self._pins().detail)
        for change, why in (
            ({"harness_version": "discord.py 2.8.0"}, "not the pinned"),
            ({"actual_homes": {"HOME": "", "XDG_CONFIG_HOME": f"{self.BASE}/reference-home"}}, "got no HOME"),
            ({"actual_homes": {"XDG_CONFIG_HOME": "/root/.reference"}}, "outside the run's directory"),
            ({"actual_homes": {"HOME": f"{self.BASE}-other/home"}}, "outside the run's directory"),
            ({"actual_homes": {}}, "not read"),
            ({"user_homes_after": [{"path": "/root/.reference", "exists": True, "entries": 1, "listing_sha256": "a"}]}, "created"),
        ):
            with self.subTest(why=why):
                check = self._pins(**change)
                self.assertFalse(check.ok)
                self.assertIn(why, check.detail)
        existing = {"path": "/root/.reference", "exists": True, "entries": 2, "listing_sha256": "a"}
        self.assertTrue(self._pins(user_homes_before=[existing], user_homes_after=[existing]).ok)
        changed = self._pins(user_homes_before=[existing], user_homes_after=[{**existing, "listing_sha256": "b"}])
        self.assertFalse(changed.ok)
        self.assertIn("changed", changed.detail)

    def test_only_the_harnesss_own_key_reaches_its_processes_and_none_its_shell(self):
        harness = {"what": "reference app-server", "env": ["OPENROUTER_API_KEY", "REHEARSAL_CANARY"], "secrets": ["OPENROUTER_API_KEY", "REHEARSAL_CANARY"]}
        shell = {"process": "the agent's terminal", "agent_shell": True, "env": ["REHEARSAL_CANARY"], "secrets": ["REHEARSAL_CANARY"]}
        keys = {"harness_keys": ["OPENROUTER_API_KEY"], "canary": "REHEARSAL_CANARY"}
        passed = self._pins(processes=[harness, shell], **keys)
        self.assertTrue(passed.ok, passed.detail)
        self.assertIn("the agent's shell gets none", passed.detail)
        nunchi = {**harness, "secrets": ["NUNCHI_ATTENTION_API_KEY", "OPENROUTER_API_KEY"]}
        leaky_shell = {**shell, "secrets": ["NUNCHI_ATTENTION_API_KEY", "REHEARSAL_CANARY"]}
        unread = {"process": "the agent's terminal", "agent_shell": True, "error": "ImportError: no tools"}
        for processes, why in (
            ([nunchi], "reference app-server got a key in NUNCHI_ATTENTION_API_KEY"),
            ([harness, leaky_shell], "the agent's terminal got a key in NUNCHI_ATTENTION_API_KEY"),
            ([{**shell, "secrets": ["OPENROUTER_API_KEY"]}], "the agent's terminal got a key in OPENROUTER_API_KEY"),
            ([unread], "could not be read"),
        ):
            with self.subTest(why=why):
                check = self._pins(processes=processes, **keys)
                self.assertFalse(check.ok)
                self.assertIn(why, check.detail)

    def _document(self):
        return {
            "commit": {"sha": "a" * 40},
            "nunchi": {"version": "2.0.0", "wheel": {"file": "n.whl", "sha256": "b" * 64}},
            "harness_install": {"version": "discord.py 2.7.1", "executable": "/x/reference"},
            "configs": [{"name": "reference user config", "sha256": "d" * 64}],
            "commands": [{"argv": ["reference"]}],
            "moments": [{"name": "direct-question"}],
        }

    def test_record_complete(self):
        self.assertTrue(checks.record_complete(self._document(), require_wheel=True).ok)
        missing = self._document()
        del missing["commands"]
        self.assertIn("commands", checks.record_complete(missing, require_wheel=True).detail)
        no_wheel = self._document()
        no_wheel["nunchi"] = {"version": "2.0.0"}
        self.assertFalse(checks.record_complete(no_wheel, require_wheel=True).ok)
        self.assertTrue(checks.record_complete(no_wheel, require_wheel=False).ok)
        unhashed = self._document()
        unhashed["configs"] = [{"name": "x"}]
        self.assertFalse(checks.record_complete(unhashed, require_wheel=True).ok)

    BOUND = {"request_id": "r1", "trigger": "e1", "bound": True, "result": {"kind": "message", "text": "On it."}}
    HANDED = [{"request_id": "r1", "kind": "message", "text": "On it.", "delivery": "sent"}]

    @staticmethod
    def _host(request_id, outcome):
        return {"request_id": request_id, "stage": "participant-host", "body": {"invoked": True, "outcome": outcome}}

    def test_a_turn_bound_and_ended_with_the_harnesss_own_result_passes(self):
        silent = {"request_id": "r2", "trigger": "e2", "bound": True, "result": {"kind": "silence"}}
        receipts = [self._host("r1", "unknown"), self._host("r2", "silent")]
        check = checks.turns_bound_and_ended([self.BOUND, silent], receipts, self.HANDED)
        self.assertTrue(check.ok, check.detail)
        self.assertIn("2 turn(s)", check.detail)

    def test_a_named_failure_fails_with_its_name(self):
        # The mod never loaded, or the model call failed: the harness did not take the turn.
        named = {"request_id": "r2", "trigger": "e2", "bound": False, "error": "ClaudeCodeGateError: the mod never attached"}
        check = checks.turns_bound_and_ended([named], [self._host("r2", "unknown")], [])
        self.assertFalse(check.ok)
        self.assertIn("failed: ClaudeCodeGateError: the mod never attached", check.detail)
        self.assertIn("without a name", checks.turns_bound_and_ended([{**named, "error": " "}], [], []).detail)

    def test_a_turn_the_harness_ended_in_error_after_its_post_fails(self):
        # The post settled the turn's outcome, so only the harness's own result shows the failed call.
        receipts = [self._host("r1", "unknown")]
        self.assertTrue(checks.turns_bound_and_ended([self.BOUND], receipts, self.HANDED).ok)
        failure = "Claude Code ended a turn with an error result (subtype success, is_error true): API Error: 400 broken"
        check = checks.turns_bound_and_ended([self.BOUND], receipts, self.HANDED, harness_failures=[failure])
        self.assertFalse(check.ok)
        self.assertEqual(failure, check.detail)

    def test_a_cancelled_or_timed_out_turn_fails_whatever_the_probe_recorded(self):
        # The host's receipt wins: "unknown" with nothing handed to the room is no silence.
        cancelled = {"request_id": "r5", "trigger": "e5", "bound": True, "result": {"kind": "silence"}}
        check = checks.turns_bound_and_ended([cancelled], [self._host("r5", "unknown")], [])
        self.assertFalse(check.ok)
        self.assertIn("cancelled, outlived the host's deadline or failed", check.detail)
        running = {"request_id": "r6", "trigger": "e6", "bound": True}
        self.assertIn("never ended", checks.turns_bound_and_ended([running], [self._host("r6", "unknown")], []).detail)

    def test_a_turn_the_host_and_the_probe_disagree_on_fails(self):
        unbound = {"request_id": "r3", "trigger": "e3", "bound": False, "result": {"kind": "silence"}}
        self.assertIn("without being bound", checks.turns_bound_and_ended([unbound], [self._host("r3", "silent")], []).detail)
        self.assertIn("recorded no outcome", checks.turns_bound_and_ended([self.BOUND], [], self.HANDED).detail)
        posted = checks.turns_bound_and_ended([self.BOUND], [self._host("r1", "silent")], self.HANDED)
        self.assertIn("recorded a silence", posted.detail)
        unseen = checks.turns_bound_and_ended([self.BOUND], [self._host("r1", "unknown"), self._host("r9", "silent")], self.HANDED)
        self.assertIn("the probe saw no turn", unseen.detail)

    def test_a_run_without_a_turn_fails(self):
        check = checks.turns_bound_and_ended([], [], [])
        self.assertFalse(check.ok)
        self.assertIn("did not show it reaching its model", check.detail)

    def test_attention_must_judge_and_its_failures_are_listed(self):
        ok = {"trigger": "e1", "served": {"model": "m"}}
        down = {"trigger": "e2", "error": "AttentionError: attention provider returned HTTP 400"}
        fallback = {"request_id": "r2", "trigger": "e2", "source": "ERROR_FALLBACK"}
        some = checks.attention_judged([ok, down], [fallback])
        self.assertTrue(some.ok)
        self.assertIn("1 of 2 attention call(s) returned a judgment", some.detail)
        self.assertIn("HTTP 400", some.detail)
        self.assertIn("1 wake(s) came from the error fallback", some.detail)
        none = checks.attention_judged([down, down], [fallback])
        self.assertFalse(none.ok)
        self.assertTrue(none.detail.startswith("attention never returned a judgment"))
        self.assertFalse(checks.attention_judged([], []).ok)

    def test_one_room_action_per_turn_each_delivered(self):
        post = {"request_id": "r1", "kind": "message", "text": "On it.", "delivery": "sent"}
        self.assertTrue(checks.one_room_action_per_turn([post], [True]).ok)
        twice = checks.one_room_action_per_turn([post, {**post, "text": "Again."}], [True, True])
        self.assertFalse(twice.ok)
        self.assertIn("2 room actions", twice.detail)
        refused = {**post, "delivery": "failed", "detail": "Discord MCP tool failed"}
        check = checks.one_room_action_per_turn([refused], [False])
        self.assertFalse(check.ok)
        self.assertIn("was not delivered: it reads 'failed' (Discord MCP tool failed)", check.detail)

    def test_an_action_is_delivered_when_sent_or_when_the_harness_posted_exactly_it(self):
        sent = {"kind": "message", "text": "A", "delivery": "sent"}
        unknown = {"kind": "message", "text": "B", "delivery": "unknown"}
        room = [{"kind": "message", "text": "B"}]
        self.assertEqual([True, False], checks.delivered([sent, unknown], room, harness_posts=False))
        self.assertEqual([True, True], checks.delivered([sent, unknown], room, harness_posts=True))
        # Each message in the room matches one answer at most; a changed text matches none.
        self.assertEqual([True, False], checks.delivered([unknown, unknown], room, harness_posts=True))
        self.assertEqual([False], checks.delivered([{**unknown, "text": "B!"}], room, harness_posts=True))

    def test_the_room_gets_only_what_was_committed(self):
        post = {"request_id": "r1", "kind": "message", "text": "On it."}
        shown = {"kind": "message", "text": "On it."}
        self.assertTrue(checks.no_leaks([post], [shown], ["r1"]).ok)
        stray = checks.no_leaks([post], [shown, {"kind": "message", "text": "Your request was not processed"}], ["r1"])
        self.assertFalse(stray.ok)
        self.assertIn("never committed", stray.detail)
        from nunchi.turn_conformance import KnownGap

        gap = KnownGap("candidate gap 7", scenarios=(checks.PROBE_SCENARIO,), kind="message", text="Your request was not processed")
        declared = checks.no_leaks([post], [shown, {"kind": "message", "text": "Your request was not processed."}], ["r1"], known_gaps=[gap])
        # A declared gap is named, and reads as a gap, never as a pass.
        self.assertFalse(declared.ok)
        self.assertIn("declared gap, a message: 'Your request was not processed.': candidate gap 7", declared.detail)
        self.assertNotIn("never committed", declared.detail)

    def test_no_committed_post_names_the_machinery(self):
        clean = [{"request_id": "r1", "kind": "message", "text": "Ten seconds is a sensible default."}]
        self.assertTrue(checks.no_leaks(clean, [], ["r1", "room_send"]).ok)
        for text in ('<nunchi_wake id="abcdefghijklmnopqr"/> hi', "I used room_send for that", "see request r1-xyz r1"):
            with self.subTest(text=text):
                self.assertFalse(checks.no_leaks([{**clean[0], "text": text}], [], ["r1", "room_send"]).ok)

    def test_a_moments_outcome_is_reported_against_what_it_expects(self):
        outcome = checks.moment_outcome
        self.assertEqual("fits", outcome("post", reached=True, graded_turns=1, delivered_posts=1))
        self.assertEqual("misses", outcome("post", reached=True, graded_turns=1, delivered_posts=0))
        self.assertEqual("fits", outcome("no-turn", reached=True, graded_turns=0, delivered_posts=0))
        self.assertEqual("misses", outcome("no-turn", reached=True, graded_turns=1, delivered_posts=0))
        # A graded message that never reached Nunchi tested nothing.
        self.assertEqual("not delivered", outcome("no-turn", reached=False, graded_turns=0, delivered_posts=0))

    def test_scripted_outcomes(self):
        bot = {"name": "bot-status-report", "outcome": "fits", "other_turns": 0, "posts": []}
        question = {"name": "direct-question", "outcome": "fits", "other_turns": 0, "posts": [{"text": "A"}]}
        self.assertTrue(checks.scripted_outcomes([bot, question], "A", room_tool_called=True).ok)
        for moments, called, why in (
            ([{**bot, "outcome": "not delivered"}, question], None, "reads 'not delivered'"),
            ([bot, {**question, "outcome": "misses", "posts": []}], None, "reads 'misses'"),
            ([{**bot, "other_turns": 2}, question], None, "2 turn(s) on other messages"),
            ([bot, {**question, "posts": [{"text": "B"}]}], None, "not the scripted answer"),
            ([bot, question], False, "no room tool was called"),
            ([], None, "no moment was played"),
        ):
            with self.subTest(why=why):
                check = checks.scripted_outcomes(moments, "A", room_tool_called=called)
                self.assertFalse(check.ok)
                self.assertIn(why, check.detail)


# -- stand-ins ----------------------------------------------------------------------------------------


class StandInTest(unittest.TestCase):
    def test_scripted_attention_wakes_only_for_its_phrase(self):
        attention = standin.ScriptedAttention(["sensible default timeout"])
        self.addCleanup(attention.close)
        model = OpenAICompatibleAttentionModel(model="m", api_key="placeholder-key-123", base_url=attention.base_url)

        def judge(text):
            projection = {"trigger_event_id": "e1", "events": [{"id": "e1", "text": text}]}
            return model.judge(instructions="i", projection=projection, timeout_seconds=10)

        self.assertGreater(judge("what's a sensible default timeout?")["move"]["speak"], 0.5)
        self.assertGreater(judge("Build #482 passed")["move"]["stay_quiet"], 0.5)
        self.assertEqual(["WAKE", "SUPPRESS"], [item["disposition"] for item in attention.judged])
        self.assertEqual("scripted", model.last_response["provider"])


# -- the Claude Code leg, with a faked claude ------------------------------------------------------
