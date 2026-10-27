"""Obsolete: tests the design under architecture review, in which Nunchi runs the agent's turn and sends for it. Not a requirement for the new design.

A reaction is exactly one emoji, and a word is refused before anything is committed.

Run 38135715452: on the fourth message of a story the agent nodded with the
reaction "yikes". The react tool asked for "for example one emoji", the core
committed the word, the room refused it, and the turn's one room action was
spent on a nod that never landed. The rule lives once in the core
(`nunchi.reactions.is_one_emoji`) and every way a participant acts is held to
it: a tool turn (`Turn.call`, over the local socket too), the one-reply style
(`ParticipantTurnProtocol.consume`), and a plain participant the host runs
(`ParticipantTurnHost`). Each refuses before anything is committed and, where
the agent can try again, says so. The reference adapters still take everything
the rule passes.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import threading
import unittest
from unittest import mock
import urllib.parse

from nunchi.adapters.matrix import MatrixTransport
from nunchi.adapters.telegram import TelegramTransport
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient
from nunchi.mcp_discord.tools import ToolExecutor
from nunchi.participant import TransportResult
from nunchi.participant_model import (
    PARTICIPANT_ACTION_SCHEMA,
    PARTICIPANT_TOOL_SPECS,
    REACTION_ADVICE,
    ParticipantModelError,
    ParticipantTurnProtocol,
    ReactionRefused,
    participant_tool_action,
    participant_tool_turn_prompt,
)
from nunchi.reactions import REACTION_RULE, THUMBS_UP, is_one_emoji, reaction_refusal
from nunchi.turn import SecretGuard, TurnParticipant
from tests.v2.turn_fixtures import OPPORTUNITY, PROFILE, test_wake
from tests.v2.test_participant_tool_turn import VISIBLE, _request
from tests.v2.test_shared_foundation import CapturingParticipant, MhmTests, RecordingTransport, FixtureModel, foundation, message
from tests.v2.test_turn import NAMES, RecordingDriver, Room

# What the rule passes: one emoji of every shape a room takes.
ONE_EMOJI = {
    "an emoji": "\N{THUMBS UP SIGN}",
    "an emoji with a skin tone": "\N{THUMBS UP SIGN}\N{EMOJI MODIFIER FITZPATRICK TYPE-4}",
    "a skin tone alone": "\N{EMOJI MODIFIER FITZPATRICK TYPE-4}",
    "a symbol with the emoji style mark": "\N{HEAVY BLACK HEART}️",
    "a symbol without it": "\N{HEAVY BLACK HEART}",
    "a hand with the mark and a skin tone": "\N{WHITE UP POINTING INDEX}️\N{EMOJI MODIFIER FITZPATRICK TYPE-3}",
    "a joined family": "\N{MAN}‍\N{WOMAN}‍\N{GIRL}‍\N{BOY}",
    "a joined person with a skin tone": "\N{ADULT}\N{EMOJI MODIFIER FITZPATRICK TYPE-4}‍\N{PERSONAL COMPUTER}",
    "a joined flag": "\N{WAVING WHITE FLAG}️‍\N{RAINBOW}",
    "a joined heart on fire": "\N{HEAVY BLACK HEART}️‍\N{FIRE}",
    "a joined eye in a speech bubble": "\N{EYE}️‍\N{LEFT SPEECH BUBBLE}️",
    "a country flag": "\N{REGIONAL INDICATOR SYMBOL LETTER U}\N{REGIONAL INDICATOR SYMBOL LETTER S}",
    "a regional indicator letter": "\N{REGIONAL INDICATOR SYMBOL LETTER U}",
    "a subdivision flag": "\N{WAVING BLACK FLAG}" + "".join(chr(0xE0000 + ord(c)) for c in "gbeng") + "\U000e007f",
    "a keycap digit": "1️⃣",
    "a keycap number sign": "#️⃣",
    "a keycap asterisk": "*️⃣",
    "a keycap without the style mark": "0⃣",
    "the keycap ten": "\N{KEYCAP TEN}",
    "a punctuation emoji": "\N{DOUBLE EXCLAMATION MARK}️",
    "an information emoji": "\N{INFORMATION SOURCE}️",
    "an arrow emoji": "\N{LEFT RIGHT ARROW}️",
    "a square emoji": "\N{WHITE MEDIUM SQUARE}️",
    "a wavy dash emoji": "\N{WAVY DASH}️",
    "a copyright sign": "\N{COPYRIGHT SIGN}️",
    # Unassigned in Unicode 16.0, inside the emoji blocks: where the emoji of a later version land.
    "an emoji newer than the tables": "\U0001faff",
    "an emoji newer than the tables, with a style mark": "\U0001faf9\ufe0f",
}
# What it refuses: the word that spent a turn, codes, more than one, and the bits of an emoji alone.
NOT_ONE_EMOJI = {
    "the word that spent a turn": "yikes",
    "a short word": "ok",
    "a letter": "x",
    "a word with a space": "thumbs up",
    "a :name: code": ":thumbsup:",
    "a :+1: code": ":+1:",
    "plus one": "+1",
    "a digit": "1",
    "a number": "10",
    "a number sign": "#",
    "an asterisk": "*",
    "a punctuation mark": "!",
    "a non-ASCII letter": "é",
    "a letter of another script": "あ",
    "a Cyrillic letter": "я",
    "nothing": "",
    "a space": " ",
    "two emoji": "\N{THUMBS UP SIGN}\N{THUMBS UP SIGN}",
    "two emoji of a kind": "\N{HEAVY BLACK HEART}️\N{HEAVY BLACK HEART}️",
    "two flags": "\N{REGIONAL INDICATOR SYMBOL LETTER U}\N{REGIONAL INDICATOR SYMBOL LETTER S}"
    "\N{REGIONAL INDICATOR SYMBOL LETTER F}\N{REGIONAL INDICATOR SYMBOL LETTER R}",
    "three regional indicators": "\N{REGIONAL INDICATOR SYMBOL LETTER U}\N{REGIONAL INDICATOR SYMBOL LETTER S}"
    "\N{REGIONAL INDICATOR SYMBOL LETTER F}",
    "two keycaps": "1️⃣1️⃣",
    "an emoji and a word": "\N{THUMBS UP SIGN}yikes",
    "a word and an emoji": "yikes\N{THUMBS UP SIGN}",
    "an emoji and a space": "\N{THUMBS UP SIGN} ",
    "an emoji and a newline": "\N{THUMBS UP SIGN}\n",
    "a space and an emoji": " \N{THUMBS UP SIGN}",
    "a join with nothing after it": "\N{THUMBS UP SIGN}‍",
    "a join with nothing before it": "‍\N{THUMBS UP SIGN}",
    "a joiner alone": "‍",
    "a style mark alone": "️",
    "a keycap mark alone": "⃣",
    "a keycap mark on an emoji": "\N{THUMBS UP SIGN}⃣",
    "a subdivision flag with no cancel tag": "\N{WAVING BLACK FLAG}" + "".join(chr(0xE0000 + ord(c)) for c in "gbeng"),
    "a black flag and a cancel tag": "\N{WAVING BLACK FLAG}\U000e007f",
    # What a platform refuses though it is one symbol: not an emoji (Emoji=No), however it is classed as a symbol.
    "a check mark": "\u2713",
    "a star": "\u2605",
    "a degree sign": "\u00b0",
    "a musical note": "\u266a",
    "a place of interest sign": "\u2318",
    "a braille pattern": "\u2800",
    "a circled letter": "\u24d0",
    "a dingbat arrow": "\u279c",
    "a chess piece": "\U0001fa00",
    "an alchemical symbol": "\U0001f700",
    # Joined or tagged though neither is an emoji.
    "two thumbs joined": "\N{THUMBS UP SIGN}\u200d\N{THUMBS UP SIGN}",
    "a face joined to a thumb": "\N{GRINNING FACE}\u200d\N{THUMBS UP SIGN}",
    "five parts joined": "\N{MAN}\u200d\N{WOMAN}\u200d\N{GIRL}\u200d\N{BOY}\u200d\N{BOY}",
    "two skin tones": "\N{EMOJI MODIFIER FITZPATRICK TYPE-4}\N{EMOJI MODIFIER FITZPATRICK TYPE-4}",
    "a skin tone and a style mark": "\N{EMOJI MODIFIER FITZPATRICK TYPE-4}\ufe0f",
    "a skin tone on a face": "\N{GRINNING FACE}\N{EMOJI MODIFIER FITZPATRICK TYPE-4}",
    "a skin tone on a sign": "\N{HEAVY BLACK HEART}\N{EMOJI MODIFIER FITZPATRICK TYPE-4}",
    "a word in tag characters after a black flag": "\N{WAVING BLACK FLAG}" + "".join(chr(0xE0000 + ord(c)) for c in "yikes") + "\U000e007f",
    "a subdivision flag RGI has not": "\N{WAVING BLACK FLAG}" + "".join(chr(0xE0000 + ord(c)) for c in "usca") + "\U000e007f",
    "a pair of regional indicators that is no flag": "\N{REGIONAL INDICATOR SYMBOL LETTER A}\N{REGIONAL INDICATOR SYMBOL LETTER A}",
    "a number": 5,
    "None": None,
    "a list": ["\N{THUMBS UP SIGN}"],
}


class OneEmojiRuleTests(unittest.TestCase):
    def test_every_shape_of_one_emoji_passes(self):
        for what, reaction in ONE_EMOJI.items():
            with self.subTest(what):
                self.assertTrue(is_one_emoji(reaction), [hex(ord(c)) for c in reaction])
                self.assertIsNone(reaction_refusal(reaction))

    def test_words_codes_pieces_and_more_than_one_are_refused(self):
        for what, reaction in NOT_ONE_EMOJI.items():
            with self.subTest(what):
                self.assertFalse(is_one_emoji(reaction), repr(reaction))
                self.assertEqual(REACTION_RULE, reaction_refusal(reaction))

    def test_every_emoji_of_unicode_16_0_passes_whatever_python_runs_the_test(self):
        # The 3,790 RGI sequences (tests/v2/data/rgi-emoji.json says how they were made): the rule's tables are its own,
        # so the answer is the same on every Python, whatever Unicode version its `unicodedata` knows.
        found = json.loads((Path(__file__).parent / "data" / "rgi-emoji.json").read_text(encoding="utf-8"))
        self.assertEqual(("16.0", 3790), (found["unicode"], found["count"]))
        self.assertEqual(3790, len(set(found["emoji"])))
        refused = [" ".join(f"{ord(c):X}" for c in emoji) for emoji in found["emoji"] if not is_one_emoji(emoji)]
        self.assertEqual([], refused[:10], f"{len(refused)} of 3790 refused")

    def test_the_rule_reads_no_unicode_table_of_the_pythons_own(self):
        from nunchi import reactions

        # A code point is judged by the rule's tables and not by what this interpreter's `unicodedata` calls it (a symbol,
        # a letter, unassigned), which differs from one Python to the next.
        self.assertNotIn("unicodedata", vars(reactions))
        self.assertTrue(is_one_emoji("\U0001faff"))
        self.assertFalse(is_one_emoji("\u2713"))

    def test_what_passes_alone_is_exactly_the_emoji_and_the_places_for_later_ones(self):
        from nunchi import reactions

        accepted = [code for code in range(0x80, 0x110000) if not 0xD800 <= code <= 0xDFFF and is_one_emoji(chr(code))]
        emoji = sum(last - first + 1 for first, last in reactions._EMOJI)
        later = sum(last - first + 1 for first, last in reactions._UNASSIGNED_IN_EMOJI_BLOCKS)
        self.assertEqual(emoji + later, len(accepted))
        self.assertLess(len(accepted), 1500, "a rule by symbol category let 5,706 non-emoji through")

    def test_the_refusal_says_what_a_reaction_is(self):
        self.assertIn("exactly one emoji", REACTION_RULE)
        self.assertIn(THUMBS_UP, REACTION_RULE)
        self.assertIn("A word", REACTION_RULE)
        self.assertIn(":name: code", REACTION_RULE)

    def test_the_react_tool_asks_for_exactly_one_emoji_and_says_a_word_is_not_a_reaction(self):
        spec = PARTICIPANT_TOOL_SPECS["react"]
        field = spec["input_schema"]["properties"]["reaction"]["description"]
        for text in (spec["description"], field):
            with self.subTest(text[:40]):
                self.assertIn("one emoji", text)
                self.assertIn("a word is not a reaction", text.lower())
        self.assertIn("exactly", spec["description"])
        self.assertIn("a thumbs up", spec["description"])
        self.assertIn(THUMBS_UP, field)
        self.assertNotIn("for example one emoji", spec["description"] + field)
        prompt = participant_tool_turn_prompt(PROFILE, tools={"react": "room.react", "quiet": "room.quiet"})
        self.assertIn("The reaction is exactly one emoji; a word is not a reaction.", prompt)
        # The one-reply style is told the same, in its schema and its instructions.
        reaction = next(
            item for item in PARTICIPANT_ACTION_SCHEMA["properties"]["action"]["oneOf"] if item["properties"]["kind"] == {"const": "reaction"}
        )
        self.assertIn("one emoji", reaction["properties"]["reaction"]["description"])
        protocol = ParticipantTurnProtocol(profile=PROFILE, wake=test_wake(), opportunity=deepcopy(OPPORTUNITY))
        self.assertIn("reaction (exactly one emoji; a word is not a reaction)", protocol.instructions)


class EveryAdapterTakesWhatTheRulePassesTests(unittest.TestCase):
    """The platform calls that turn a reaction into a request leave nothing the rule passes out."""

    def test_the_discord_tool_and_its_rest_call_carry_every_one_of_them_whole(self):
        urls = []

        def http(method, url, headers, body):
            urls.append((method, url))
            return (204, {}, b"")

        rest = DiscordRestClient("test-token", http=http, sleeper=lambda _seconds: None)
        executor = ToolExecutor(rest, SendBackstop(500, 10), authorizer=mock.Mock())
        for what, reaction in ONE_EMOJI.items():
            with self.subTest(what):
                urls.clear()
                payload, ok = executor._reaction({"channel_id": "42", "message_id": "101", "reaction": reaction}, remove=False)
                self.assertTrue(ok, payload)
                self.assertEqual(reaction, payload["reaction"]["reaction"])
                (method, url), = urls
                self.assertEqual("PUT", method)
                sent = url.rsplit("/reactions/", 1)[1].removesuffix("/@me")
                self.assertEqual(reaction, urllib.parse.unquote(sent))

    def test_the_discord_library_the_reference_posts_with_carries_every_one_of_them_whole(self):
        try:
            from discord.message import convert_emoji_reaction
        except ImportError:
            self.skipTest("discord.py is not installed")
        for what, reaction in ONE_EMOJI.items():
            with self.subTest(what):
                self.assertEqual(reaction, urllib.parse.unquote(convert_emoji_reaction(reaction)))

    def test_the_matrix_transport_sends_every_one_of_them_as_the_annotation_key(self):
        with mock.patch.dict(os.environ, {"REF_MATRIX_TOKEN": "held-matrix-access-token"}):
            transport = MatrixTransport(
                {"homeserver": "https://matrix.example", "access_token_env": "REF_MATRIX_TOKEN"},
                room_id="!room:example",
                actor_id="matrix:actor:@vigil:example",
            )
        sent = []

        def request(method, path, payload=None):
            sent.append((method, path, deepcopy(payload)))
            return {"event_id": "$native"}

        transport._request = request
        wake = {"room": {"id": "!room:example"}}
        for what, reaction in ONE_EMOJI.items():
            with self.subTest(what):
                sent.clear()
                action = {
                    "kind": "reaction", "origin_event_id": "matrix:event:$1", "target_event_id": "matrix:event:$1",
                    "reaction": reaction, "operation": "add",
                }
                self.assertEqual("sent", transport.dispatch(action=action, wake=wake).delivery)
                self.assertEqual(reaction, sent[0][2]["m.relates_to"]["key"])
                self.assertEqual("m.annotation", sent[0][2]["m.relates_to"]["rel_type"])

    def test_the_telegram_reference_adapter_makes_no_reaction_call_so_it_has_nothing_to_refuse(self):
        with mock.patch.dict(os.environ, {"REF_TELEGRAM_TOKEN": "987654321:held-telegram-token-value-0123456789"}):
            transport = TelegramTransport({"bot_token_env": "REF_TELEGRAM_TOKEN"})
        self.assertFalse(transport.reaction_capability().supported)
        self.assertEqual(("message", "reply"), transport.ordinary_action_capabilities())
        transport._call = mock.Mock(side_effect=AssertionError("no native call is made for a reaction"))
        action = {
            "kind": "reaction", "origin_event_id": "telegram:message:1:1", "target_event_id": "telegram:message:1:1",
            "reaction": THUMBS_UP, "operation": "add",
        }
        result = transport.dispatch(action=action, wake={"room": {"id": "1"}})
        self.assertEqual("unavailable", result.delivery)


class TheStandInHoldsTheCoresRuleTests(unittest.TestCase):
    """The Discord stand-in (tests/support/fake_discord) refuses what the core refuses and nothing more.

    One stricter than the core would lose the nod of a live run (the core commits, the stand-in refuses) and read it as the
    agent's fault: on Python 3.12 the old approximation refused 12 RGI emoji that Unicode 15.1 added.
    """

    def test_it_takes_every_emoji_of_unicode_16_0_and_every_shape_the_core_takes_and_refuses_the_rest(self):
        from tests.support.fake_discord.world import emoji_ok

        found = json.loads((Path(__file__).parent / "data" / "rgi-emoji.json").read_text(encoding="utf-8"))
        self.assertEqual([], [emoji for emoji in found["emoji"] if not emoji_ok(emoji)])
        for reactions in (ONE_EMOJI.values(), (value for value in NOT_ONE_EMOJI.values() if isinstance(value, str))):
            for reaction in reactions:
                self.assertEqual(is_one_emoji(reaction), emoji_ok(reaction), repr(reaction))
        self.assertFalse(emoji_ok("blob:123456789012345678"), "a custom emoji: the world has none")


class EveryTurnPathRefusesBeforeCommitTests(unittest.TestCase):
    def test_the_tool_action_refuses_a_word_for_an_add_and_a_remove_and_takes_an_emoji(self):
        for operation in ("add", "remove"):
            with self.subTest(operation), self.assertRaises(ReactionRefused) as raised:
                participant_tool_action(
                    "react", {"target_event_id": "e1", "reaction": "yikes", "operation": operation},
                    request=_request(), visible_event_ids=set(VISIBLE),
                )
            self.assertEqual(REACTION_RULE, str(raised.exception))
            self.assertIsInstance(raised.exception, ParticipantModelError)
        for reaction in ("\N{THUMBS UP SIGN}", "\N{WHITE UP POINTING INDEX}️\N{EMOJI MODIFIER FITZPATRICK TYPE-3}"):
            action = participant_tool_action(
                "react", {"target_event_id": "e1", "reaction": reaction}, request=_request(), visible_event_ids=set(VISIBLE)
            )
            self.assertEqual((reaction, "add"), (action["reaction"], action["operation"]))

    def test_a_malformed_call_is_refused_for_its_own_reason_before_the_word_is(self):
        for arguments, reason in (
            ({"target_event_id": "e1", "reaction": "yikes", "operation": "toggle"}, "add or remove"),
            ({"target_event_id": "e404", "reaction": THUMBS_UP}, "absent from supplied facts"),
            ({"target_event_id": "e404", "reaction": "yikes"}, "absent from supplied facts"),
        ):
            with self.subTest(arguments), self.assertRaises(ParticipantModelError) as raised:
                participant_tool_action("react", arguments, request=_request(), visible_event_ids=set(VISIBLE))
            self.assertIn(reason, str(raised.exception))
            self.assertNotIsInstance(raised.exception, ReactionRefused)

    def test_a_turn_that_may_not_react_is_told_that_and_not_to_react_again_with_an_emoji(self):
        request = _request(ordinary=("message", "reply"))
        for reaction in ("yikes", THUMBS_UP, "", None):
            with self.subTest(reaction=reaction), self.assertRaises(ParticipantModelError) as raised:
                participant_tool_action(
                    "react", {"target_event_id": "e1", "reaction": reaction}, request=request, visible_event_ids=set(VISIBLE)
                )
            self.assertIn("exceeds current ordinary permissions", str(raised.exception))
            self.assertNotIsInstance(raised.exception, ReactionRefused)

    def test_a_missing_or_empty_reaction_is_a_word_that_is_no_emoji_not_an_error_nobody_can_read(self):
        for arguments in ({"target_event_id": "e1"}, {"target_event_id": "e1", "reaction": ""}, {"target_event_id": "e1", "reaction": None}):
            with self.subTest(arguments), self.assertRaises(ReactionRefused):
                participant_tool_action("react", arguments, request=_request(), visible_event_ids=set(VISIBLE))


class ToolTurnTests(unittest.TestCase):
    """A tool turn: the refusal is the tool's answer, the turn is still open, and the nod that follows is committed."""

    def setUp(self):
        self.driver = RecordingDriver()
        self.room = Room()
        self.participant = TurnParticipant(
            profile=PROFILE, driver=self.driver, guard=SecretGuard(()), tool_names=NAMES, result_wait_seconds=5
        )
        self.cancel = threading.Event()
        self.box = {}

        def run():
            try:
                self.box["action"] = self.participant.run_protocol(
                    wake=test_wake(), opportunity=deepcopy(OPPORTUNITY), expand=self.room.expand, cancel=self.cancel
                )
            except BaseException as exc:  # noqa: BLE001 - recorded for assertions
                self.box["error"] = exc

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.assertTrue(self.driver.started_event.wait(5))
        self.turn = self.driver.started[0]
        self.assertTrue(self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id))
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.cancel.set)

    def nod(self, reaction, **extra):
        answer = {}
        thread = threading.Thread(
            target=lambda: answer.setdefault(
                "value",
                self.participant.call_tool(
                    turn_id="t1", tool="emoji", arguments={"target_event_id": "e1", "reaction": reaction, **extra}
                ),
            ),
            daemon=True,
        )
        thread.start()
        return thread, answer

    def test_a_word_is_refused_with_a_tool_error_and_the_turn_is_not_spent(self):
        ok, text = self.participant.call_tool(
            turn_id="t1", tool="emoji", arguments={"target_event_id": "e1", "reaction": "yikes"}
        )
        self.assertFalse(ok)
        self.assertIn("exactly one emoji", text)
        self.assertIn(REACTION_ADVICE, text)
        self.assertIn("not spent", text)
        # Nothing was committed: no action, no look before posting, the turn is open and not quiet.
        self.assertIsNone(self.turn.action)
        self.assertFalse(self.turn.action_ready.is_set())
        self.assertFalse(self.turn.looked_again)
        self.assertFalse(self.turn.quieted)
        self.assertTrue(self.turn.open())
        self.assertEqual({}, self.box)

    def test_the_agent_can_then_nod_properly_and_that_is_its_one_room_action(self):
        self.assertFalse(self.participant.call_tool(turn_id="t1", tool="emoji", arguments={"target_event_id": "e1", "reaction": "yikes"})[0])
        thread, answer = self.nod("\N{THUMBS UP SIGN}")
        self.assertTrue(self.turn.action_ready.wait(5))
        self.participant.settle(self.turn.request_id, TransportResult("sent", "native:1"))
        thread.join(5)
        self.assertTrue(answer["value"][0], answer)
        self.thread.join(5)
        self.assertEqual(
            {"kind": "reaction", "origin_event_id": "e1", "target_event_id": "e1", "reaction": "\N{THUMBS UP SIGN}", "operation": "add"},
            self.box["action"],
        )
        # And only the one: a second call is refused for that, not for its reaction.
        self.assertEqual(
            (False, "You already took your one room action in this turn. End your turn."),
            self.participant.call_tool(turn_id="t1", tool="emoji", arguments={"target_event_id": "e1", "reaction": "yikes"}),
        )

    def test_the_agent_can_stay_quiet_or_speak_after_a_refused_word(self):
        self.assertFalse(self.participant.call_tool(turn_id="t1", tool="emoji", arguments={"target_event_id": "e1", "reaction": ":+1:"})[0])
        # Staying quiet: it ends its turn without another call, and says why.
        self.assertTrue(self.participant.end_turn(turn_id="t1", ok=True, detail="done", note="Nothing of mine to add."))
        self.thread.join(5)
        self.assertEqual({"action": {"kind": "silence", "why": "Nothing of mine to add."}}, self.box)

    def test_the_agent_can_speak_instead_after_a_refused_word(self):
        self.assertFalse(self.participant.call_tool(turn_id="t1", tool="emoji", arguments={"target_event_id": "e1", "reaction": "yikes"})[0])
        answer = {}
        thread = threading.Thread(
            target=lambda: answer.setdefault("value", self.participant.call_tool(turn_id="t1", tool="say", arguments={"text": "Yikes, that is a lot."})),
            daemon=True,
        )
        thread.start()
        self.assertTrue(self.turn.action_ready.wait(5))
        self.participant.settle(self.turn.request_id, TransportResult("sent", "native:1"))
        thread.join(5)
        self.assertTrue(answer["value"][0], answer)
        self.assertEqual("message", self.turn.action["kind"])

    def test_a_missing_or_empty_reaction_or_target_is_refused_with_a_tool_error_too(self):
        # `_nonempty` raised a ValidationError that `Turn.call` did not catch: over the socket the connection dropped.
        for arguments in (
            {"target_event_id": "e1"},
            {"target_event_id": "e1", "reaction": ""},
            {"target_event_id": "e1", "reaction": None},
            {"reaction": THUMBS_UP},
            {"target_event_id": "", "reaction": THUMBS_UP},
        ):
            with self.subTest(arguments):
                ok, text = self.participant.call_tool(turn_id="t1", tool="emoji", arguments=arguments)
                self.assertFalse(ok)
                self.assertTrue(text.startswith("Refused: "), text)
                self.assertIsNone(self.turn.action)
                self.assertTrue(self.turn.open())

    def test_it_is_the_same_over_the_local_socket(self):
        import tempfile
        from pathlib import Path

        from nunchi.turn_server import TurnServer
        from tests.v2.turn_fixtures import gate_post

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path, secret = Path(directory.name) / "turns" / "turn.sock", "a-launch-secret-for-this-test"
        server = TurnServer(self.participant, socket_path=path, session_secret=secret)
        server.start()
        self.addCleanup(server.close)
        status, body = gate_post(path, "/v1/tool", {"turn_id": "t1", "tool": "emoji", "input": {"target_event_id": "e1", "reaction": "yikes"}}, secret)
        self.assertEqual(200, status)
        self.assertFalse(body["ok"])
        self.assertIn("exactly one emoji", body["error"])
        self.assertIsNone(self.turn.action)
        # An empty or missing reaction or target answers the same way, and the connection is not dropped.
        for arguments in ({"target_event_id": "e1"}, {"target_event_id": "e1", "reaction": ""}, {"reaction": THUMBS_UP}):
            with self.subTest(arguments):
                status, body = gate_post(path, "/v1/tool", {"turn_id": "t1", "tool": "emoji", "input": arguments}, secret)
                self.assertEqual((200, False), (status, body["ok"]))
                self.assertTrue(body["error"].startswith("Refused: "), body)
        self.assertIsNone(self.turn.action)


