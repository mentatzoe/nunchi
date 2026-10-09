"""The rehearsal probe (#94 step 9f, PR 1): routes, scan, record, spend, checks, and each harness's leg.

Everything here is offline. The Claude Code leg runs the real
`ClaudeCodeRoomRuntime` and its session manager against a faked ``claude``
that does what the Nunchi mod does inside a real one (attach, bind, call a
room tool over the gate's socket) and speaks stream-json, as
`nunchi.integrations.claude_code_conformance` fakes the session; its modes
are the failures a pass must never hide (no mod, a failed model call, a turn
past the host's deadline, a post over Discord's limit), with dead attention,
an unattested acknowledgement and an undelivered message beside them. The
scripted probe for Codex and Hermes runs where the pinned installs are
present (``NUNCHI_CODEX_BIN``; Hermes with discord.py in this Python): CI's
Codex and Hermes lanes run this module, and it skips elsewhere.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import tomllib
import unittest
import urllib.error
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

    def test_claude_code_goes_to_openrouter_with_its_key_named_not_valued(self):
        route = routes.claude_code_route(SLUG)
        self.assertEqual("https://openrouter.ai/api", route.env["ANTHROPIC_BASE_URL"])
        self.assertEqual("", route.env["ANTHROPIC_API_KEY"])
        self.assertEqual(("ANTHROPIC_AUTH_TOKEN",), route.secret_env)
        for name in routes.CLAUDE_BACKGROUND_MODEL_ENV:
            self.assertEqual(SLUG, route.env[name])
        with mock.patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": self.SECRET, "NUNCHI_ATTENTION_API_KEY": self.SECRET}):
            self.assertNotIn(self.SECRET, json.dumps(route.describe()))

    def test_the_codex_config_parses_and_names_its_key_variable(self):
        for scripted, base_url in ((False, routes.OPENROUTER), (True, "http://127.0.0.1:5555/v1")):
            with self.subTest(scripted=scripted):
                text = routes.codex_config(SLUG, base_url=base_url, scripted=scripted)
                config = tomllib.loads(text)
                self.assertEqual(SLUG, config["model"])
                self.assertEqual("openrouter", config["model_provider"])
                provider = config["model_providers"]["openrouter"]
                self.assertEqual(base_url, provider["base_url"])
                self.assertEqual("responses", provider["wire_api"])
                self.assertEqual("OPENROUTER_API_KEY", provider["env_key"])
                self.assertIs(False, provider["supports_websockets"])
                self.assertEqual("workspace-write", config["sandbox_mode"])
                self.assertIs(False, config["sandbox_workspace_write"]["network_access"])
                self.assertEqual(scripted, "request_max_retries" in provider)
                self.assertNotIn("sk-", text)

    def test_hermes_runs_every_call_on_the_agents_model(self):
        live = routes.hermes_model_config(SLUG, ["title_generation", "vision"])
        self.assertEqual(
            {"default": SLUG, "provider": "openrouter", "base_url": routes.OPENROUTER, "api_key": ""}, live["model"]
        )
        self.assertEqual({"provider": "openrouter", "model": SLUG}, live["auxiliary"]["title_generation"])
        self.assertEqual({"title_generation", "vision"}, set(live["auxiliary"]))
        scripted = routes.hermes_model_config(SLUG, ["vision"], scripted_base_url="http://127.0.0.1:1/v1")
        self.assertEqual("custom", scripted["model"]["provider"])
        self.assertEqual("http://127.0.0.1:1/v1", scripted["auxiliary"]["vision"]["base_url"])

    def test_the_hermes_section_withholds_the_openrouter_key(self):
        section = routes.hermes_section("1100")
        self.assertEqual("discord", section["platform"])
        self.assertEqual("1100", section["chat_id"])
        self.assertIn("OPENROUTER_API_KEY", section["withheld_env"])
        self.assertIn("DISCORD_BOT_TOKEN", section["withheld_env"])
        from nunchi.integrations.hermes_plugin.plugin import HermesRoute

        self.assertEqual("discord", HermesRoute.from_section(section).platform)

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

    def test_a_clean_user_keeps_only_the_path_locale_network_and_homes(self):
        with tempfile.TemporaryDirectory() as directory:
            homes = routes.Homes(Path(directory)).create()
            inherited = {"PATH": "/bin", "LANG": "C.UTF-8", "GITHUB_TOKEN": "ghp_" + "x" * 36, "HOME": "/home/runner"}
            env = routes.clean_environment(homes, routes.claude_code_route(SLUG), inherited=inherited)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertEqual(homes["HOME"], env["HOME"])
        for name in ("HOME", "TMPDIR", "CODEX_HOME", "HERMES_HOME", "CLAUDE_CONFIG_DIR"):
            self.assertTrue(env[name].startswith(directory), name)
        self.assertEqual("/bin", env["PATH"])

    def test_claude_code_knows_each_slug_by_its_own_model_id(self):
        self.assertEqual(routes.ClaudeModel("claude-haiku-4-5", "default"), routes.claude_code_model(SLUG))
        for slug, model in routes.CLAUDE_CODE_MODELS.items():
            with self.subTest(slug=slug):
                self.assertTrue(slug.startswith("anthropic/claude-"))
                self.assertIn(model.permission_mode, ("default", "auto"))
        with self.assertRaisesRegex(ValueError, "CLAUDE_CODE_MODELS"):
            routes.claude_code_model("openai/gpt-6-luna")

    def test_every_harness_has_its_pin_and_key_name(self):
        for harness in routes.HARNESSES:
            self.assertIn(harness, routes.PINS)
            self.assertIn(harness, routes.HARNESS_KEY_ENV)

    def test_attention_beside_hermes_reads_hermess_own_key_and_no_nunchi_name(self):
        # Hermes runs the plugin in its own process and strips OPENROUTER_API_KEY from the
        # agent's terminal; it would pass a NUNCHI_* name on.
        self.assertEqual("OPENROUTER_API_KEY", routes.attention_key_env("hermes"))
        for harness in ("claude-code", "codex"):
            self.assertEqual("NUNCHI_ATTENTION_API_KEY", routes.attention_key_env(harness))
        config = routes.attention_config("openai/gpt-6-luna@low", api_key_env=routes.attention_key_env("hermes"))
        self.assertEqual("OPENROUTER_API_KEY", config["api_key_env"])
        self.assertIn("OPENROUTER_API_KEY", routes.hermes_section("1100")["withheld_env"])


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

    def test_a_home_snapshot_sees_a_new_or_changed_home(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / ".codex"
            absent = record.home_snapshot(home)
            self.assertFalse(absent["exists"])
            home.mkdir()
            (home / "config.toml").write_text("a")
            first = record.home_snapshot(home)
            self.assertTrue(first["exists"])
            (home / "auth.json").write_text("b")
            self.assertNotEqual(first, record.home_snapshot(home))

    def test_providers_are_found_wherever_a_transcript_names_them(self):
        found = record.served_providers({"choices": [], "provider": "Anthropic", "model": SLUG, "nested": [{"provider": "Google"}]})
        self.assertEqual([{"provider": "Anthropic", "model": SLUG}, {"provider": "Google"}], found)

    def test_the_summary_leads_with_the_truth(self):
        page = record.summary_markdown({"harness": "codex", "mode": "live", "status": "could-not-run", "errors": ["Codex is not installed"]})
        self.assertIn("**Could not run:**", page)
        self.assertIn("Codex is not installed", page)

    def test_a_pass_without_a_delivered_post_says_the_room_tools_were_not_exercised(self):
        quiet = record.summary_markdown({"harness": "claude-code", "mode": "live", "status": "pass", "moments": [
            {"name": "direct-question", "posts": []}]})
        self.assertIn("**Passed, without a room action:**", quiet)
        posted = record.summary_markdown({"harness": "claude-code", "mode": "live", "status": "pass", "moments": [
            {"name": "direct-question", "posts": [{"delivered": True, "text": "On it."}]}]})
        self.assertIn("**Passed:** every hard check held", posted)

    def test_an_arm_is_named_in_the_summarys_title(self):
        page = record.summary_markdown({"harness": "codex", "mode": "live", "arm": "OpenAI-model arm for R3", "status": "pass"})
        self.assertTrue(page.startswith("# Rehearsal probe: codex (live, OpenAI-model arm for R3)\n"))

    def test_a_failed_runs_summary_opens_with_every_reason_and_each_verdict_in_full(self):
        verdict = "blocked on a model route (R3): " + "x" * 700
        run = {
            "harness": "codex",
            "mode": "live",
            "status": "fail",
            "checks": [
                {"name": "pins-and-isolation", "ok": True, "detail": "codex-cli 0.160.1"},
                {"name": "turns-bound-and-ended", "ok": False, "detail": "turn r1 on e1 failed: TurnError: the agent's turn ended"},
                {"name": "attention-judged", "ok": True, "detail": "3 of 3 attention call(s) returned a judgment"},
            ],
            "reports": {"codex": {"verdict": verdict, "room_tool_called": False, "tool_calls": [{"tool": "x"}], "turns": [{"error": "e"}] * 9}},
        }
        head = record.summary_markdown(run).splitlines()[:7]
        self.assertEqual("**Failed:** turns-bound-and-ended did not hold.", head[2])
        self.assertEqual("- **turns-bound-and-ended:** turn r1 on e1 failed: TurnError: the agent's turn ended", head[4])
        self.assertEqual("- Attention: 3 of 3 attention call(s) returned a judgment", head[5])
        self.assertEqual(f"- codex: {verdict}", head[6])
        self.assertIn("- codex.room_tool_called: false", record.summary_markdown(run))

    def test_a_stop_at_the_budget_is_named_among_the_first_reasons(self):
        run = {
            "harness": "hermes",
            "mode": "live",
            "status": "fail",
            "checks": [{"name": "turns-bound-and-ended", "ok": False, "detail": "no wake reached the harness"}],
            "spend": {"budget_usd": 2.0, "stopped_before": "direct-question", "read": True},
        }
        head = record.summary_markdown(run).splitlines()[:6]
        self.assertEqual("- **turns-bound-and-ended:** no wake reached the harness", head[4])
        self.assertEqual("- The spend watchdog stopped the run at the budget before direct-question.", head[5])


class TurnsOnOthersMessagesTest(unittest.TestCase):
    """A turn the agent's own message started fails the run."""

    def test_only_a_turn_on_someone_elses_message_passes(self):
        from evals.rehearsal import checks

        turns = [{"request_id": "r1", "trigger": "e1"}]
        self.assertTrue(checks.turns_on_others_messages(turns, ["e0", "e1"]).ok)
        own = checks.turns_on_others_messages([*turns, {"request_id": "r2", "trigger": "own-post"}], ["e0", "e1"])
        self.assertFalse(own.ok)
        self.assertIn("turn r2 on own-post", own.detail)