class OneReplyTests(unittest.TestCase):
    """The one-reply style: the model is told once, its turn is not spent, and a second word fails the turn."""

    def protocol(self):
        return ParticipantTurnProtocol(profile=PROFILE, wake=test_wake(), opportunity=deepcopy(OPPORTUNITY))

    @staticmethod
    def reply(protocol, reaction, operation="add"):
        return {
            "protocol": protocol.request["protocol"],
            "binding": {"request_id": protocol.request_id},
            "action": {
                "kind": "reaction", "origin_event_id": "e1", "target_event_id": "e1",
                "reaction": reaction, "operation": operation,
            },
        }

    def test_a_word_is_shown_the_refusal_and_the_model_answers_again_with_an_emoji(self):
        protocol = self.protocol()
        self.assertEqual((False, None), protocol.consume(self.reply(protocol, "yikes"), expand=None))
        note = protocol.pages[-1]["note"]
        self.assertIn("exactly one emoji", note)
        self.assertIn(REACTION_ADVICE, note)
        self.assertIsNone(protocol.turn.action, "nothing was committed")
        self.assertEqual(note, protocol.input_document["context_pages"][-1]["note"])
        done, action = protocol.consume(self.reply(protocol, "\N{THUMBS UP SIGN}"), expand=None)
        self.assertTrue(done)
        self.assertEqual("\N{THUMBS UP SIGN}", action["reaction"])
        self.assertEqual(action, protocol.turn.action)

    def test_the_model_can_stay_silent_after_the_refusal(self):
        protocol = self.protocol()
        self.assertEqual((False, None), protocol.consume(self.reply(protocol, "yikes"), expand=None))
        silence = {"protocol": protocol.request["protocol"], "binding": {"request_id": protocol.request_id}, "action": {"kind": "silence"}}
        self.assertEqual((True, None), protocol.consume(silence, expand=None))
        self.assertIsNone(protocol.turn.action)

    def test_a_turn_that_may_not_react_or_names_an_unseen_target_is_told_that_and_not_to_react_again(self):
        no_reactions = deepcopy(OPPORTUNITY)
        no_reactions["permissions"]["ordinary_actions"] = ["message", "reply"]
        protocol = ParticipantTurnProtocol(profile=PROFILE, wake=test_wake(), opportunity=no_reactions)
        with self.assertRaises(ParticipantModelError) as raised:
            protocol.consume(self.reply(protocol, "yikes"), expand=None)
        self.assertIn("exceeds current ordinary permissions", str(raised.exception))
        self.assertNotIsInstance(raised.exception, ReactionRefused)
        self.assertEqual([], protocol.pages, "it was not told to react again with an emoji")
        protocol = self.protocol()
        unseen = self.reply(protocol, "yikes")
        unseen["action"]["target_event_id"] = "e404"
        with self.assertRaises(ParticipantModelError) as raised:
            protocol.consume(unseen, expand=None)
        self.assertIn("target is absent", str(raised.exception))
        self.assertEqual([], protocol.pages)

    def test_a_second_word_in_the_turn_fails_it_and_a_remove_is_held_to_the_rule_too(self):
        protocol = self.protocol()
        self.assertEqual((False, None), protocol.consume(self.reply(protocol, "ok"), expand=None))
        with self.assertRaises(ParticipantModelError) as raised:
            protocol.consume(self.reply(protocol, ":thumbsup:"), expand=None)
        self.assertIn("not one emoji again", str(raised.exception))
        self.assertIsNone(protocol.turn.action)
        removal = self.protocol()
        self.assertEqual((False, None), removal.consume(self.reply(removal, "yikes", "remove"), expand=None))