class CodexVerdictTest(unittest.TestCase):
    """The Codex verdict names R3 only on evidence of it; any other failure is named as what it is."""

    NAMESPACE = "{\"error\": {\"message\": \"Invalid value: 'namespace'. Supported values are: 'function'.\"}}"

    def _verdict(self, *turns, room_calls=0, wakes=1, tools_offered=None):
        return probe.codex_verdict(room_calls=room_calls, turns=list(turns), wakes=wakes, tools_offered=tools_offered)

    def test_a_room_tool_call_settles_the_route(self):
        self.assertIn("a room tool was called", self._verdict({"status": "completed", "error": None}, room_calls=1))

    def test_only_a_namespace_refusal_or_missing_tools_is_r3(self):
        refused = self._verdict({"status": "failed", "error": self.NAMESPACE})
        self.assertTrue(refused.startswith("blocked on a model route (R3): the provider refused Codex's namespace tools"), refused)
        self.assertIn("Invalid value: 'namespace'", refused)
        named = self._verdict({"status": "failed", "error": "400: tool type namespace is not supported"})
        self.assertTrue(named.startswith("blocked on a model route (R3)"), named)
        missing = self._verdict({"status": "completed", "error": None}, tools_offered=False)
        self.assertEqual("no room tool was called: the room tools were missing from what the model got (R3)", missing)
        for error in (
            "unexpected status 402 Payment Required: Insufficient credits",
            "unexpected status 401 Unauthorized: No auth credentials found",
            "unexpected status 400 Bad Request: Invalid value: 'web_search'",
            # A Linux-namespace error from the sandbox is not the provider refusing the tool type.
            "sandbox setup failed: bwrap: No permissions to create new namespace",
        ):
            with self.subTest(error=error):
                verdict = self._verdict({"status": "failed", "error": error})
                self.assertEqual(f"Codex's turn failed: {error}", verdict)
                self.assertNotIn("R3", verdict)

    def test_a_turn_without_a_room_tool_is_reported_as_that(self):
        silent = self._verdict({"status": "completed", "error": None}, tools_offered=True)
        self.assertEqual("no room tool was called: the turn ended without one", silent)
        self.assertEqual(silent, self._verdict({"status": "completed", "error": None}))
        self.assertIn("did not complete (interrupted)", self._verdict({"status": "interrupted", "error": None}))
        self.assertIn("no end reported", self._verdict(wakes=1))
        self.assertEqual("no turn started", self._verdict(wakes=0))


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
        self.assertEqual([], seen)
        self.assertFalse(watch.document()["read"])