class PlainParticipantHostTests(unittest.TestCase):
    """A participant the host runs and that returns its action: the host holds it to the rule, whatever drove the participant."""

    def run_host(self, reaction, operation="add"):
        transport = RecordingTransport(capability=MhmTests.capability())
        participant = CapturingParticipant({**MhmTests.own_mhm("e-word", reaction=reaction), "operation": operation})
        pipeline, _, _, receipts = foundation(model=FixtureModel("mhm"), participant=participant, transport=transport)
        outcome = pipeline.handle_delivery(delivery_id="d-word", event=message("e-word"), actors={"human:alice": {"kind": "human"}})
        return outcome.opportunities[0], transport

    def test_a_word_is_refused_before_anything_is_dispatched(self):
        opportunity, transport = self.run_host("yikes")
        self.assertEqual([], transport.calls)
        self.assertEqual("failed", opportunity.transport.delivery)
        self.assertIn("invalid action", opportunity.transport.detail)

    def test_a_word_is_refused_for_a_removal_too_and_an_emoji_is_removed_as_before(self):
        opportunity, transport = self.run_host("yikes", "remove")
        self.assertEqual([], transport.calls)
        self.assertEqual("failed", opportunity.transport.delivery)
        opportunity, transport = self.run_host("\N{THUMBS UP SIGN}", "remove")
        self.assertEqual([("\N{THUMBS UP SIGN}", "remove")], [(call[0]["reaction"], call[0]["operation"]) for call in transport.calls])

    def test_an_emoji_is_dispatched_as_before(self):
        opportunity, transport = self.run_host("\N{THUMBS UP SIGN}")
        self.assertEqual(1, len(transport.calls))
        self.assertEqual("\N{THUMBS UP SIGN}", transport.calls[0][0]["reaction"])