# -- checks -------------------------------------------------------------------------------------------


class ChecksTest(unittest.TestCase):
    BASE = "/tmp/nunchi-rehearsal-x"

    def _pins(self, **changes):
        arguments = dict(
            harness_version="codex-cli 0.160.1",
            expected="0.160.1",
            actual_homes={"HOME": f"{self.BASE}/home", "CODEX_HOME": f"{self.BASE}/codex-home"},
            base=self.BASE,
            user_homes_before=[{"path": "/root/.codex", "exists": False}],
            user_homes_after=[{"path": "/root/.codex", "exists": False}],
        )
        arguments.update(changes)
        return checks.pins_and_isolation(**arguments)

    def test_pins_and_isolation(self):
        self.assertTrue(self._pins().ok)
        self.assertIn("never created", self._pins().detail)
        for change, why in (
            ({"harness_version": "codex-cli 0.161.0"}, "not the pinned"),
            ({"actual_homes": {"HOME": "", "CODEX_HOME": f"{self.BASE}/codex-home"}}, "got no HOME"),
            ({"actual_homes": {"HERMES_HOME": "/root/.hermes"}}, "outside the run's directory"),
            ({"actual_homes": {"HOME": f"{self.BASE}-other/home"}}, "outside the run's directory"),
            ({"actual_homes": {}}, "not read"),
            ({"user_homes_after": [{"path": "/root/.codex", "exists": True, "entries": 1, "listing_sha256": "a"}]}, "created"),
        ):
            with self.subTest(why=why):
                check = self._pins(**change)
                self.assertFalse(check.ok)
                self.assertIn(why, check.detail)
        existing = {"path": "/root/.codex", "exists": True, "entries": 2, "listing_sha256": "a"}
        self.assertTrue(self._pins(user_homes_before=[existing], user_homes_after=[existing]).ok)
        changed = self._pins(user_homes_before=[existing], user_homes_after=[{**existing, "listing_sha256": "b"}])
        self.assertFalse(changed.ok)
        self.assertIn("changed", changed.detail)

    def test_only_the_harnesss_own_key_reaches_its_processes_and_none_its_shell(self):
        harness = {"what": "codex app-server", "env": ["OPENROUTER_API_KEY", "REHEARSAL_CANARY"], "secrets": ["OPENROUTER_API_KEY", "REHEARSAL_CANARY"]}
        shell = {"process": "the agent's terminal", "agent_shell": True, "env": ["REHEARSAL_CANARY"], "secrets": ["REHEARSAL_CANARY"]}
        keys = {"harness_keys": ["OPENROUTER_API_KEY"], "canary": "REHEARSAL_CANARY"}
        passed = self._pins(processes=[harness, shell], **keys)
        self.assertTrue(passed.ok, passed.detail)
        self.assertIn("the agent's shell gets none", passed.detail)
        nunchi = {**harness, "secrets": ["NUNCHI_ATTENTION_API_KEY", "OPENROUTER_API_KEY"]}
        leaky_shell = {**shell, "secrets": ["NUNCHI_ATTENTION_API_KEY", "REHEARSAL_CANARY"]}
        unread = {"process": "the agent's terminal", "agent_shell": True, "error": "ImportError: no tools"}
        for processes, why in (
            ([nunchi], "codex app-server got a key in NUNCHI_ATTENTION_API_KEY"),
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
            "harness_install": {"version": "codex-cli 0.160.1", "executable": "/x/codex"},
            "configs": [{"name": "codex user config", "sha256": "d" * 64}],
            "commands": [{"argv": ["codex"]}],
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
    SECRET = b"o" * 48

    def _client(self):
        return standin.StandInRoomClient(
            participant_id="vigil", room_id="1100", actor_id="discord:actor:9900", secret=self.SECRET, display_name="Vigil"
        )

    def _binding(self):
        return ParticipantBinding(
            participant_id="vigil", actor_id="discord:actor:9900", platform="discord", room_id="1100",
            continuity_scope_id="discord:channel:1100",
        )

    def _registered(self):
        client = self._client()
        connection = DiscordRoomConnection(client=client, binding=self._binding(), secret=self.SECRET, label="t", surface="t")
        connection.register()
        return client, MCPDiscordTransport(client, "1100", "vigil", "discord:actor:9900", self.SECRET)

    def test_registration_gets_the_exact_attestation(self):
        client, _ = self._registered()
        self.assertTrue(client.registered)
        self.assertTrue(client.wire.entries[0]["ok"])
        self.assertEqual("discord:actor:9900", client.wire.entries[0]["answer"]["transport_self_actor_id"])

    def test_a_post_reads_sent_through_the_real_transport_and_echoes_back(self):
        client, transport = self._registered()
        wake = {"request_id": "req-1", "room": {"id": "1100"}}
        result = transport.dispatch(action={"kind": "message", "text": "Ten seconds."}, wake=wake)
        self.assertEqual("sent", result.delivery)
        self.assertEqual([{"kind": "message", "message_id": result.detail.split(":")[-1], "text": "Ten seconds.", "reply_to": None}], client.effects)
        echo = client.take_echoes()
        self.assertEqual("discord:actor:9900", echo[0]["author_id"])
        self.assertEqual([], client.take_echoes())
        self.assertEqual("req-1", client.wire.entries[-1]["request_id"])
        self.assertNotIn("_nunchi_authorization", json.dumps(client.wire.entries))
        reply = transport.dispatch(
            action={"kind": "reply", "target_event_id": "discord:message:5", "text": "Yes."}, wake=wake
        )
        self.assertEqual("sent", reply.delivery)
        self.assertEqual("discord:message:5", client.take_echoes()[0]["reply_to_event_id"])
        reaction = transport.dispatch(
            action={"kind": "reaction", "target_event_id": "discord:message:5", "reaction": "👂", "operation": "add"},
            wake=wake,
        )
        self.assertEqual("sent", reaction.delivery)
        self.assertTrue(transport.reaction_capability().allows("👂"))

    def test_the_transports_own_checks_refuse_what_discord_would(self):
        # The shared transport's ToolExecutor, not a copy: an over-long or empty post, or a
        # reply to a target that is not a snowflake, is refused, and nothing reaches the room.
        client, transport = self._registered()
        wake = {"request_id": "req-2", "room": {"id": "1100"}}
        for action, why in (
            ({"kind": "message", "text": "x" * 2001}, "2000-character limit"),
            ({"kind": "message", "text": "  "}, "non-empty"),
            ({"kind": "reply", "target_event_id": "discord:message:abc", "text": "Yes."}, "snowflake"),
        ):
            with self.subTest(why=why):
                self.assertEqual("failed", transport.dispatch(action=action, wake=wake).delivery)
                self.assertIn(why, client.wire.entries[-1]["refused"])
        self.assertEqual([], client.effects)

    def test_an_acknowledgement_without_the_exact_identity_reads_unknown(self):
        client, transport = self._registered()
        create = standin._StandInDiscord.create_message

        def wrong_author(rest, channel_id, content, *, reply_to_message_id=None):
            message = create(rest, channel_id, content, reply_to_message_id=reply_to_message_id)
            return {**message, "author": {**message["author"], "id": "1"}}

        with mock.patch.object(standin._StandInDiscord, "create_message", wrong_author):
            result = transport.dispatch(action={"kind": "message", "text": "Ten seconds."}, wake={"request_id": "r", "room": {"id": "1100"}})
        self.assertEqual("unknown", result.delivery)

    def test_a_call_without_a_valid_authorization_is_refused(self):
        client = self._client()
        answer = client.call_tool("send_message", {"channel_id": "1100", "content": "hi"})
        self.assertTrue(answer["isError"])
        self.assertIn("not authenticated", client.wire.entries[-1]["refused"])
        client, _ = self._registered()
        other = MCPDiscordTransport(client, "1100", "vigil", "discord:actor:9900", b"x" * 48)
        result = other.dispatch(action={"kind": "message", "text": "hi"}, wake={"request_id": "r", "room": {"id": "1100"}})
        self.assertEqual("failed", result.delivery)
        self.assertIn("MAC", client.wire.entries[-1]["refused"])
        self.assertEqual([], client.effects)

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


FAKE_CLAUDE = r'''#!{python}
"""A faked `claude`: what the Nunchi mod does in a real session, over stream-json and the gate's socket.

A ``mode`` file beside it picks a failure: ``no-mod`` (the mod never loads), ``is-error`` (the model
call fails), ``hang`` (the turn outlives the host's deadline), ``long`` (a post over Discord's limit),
``leak`` (the canary in a post), ``unrecognized`` (Claude Code does not know the model), ``auto`` (the
session starts in auto mode).
"""
import http.client, json, os, re, socket, sys, time
from pathlib import Path
here = Path(__file__).resolve().parent
mode = (here / "mode").read_text().strip() if (here / "mode").exists() else ""
def note(entry):
    with open(here / "record.jsonl", "a") as handle:
        handle.write(json.dumps(entry) + "\n")
if sys.argv[1:2] == ["--version"]:
    print("2.1.289 (Claude Code)")
    sys.exit(0)
argv = sys.argv[1:]
model = argv[argv.index("--model") + 1] if "--model" in argv else "default"
settings = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
note({"argv": argv, "env_names": sorted(os.environ), "cwd": os.getcwd(),
      "auth_token_set": bool(os.environ.get("ANTHROPIC_AUTH_TOKEN")),
      "api_key_empty": os.environ.get("ANTHROPIC_API_KEY") == "",
      "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
      "settings": json.loads(settings.read_text()) if settings.exists() else None})
class Connection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(os.environ["NUNCHI_CLAUDE_CODE_GATE_SOCKET"])
def post(path, body):
    connection = Connection("nunchi-gate", timeout=60)
    connection.request("POST", path, json.dumps(body), {"content-type": "application/json",
                       "x-nunchi-session": os.environ["NUNCHI_CLAUDE_CODE_GATE_SESSION"]})
    answer = json.loads(connection.getresponse().read())
    connection.close()
    return answer
def emit(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()
session = "6f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5"
def result(**fields):
    emit({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
          "result": "Posted my answer.", "total_cost_usd": 0.0, "modelUsage": {model: {}}, **fields})
plugin_dir = argv[argv.index("--plugin-dir") + 1]
if mode == "unrecognized":
    sys.stderr.write('[claude-code:unrecognized_model] {"model":"%s","query_source":"sdk"}\n' % model)
    sys.stderr.flush()
if mode == "no-mod":
    emit({"type": "system", "subtype": "init", "session_id": session, "model": model, "plugins": [],
          "plugin_errors": [{"name": "nunchi", "error": "the plugin failed to load"}], "permissionMode": "default"})
else:
    emit({"type": "system", "subtype": "init", "session_id": session, "model": model,
          "plugins": [{"name": "nunchi", "path": plugin_dir}], "plugin_errors": [],
          "permissionMode": "auto" if mode == "auto" else "default", "apiKeySource": "ANTHROPIC_AUTH_TOKEN"})
    post("/v1/attach", {})
turn = 0
for line in sys.stdin:
    message = json.loads(line)
    if message.get("type") != "user":
        continue
    turn += 1
    if mode == "no-mod":
        # Nothing binds the turn: the model answers in text, which never reaches the room.
        emit({"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": "Ten seconds."}]}})
        result(result="Ten seconds.")
        continue
    text = message["message"]["content"][0]["text"]
    match = re.match(r'<nunchi_wake id="([A-Za-z0-9_-]+)"/>', text)
    turn_id = "fake-turn-%d" % turn
    bound = post("/v1/turn-start", {"turn_id": turn_id, "wake_id": match.group(1) if match else None})
    if mode == "is-error":
        failure = "API Error: 400 anthropic/claude-haiku-4.5 is not a valid model ID"
        result(subtype="error_during_execution", is_error=True, result=failure, errors=[failure], modelUsage={})
        continue
    if mode == "hang":
        time.sleep(12)
    answer = {answer}
    if mode == "long":
        answer = "Ten seconds. " + "x" * 2100
    if mode == "leak":
        answer = "my canary is " + os.environ.get("REHEARSAL_CANARY", "?")
        emit({"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": answer}]}})
    note({"bound": bound, "answer": post("/v1/tool", {"turn_id": turn_id, "tool": "mcp__nunchi__room_send",
                                                       "input": {"text": answer}})})
    emit({"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": "Posted."}]}})
    result()
'''


class _DeadAttention(standin.ScriptedAttention):
    """Attention whose provider answers every call with HTTP 503."""

    def _handler(self):
        from http.server import BaseHTTPRequestHandler

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):  # noqa: N802
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                payload = b'{"error": {"message": "no provider is available", "code": 503}}'
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler


def _wrong_author():
    """The stand-in's Discord acknowledges each post with another author: the library cannot attest it."""

    create = standin._StandInDiscord.create_message

    def create_message(rest, channel_id, content, *, reply_to_message_id=None):
        message = create(rest, channel_id, content, reply_to_message_id=reply_to_message_id)
        return {**message, "author": {**message["author"], "id": "1"}}

    return mock.patch.object(standin._StandInDiscord, "create_message", create_message)


class ClaudeCodeLegTest(unittest.TestCase):
    """The real runtime and session manager, with the claude process faked; each failure fails the run."""

    def _run(self, mode="", *, turn_timeout=60.0, patches=()):
        directory = Path(tempfile.mkdtemp(prefix="nrc-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        bin_dir = directory / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        source = FAKE_CLAUDE.replace("{python}", sys.executable).replace("{answer}", repr(probe.SCRIPTED_ANSWER))
        fake.write_text(source, encoding="utf-8")
        fake.chmod(0o700)
        if mode:
            (bin_dir / "mode").write_text(mode)
        # Scripted attention and placeholder keys; the faked claude stands in for the model.
        options = probe.Options(
            harness="claude-code",
            out=directory / "out",
            scripted=True,
            claude_bin=str(fake),
            turn_timeout_seconds=turn_timeout,
            command=["test"],
        )
        before = dict(os.environ)
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            printed = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            code = probe.run_probe(options)
        self.assertEqual(before, dict(os.environ), "the probe restores this process's environment")
        records = [json.loads(line) for line in (bin_dir / "record.jsonl").read_text().splitlines()]
        return code, directory / "out" / "claude-code", records, printed.getvalue()

    def _failed(self, mode, check, why, **options):
        """A run that fails: exit 1, status fail, and ``check`` failed with ``why`` in summary.md's first lines."""

        code, out, _records, printed = self._run(mode, **options)
        run = json.loads((out / "run.json").read_text())
        self.assertEqual(1, code, printed)
        self.assertEqual("fail", run["status"])
        failed = {item["name"]: item["detail"] for item in run["checks"] if not item["ok"]}
        self.assertIn(check, failed, run["checks"])
        self.assertIn(why, failed[check])
        summary = (out / "summary.md").read_text()
        head = "\n".join(summary.splitlines()[:10])
        self.assertIn("**Failed:**", head)
        self.assertIn(f"- **{check}:**", head)
        self.assertIn(why, head)
        return run, summary, out

    def test_the_leg_binds_posts_once_and_records_what_claude_code_showed(self):
        code, out, records, printed = self._run()
        run = json.loads((out / "run.json").read_text())
        self.assertEqual(0, code, printed)
        self.assertEqual("pass", run["status"])
        self.assertTrue(all(check["ok"] for check in run["checks"]), run["checks"])
        self.assertEqual(
            [
                "pins-and-isolation",
                "record-complete",
                "turns-bound-and-ended",
                "turns-on-others-messages",
                "attention-judged",
                "one-room-action-per-turn",
                "no-leaks",
                "scripted-outcomes",
            ],
            [check["name"] for check in run["checks"]],
        )
        moments = {moment["name"]: moment for moment in run["moments"]}
        self.assertEqual(0, moments["bot-status-report"]["graded_turns"])
        self.assertEqual("fits", moments["bot-status-report"]["outcome"])
        self.assertEqual(
            [{"text": probe.SCRIPTED_ANSWER, "delivery": "sent", "delivered": True}], moments["direct-question"]["posts"]
        )
        self.assertEqual("fits", moments["direct-question"]["outcome"])
        report = run["reports"]["claude_code"]
        self.assertTrue(report["mod_loaded"]["attached_to_the_gate"])
        self.assertEqual(["nunchi"], report["mod_loaded"]["init_plugins"])
        self.assertTrue(report["turn_bound"])
        self.assertTrue(report["model"]["accepted"])
        self.assertIn(SLUG, report["model"]["named_in_transcript"])
        # The session ran as the clean user, with the route and without Nunchi's keys.
        start = next(entry for entry in records if "argv" in entry)
        self.assertEqual(SLUG, start["argv"][start["argv"].index("--model") + 1])
        self.assertIn("--plugin-dir", start["argv"])
        self.assertTrue(start["auth_token_set"])
        self.assertTrue(start["api_key_empty"])
        self.assertEqual("https://openrouter.ai/api", start["base_url"])
        # The README's settings, and the slug mapped to the id Claude Code knows the model by.
        self.assertEqual({**routes.CLAUDE_SETTINGS, "modelOverrides": {"claude-haiku-4-5": SLUG}}, start["settings"])
        self.assertEqual([], report["not_as_configured"])
        self.assertEqual([SLUG], report["model"]["answered_as"])
        for name in ("NUNCHI_ATTENTION_API_KEY", "NUNCHI_REHEARSAL_OUTPUT_KEY", "GITHUB_TOKEN"):
            self.assertNotIn(name, start["env_names"])
        self.assertIn("REHEARSAL_CANARY", start["env_names"])
        self.assertTrue(start["cwd"].startswith(run["isolation"]["work_directory"]))
        self.assertEqual(
            [{"ok": True, "text": "Done: the room accepted this action."}], [entry["answer"] for entry in records if "answer" in entry]
        )
        # The record names the variables each process actually got, and never holds their values.
        environment = run["environment"]
        commands = {command["what"]: command for command in run["commands"]}
        session = commands["the room's Claude Code session, launched by the runtime"]
        self.assertEqual(start["argv"], session["argv"][1:])
        self.assertTrue(set(session["env"]) <= set(start["env_names"]))
        self.assertIn("NUNCHI_CLAUDE_CODE_GATE_SOCKET", session["env"])
        self.assertEqual(["ANTHROPIC_AUTH_TOKEN", "REHEARSAL_CANARY"], session["secrets"])
        for what in ("the harness's version, for the record", "the runtime's version floor (claude_code_version)"):
            self.assertEqual(["ANTHROPIC_AUTH_TOKEN", "REHEARSAL_CANARY"], commands[what]["secrets"])
            self.assertFalse([name for name in commands[what]["env"] if name.startswith("NUNCHI_")])
        self.assertEqual(1, sum(1 for command in run["commands"] if "session" in command["what"]))
        self.assertEqual(["NUNCHI_ATTENTION_API_KEY", "NUNCHI_REHEARSAL_OUTPUT_KEY"], environment["nunchi_process_only"])
        self.assertEqual("NUNCHI_ATTENTION_API_KEY", environment["attention_key"])
        self.assertEqual(
            {"on": True, "detail": "enabled with failIfUnavailable, and the session started", "settings": routes.CLAUDE_SETTINGS["sandbox"]},
            report["sandbox"],
        )
        self.assertTrue((out / "transcript" / "claude-stream.jsonl").exists())
        # turns.json and run.json tell the same turns.
        turns = json.loads((out / "turns.json").read_text())
        self.assertEqual(turns["turns"], [turn for moment in run["moments"] for turn in moment["turns"]])
        self.assertTrue(all(item["delivered"] for item in turns["committed"]))
        summary = (out / "summary.md").read_text()
        self.assertTrue(summary.startswith("# Rehearsal probe: claude-code"))
        head = "\n".join(summary.splitlines()[:8])
        self.assertIn("**Passed:**", head)
        self.assertIn("- Attention: 3 of 3 attention call(s) returned a judgment", head)
        self.assertIn(f"- claude_code: the mod attached and bound the turn, and the model answered as {SLUG}", head)
        self.assertIn("- claude_code sandbox: on (enabled with failIfUnavailable, and the session started)", head)
        result = json.loads((out / "scan.json").read_text())
        self.assertTrue(result["clean"])
        self.assertIn("ANTHROPIC_AUTH_TOKEN", result["variables"])
        self.assertIn("REHEARSAL_CANARY", result["variables"])

    def test_a_model_claude_code_does_not_recognize_fails_the_run(self):
        run, summary, _ = self._failed("unrecognized", "pins-and-isolation", "Claude Code did not recognize the model: [claude-code:unrecognized_model]")
        self.assertIn("the harness did not run as configured", summary)
        self.assertIn("Claude Code did not recognize the model", run["reports"]["claude_code"]["verdict"])

    def test_a_session_in_another_permission_mode_fails_the_run(self):
        run, _, _ = self._failed("auto", "pins-and-isolation", "permission mode 'auto', not 'default'")
        self.assertEqual("auto", run["reports"]["claude_code"]["permission_mode"])

    def test_a_mod_that_never_loads_fails_the_run(self):
        run, summary, _ = self._failed("no-mod", "turns-bound-and-ended", "the mod never attached")
        report = run["reports"]["claude_code"]
        self.assertFalse(report["mod_loaded"]["attached_to_the_gate"])
        self.assertFalse(report["turn_bound"])
        self.assertIn("- claude_code: the mod never attached (plugin errors:", summary)
        self.assertEqual([], run["moments"][1]["posts"])

    def test_a_failed_model_call_fails_the_run(self):
        run, summary, _ = self._failed("is-error", "turns-bound-and-ended", "the agent's turn ended without an answer")
        report = run["reports"]["claude_code"]
        self.assertFalse(report["model"]["accepted"])
        self.assertEqual(["API Error: 400 anthropic/claude-haiku-4.5 is not a valid model ID"], report["results"][0]["errors"])
        self.assertIn("Claude Code ended a turn as error_during_execution: API Error: 400", summary)

    def test_a_turn_past_the_hosts_deadline_fails_the_run(self):
        # The host gives up at its deadline and cancels the turn: that is never the agent's silence.
        run, _, out = self._failed("hang", "turns-bound-and-ended", "cancelled, outlived the host's deadline or failed", turn_timeout=4.0)
        receipts = [json.loads(line) for path in (out / "receipts").glob("*receipts.jsonl") for line in path.read_text().splitlines()]
        host = [receipt["body"]["outcome"] for receipt in receipts if receipt.get("stage") == "participant-host"]
        self.assertEqual(["unknown"], host)
        self.assertEqual([], [receipt for receipt in receipts if receipt.get("stage") == "transport"])
        self.assertEqual("misses", run["moments"][1]["outcome"])

    def test_dead_attention_fails_the_run_and_lists_its_fallback_wakes(self):
        run, summary, _ = self._failed(
            "", "attention-judged", "attention never returned a judgment",
            patches=[mock.patch.object(probe, "ScriptedAttention", _DeadAttention)],
        )
        head = "\n".join(summary.splitlines()[:10])
        self.assertIn("HTTP 503", head)
        self.assertIn("came from the error fallback, not attention's judgment", head)
        bot = run["moments"][0]
        self.assertEqual(["ERROR_FALLBACK"], bot["graded_wake_sources"])
        self.assertIn("woken by attention's error fallback, not its judgment", summary)

    def test_a_post_over_discords_limit_is_refused_and_fails_the_run(self):
        run, _, _ = self._failed("long", "one-room-action-per-turn", "was not delivered: it reads 'failed'")
        self.assertEqual(
            [{"text": "Ten seconds. " + "x" * 2100, "delivery": "failed", "delivered": False}], run["moments"][1]["posts"]
        )
        self.assertEqual("misses", run["moments"][1]["outcome"])

    def test_an_acknowledgement_the_library_cannot_attest_fails_the_run(self):
        run, _, _ = self._failed("", "one-room-action-per-turn", "it reads 'unknown'", patches=[_wrong_author()])
        self.assertEqual("misses", run["moments"][1]["outcome"])

    def test_a_graded_message_that_never_reaches_nunchi_reads_not_delivered(self):
        deliver = probe.SharedTransportLeg.deliver

        def drop_the_bot(leg, raw, at, scene, sequence):
            if raw["id"] != "b1":
                return deliver(leg, raw, at, scene, sequence)
            return {"scene_event": "b1", "event_id": "discord:message:1", "reached_nunchi": False, "observed": False}

        run, summary, _ = self._failed(
            "", "scripted-outcomes", "bot-status-report reads 'not delivered'",
            patches=[mock.patch.object(probe.SharedTransportLeg, "deliver", drop_the_bot)],
        )
        self.assertEqual("not delivered", run["moments"][0]["outcome"])
        self.assertIn("| bot-status-report | no-turn | no | 0 | 0 of 0 | not delivered |", summary)

    def test_a_canary_in_any_output_deletes_the_outputs_and_fails_the_run(self):
        code, out, _records, printed = self._run("leak")
        self.assertEqual(1, code)
        self.assertEqual({"scan.json", "summary.md"}, {path.name for path in out.iterdir()})
        result = json.loads((out / "scan.json").read_text())
        self.assertFalse(result["clean"])
        self.assertIn("REHEARSAL_CANARY", {hit["variable"] for hit in result["hits"]})
        self.assertIn("deleted", (out / "summary.md").read_text())
        self.assertIn("deleted", printed)


class ProbeCommandTest(unittest.TestCase):
    def test_claude_code_has_no_scripted_lane_yet(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as error:
            code = probe.main(["--harness", "claude-code", "--scripted", "--out", directory])
            self.assertEqual([], list(Path(directory).iterdir()))
        self.assertEqual(probe.EXIT_NOT_YET, code)
        self.assertIn("PR 2", error.getvalue())

    def test_a_missing_harness_is_recorded_as_could_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            options = probe.Options(harness="codex", out=Path(directory), scripted=True, codex_bin="/nonexistent/codex", command=["test"])
            with contextlib.redirect_stdout(io.StringIO()):
                code = probe.run_probe(options)
            run = json.loads((Path(directory) / "codex" / "run.json").read_text())
            summary = (Path(directory) / "codex" / "summary.md").read_text()
        self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
        self.assertEqual("could-not-run", run["status"])
        self.assertIn("Codex is not installed", " ".join(run["errors"]))
        self.assertIn("**Could not run:**", summary)

    def test_a_live_run_needs_the_key(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NUNCHI_ATTENTION_API_KEY", None)
            with contextlib.redirect_stdout(io.StringIO()):
                code = probe.run_probe(probe.Options(harness="hermes", out=Path(directory), command=["test"]))
            run = json.loads((Path(directory) / "hermes" / "run.json").read_text())
        self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
        self.assertIn("NUNCHI_ATTENTION_API_KEY is not set", " ".join(run["errors"]))

    def test_a_probe_error_fails_the_run_even_when_every_check_held(self):
        document = {"errors": ["RuntimeError: boom in the second moment"]}
        probe._set_status(document, [checks.Check("no-leaks", True, "")], could_not_run=False, stopped=False)
        self.assertEqual(("fail", probe.EXIT_FAILED), (document["status"], document["exit_code"]))
        document = {"errors": []}
        probe._set_status(document, [checks.Check("no-leaks", False, "x")], could_not_run=False, stopped=True)
        self.assertEqual("fail", document["status"])
        document = {"errors": []}
        probe._set_status(document, [checks.Check("no-leaks", True, "")], could_not_run=False, stopped=True)
        self.assertEqual(("stopped-at-budget", probe.EXIT_BUDGET), (document["status"], document["exit_code"]))

    def test_bad_arguments(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(probe.EXIT_USAGE, probe.main(["--harness", "codex", "--out", directory, "--budget-usd", "0"]))
            self.assertEqual(probe.EXIT_USAGE, probe.main(["--harness", "codex", "--out", directory, "--attention-model", "m@loud"]))
            self.assertEqual(
                probe.EXIT_USAGE, probe.main(["--harness", "codex", "--out", directory, "--attention-model", "responses:m@low"])
            )
            # Claude Code runs only on a slug the probe maps to Claude Code's own model id.
            self.assertEqual(
                probe.EXIT_USAGE, probe.main(["--harness", "claude-code", "--out", directory, "--agent-model", "openai/gpt-6-luna"])
            )
            self.assertEqual([], list(Path(directory).iterdir()))


# -- the scripted probe through the pinned installs -----------------------------------------------------


def _codex_available() -> bool:
    from nunchi.integrations.codex_app_server_conformance import codex_available

    return codex_available()


def _hermes_available() -> bool:
    from nunchi.integrations.hermes_plugin_conformance import discord_available

    return discord_available()


def _scripted(harness: str) -> tuple[int, dict, dict, str]:
    """``python -m evals.rehearsal.probe --harness <harness> --scripted``, as CI runs it, in its own process."""

    directory = tempfile.mkdtemp(prefix="nrs-")
    try:
        env = dict(os.environ)
        # The same Nunchi this test imports: the source tree or the installed wheel.
        env["PYTHONPATH"] = str(Path(nunchi.__file__).resolve().parents[1])
        done = subprocess.run(
            [sys.executable, "-m", "evals.rehearsal.probe", "--harness", harness, "--scripted", "--out", directory],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        run = json.loads((Path(directory) / harness / "run.json").read_text())
        result = json.loads((Path(directory) / harness / "scan.json").read_text())
        return done.returncode, run, result, done.stdout + done.stderr
    finally:
        __import__("shutil").rmtree(directory, ignore_errors=True)


class ScriptedProbeTest(unittest.TestCase):
    """The scripted probe as CI's Codex and Hermes lanes run it: every moment's outcome is a hard check."""

    def _check(self, harness):
        code, run, result, output = _scripted(harness)
        self.assertEqual(0, code, output)
        self.assertEqual("scripted", run["mode"])
        self.assertTrue(all(check["ok"] for check in run["checks"]), run["checks"])
        self.assertEqual("scripted-outcomes", run["checks"][-1]["name"])
        moments = {moment["name"]: moment for moment in run["moments"]}
        # The bot's status report reaches Nunchi, and attention lets it pass.
        self.assertTrue(moments["bot-status-report"]["reached"])
        self.assertEqual(0, moments["bot-status-report"]["graded_turns"])
        self.assertEqual("fits", moments["bot-status-report"]["outcome"])
        self.assertEqual("fits", moments["direct-question"]["outcome"])
        self.assertEqual(1, len(moments["direct-question"]["posts"]))
        post = moments["direct-question"]["posts"][0]
        self.assertEqual(probe.SCRIPTED_ANSWER, post["text"])
        self.assertTrue(post["delivered"])
        self.assertEqual(["WAKE"], moments["direct-question"]["graded_wake_sources"])
        self.assertTrue(result["clean"])
        self.assertFalse(run["spend"]["read"])
        return run

    def _no_nunchi_key_in_a_harness_process(self, run):
        for entry in [*run["commands"], *run["environment"]["processes"]]:
            if entry.get("in_process"):
                continue
            with self.subTest(process=entry.get("what") or entry.get("process")):
                self.assertNotIn("NUNCHI_ATTENTION_API_KEY", entry["env"])
                self.assertNotIn("NUNCHI_REHEARSAL_OUTPUT_KEY", entry["env"])

    @unittest.skipUnless(_codex_available(), "requires the pinned Codex (NUNCHI_CODEX_BIN)")
    def test_codex(self):
        run = self._check("codex")
        report = run["reports"]["codex"]
        self.assertTrue(report["room_tool_called"])
        self.assertTrue(report["scripted_model"]["room_tools_offered_as_namespace"])
        # Every app-server the integration started, with the variables it got.
        commands = {command["what"]: command for command in run["commands"]}
        app = commands["codex app-server, started by the integration"]
        self.assertEqual(["app-server", "--listen", "stdio://"], app["argv"][1:])
        self.assertEqual(["OPENROUTER_API_KEY", "REHEARSAL_CANARY"], app["secrets"])
        bridge = next(command for command in run["commands"] if command["what"].startswith("the room's MCP server"))
        self.assertEqual(["NUNCHI_CODEX_TURN_SESSION", "NUNCHI_CODEX_TURN_SOCKET"], bridge["env"])
        self.assertIn("git init, the agent's working directory", commands)
        self._no_nunchi_key_in_a_harness_process(run)
        self.assertEqual(["NUNCHI_ATTENTION_API_KEY", "NUNCHI_REHEARSAL_OUTPUT_KEY"], run["environment"]["nunchi_process_only"])
        # Whether Codex's sandbox was on, as Codex reported it.
        self.assertEqual("workspaceWrite", report["sandbox"]["policy"]["type"])
        self.assertIn(report["sandbox"]["on"], (True, False))

    @unittest.skipUnless(_hermes_available(), "requires an installed Hermes with discord.py (hermes-agent[messaging])")
    def test_hermes(self):
        run = self._check("hermes")
        report = run["reports"]["hermes"]
        self.assertTrue(report["plugin_loaded"])
        self.assertGreaterEqual(report["model_calls_in_session"], 1)
        # Hermes's final answer is delivered by Hermes itself: it reads unknown, and the room received exactly it.
        self.assertEqual("unknown", run["moments"][1]["posts"][0]["delivery"])
        # The README's peer-agent settings: Hermes hears the CI bot.
        config = next(entry for entry in run["configs"] if entry["name"] == "hermes config.yaml")
        discord = json.loads(config["content"])["discord"]
        self.assertEqual("all", discord["allow_bots"])
        self.assertIs(False, discord["bots_require_inline_mention"])
        # Hermes runs the plugin in this process: attention reads Hermes's own OPENROUTER_API_KEY,
        # no NUNCHI_* key is in the process, and Hermes's own builders give the agent's commands no key.
        environment = run["environment"]
        self.assertEqual("OPENROUTER_API_KEY", environment["attention_key"])
        self.assertEqual([], environment["nunchi_process_only"])
        self._no_nunchi_key_in_a_harness_process(run)
        processes = {entry["process"]: entry for entry in environment["processes"]}
        hermes = processes["Hermes's GatewayRunner and the plugin, in the probe's process"]
        self.assertFalse([name for name in hermes["env"] if name.startswith("NUNCHI_")])
        self.assertEqual(["OPENROUTER_API_KEY", "REHEARSAL_CANARY"], hermes["secrets"])
        shells = [entry for entry in environment["processes"] if entry.get("agent_shell")]
        self.assertEqual(2, len(shells))
        for shell in shells:
            self.assertNotIn("OPENROUTER_API_KEY", shell["env"])
            self.assertEqual(["REHEARSAL_CANARY"], shell["secrets"])
        self.assertEqual({"on": False, "terminal_backend": "local"}, {key: report["sandbox"][key] for key in ("on", "terminal_backend")})


if __name__ == "__main__":
    unittest.main()