class TheContractNamesTheChangeTests(unittest.TestCase):
    """A narrowing of the participant's action is a version change: I-040A is @5, and the contract table agrees."""

    ROOT = Path(__file__).resolve().parents[2]

    def test_interface_revisions_match_the_contract_table(self):
        import re

        from nunchi.v2_contracts import INTERFACE_VERSIONS

        self.assertEqual((5, 3), (INTERFACE_VERSIONS["I-040A"], INTERFACE_VERSIONS["I-040D"]))
        table = (self.ROOT / "docs" / "contracts" / "nunchi.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| `(I-\d{3}[A-Z]) [A-Za-z0-9]+` \| `@(\d+)` \|", table, re.M)
        self.assertIn(("I-040A", "5"), rows)
        for interface, version in rows:
            with self.subTest(interface):
                self.assertEqual(INTERFACE_VERSIONS[interface], int(version))
        self.assertIn("`I-040A@5`", (self.ROOT / "docs" / "contracts" / "nunchi.md").read_text(encoding="utf-8"))

    def test_the_kit_has_a_refused_word_nod_for_each_posting_style(self):
        from nunchi.turn_conformance import SCENARIOS

        self.assertEqual(
            {"mhm-word": "tools", "final-mhm-word": "final-answer"},
            {name: scenario.posting for name, scenario in SCENARIOS.items() if name.endswith("mhm-word")},
        )

    def test_each_driver_plays_both_scenarios_on_the_reference(self):
        from nunchi.turn_conformance import ReferenceIntegration, run_scenario

        for name, posting in (("mhm-word", "tools"), ("final-mhm-word", "final-answer")):
            with self.subTest(name):
                self.assertEqual("pass", run_scenario(name, ReferenceIntegration(posting))["status"])


if __name__ == "__main__":
    unittest.main()
