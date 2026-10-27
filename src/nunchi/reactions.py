"""Obsolete: part of the design under architecture review, in which Nunchi runs the agent's turn and sends for it. Do not extend it or build on it.

Authenticated native reaction capability, for the participant's own reactions.

Nunchi never reacts on the participant's behalf (#94 step 7): a mhm is the
participant's own move, and an adapter's attested capability decides whether
the participant may react at all.

What a reaction is belongs here too, once, for every harness: exactly one emoji
(`reaction_refusal`). A word or a ``:name:`` code is not one, and a reaction
that no room would take must not spend the turn's one action, so it is refused
before anything is committed and the agent is told (run 38135715452: the
reaction "yikes").
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ValidationError

# What the agent is told a reaction is, in the tool's description and in the refusal.
THUMBS_UP = "\N{THUMBS UP SIGN}"
REACTION_RULE = (
    f"The reaction must be exactly one emoji, for example {THUMBS_UP}. A word, a :name: code "
    "or more than one emoji is not a reaction."
)

# -- the emoji --------------------------------------------------------------------------------------------
#
# Python's standard library has no emoji data, and its Unicode tables lag the standard, so what an emoji is
# comes from tables below, made once from Unicode 16.0 (the Emoji, Emoji_Modifier_Base and Unassigned
# properties and the 3,790 sequences of RGI_Emoji, which `tests/v2/data/rgi-emoji.json` holds for the test
# that every one of them passes). They are data, not behavior: Unicode 16.0 is the last version they know.
# Anything newer lands in the unassigned code points of the emoji blocks (`_UNASSIGNED_IN_EMOJI_BLOCKS`) and
# passes as a single emoji; a newer ZWJ sequence or flag is refused, and an agent can pick another.

# Emoji=Yes, outside ASCII (the keycap bases 0-9, # and * are `_KEYCAP_BASES`): every emoji is one of these,
# and a symbol that is no emoji (a check mark, a star, a degree sign, braille) is not.
_EMOJI = (
    (0xA9, 0xA9), (0xAE, 0xAE), (0x203C, 0x203C), (0x2049, 0x2049), (0x2122, 0x2122), (0x2139, 0x2139),
    (0x2194, 0x2199), (0x21A9, 0x21AA), (0x231A, 0x231B), (0x2328, 0x2328), (0x23CF, 0x23CF), (0x23E9, 0x23F3),
    (0x23F8, 0x23FA), (0x24C2, 0x24C2), (0x25AA, 0x25AB), (0x25B6, 0x25B6), (0x25C0, 0x25C0), (0x25FB, 0x25FE),
    (0x2600, 0x2604), (0x260E, 0x260E), (0x2611, 0x2611), (0x2614, 0x2615), (0x2618, 0x2618), (0x261D, 0x261D),
    (0x2620, 0x2620), (0x2622, 0x2623), (0x2626, 0x2626), (0x262A, 0x262A), (0x262E, 0x262F), (0x2638, 0x263A),
    (0x2640, 0x2640), (0x2642, 0x2642), (0x2648, 0x2653), (0x265F, 0x2660), (0x2663, 0x2663), (0x2665, 0x2666),
    (0x2668, 0x2668), (0x267B, 0x267B), (0x267E, 0x267F), (0x2692, 0x2697), (0x2699, 0x2699), (0x269B, 0x269C),
    (0x26A0, 0x26A1), (0x26A7, 0x26A7), (0x26AA, 0x26AB), (0x26B0, 0x26B1), (0x26BD, 0x26BE), (0x26C4, 0x26C5),
    (0x26C8, 0x26C8), (0x26CE, 0x26CF), (0x26D1, 0x26D1), (0x26D3, 0x26D4), (0x26E9, 0x26EA), (0x26F0, 0x26F5),
    (0x26F7, 0x26FA), (0x26FD, 0x26FD), (0x2702, 0x2702), (0x2705, 0x2705), (0x2708, 0x270D), (0x270F, 0x270F),
    (0x2712, 0x2712), (0x2714, 0x2714), (0x2716, 0x2716), (0x271D, 0x271D), (0x2721, 0x2721), (0x2728, 0x2728),
    (0x2733, 0x2734), (0x2744, 0x2744), (0x2747, 0x2747), (0x274C, 0x274C), (0x274E, 0x274E), (0x2753, 0x2755),
    (0x2757, 0x2757), (0x2763, 0x2764), (0x2795, 0x2797), (0x27A1, 0x27A1), (0x27B0, 0x27B0), (0x27BF, 0x27BF),
    (0x2934, 0x2935), (0x2B05, 0x2B07), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50), (0x2B55, 0x2B55), (0x3030, 0x3030),
    (0x303D, 0x303D), (0x3297, 0x3297), (0x3299, 0x3299), (0x1F004, 0x1F004), (0x1F0CF, 0x1F0CF), (0x1F170, 0x1F171),
    (0x1F17E, 0x1F17F), (0x1F18E, 0x1F18E), (0x1F191, 0x1F19A), (0x1F1E6, 0x1F1FF), (0x1F201, 0x1F202),
    (0x1F21A, 0x1F21A), (0x1F22F, 0x1F22F), (0x1F232, 0x1F23A), (0x1F250, 0x1F251), (0x1F300, 0x1F321),
    (0x1F324, 0x1F393), (0x1F396, 0x1F397), (0x1F399, 0x1F39B), (0x1F39E, 0x1F3F0), (0x1F3F3, 0x1F3F5),
    (0x1F3F7, 0x1F4FD), (0x1F4FF, 0x1F53D), (0x1F549, 0x1F54E), (0x1F550, 0x1F567), (0x1F56F, 0x1F570),
    (0x1F573, 0x1F57A), (0x1F587, 0x1F587), (0x1F58A, 0x1F58D), (0x1F590, 0x1F590), (0x1F595, 0x1F596),
    (0x1F5A4, 0x1F5A5), (0x1F5A8, 0x1F5A8), (0x1F5B1, 0x1F5B2), (0x1F5BC, 0x1F5BC), (0x1F5C2, 0x1F5C4),
    (0x1F5D1, 0x1F5D3), (0x1F5DC, 0x1F5DE), (0x1F5E1, 0x1F5E1), (0x1F5E3, 0x1F5E3), (0x1F5E8, 0x1F5E8),
    (0x1F5EF, 0x1F5EF), (0x1F5F3, 0x1F5F3), (0x1F5FA, 0x1F64F), (0x1F680, 0x1F6C5), (0x1F6CB, 0x1F6D2),
    (0x1F6D5, 0x1F6D7), (0x1F6DC, 0x1F6E5), (0x1F6E9, 0x1F6E9), (0x1F6EB, 0x1F6EC), (0x1F6F0, 0x1F6F0),
    (0x1F6F3, 0x1F6FC), (0x1F7E0, 0x1F7EB), (0x1F7F0, 0x1F7F0), (0x1F90C, 0x1F93A), (0x1F93C, 0x1F945),
    (0x1F947, 0x1F9FF), (0x1FA70, 0x1FA7C), (0x1FA80, 0x1FA89), (0x1FA8F, 0x1FAC6), (0x1FACE, 0x1FADC),
    (0x1FADF, 0x1FAE9), (0x1FAF0, 0x1FAF8),
)

# The code points no version up to 16.0 assigns, inside the emoji blocks (U+1F300-1F64F, 1F680-1F6FF,
# 1F7E0-1F7FF, 1F900-1F9FF, 1FA70-1FAFF): where the emoji a later version adds will be.
_UNASSIGNED_IN_EMOJI_BLOCKS = (
    (0x1F6D8, 0x1F6DB), (0x1F6ED, 0x1F6EF), (0x1F6FD, 0x1F6FF), (0x1F7EC, 0x1F7EF), (0x1F7F1, 0x1F7FF),
    (0x1FA7D, 0x1FA7F), (0x1FA8A, 0x1FA8E), (0x1FAC7, 0x1FACD), (0x1FADD, 0x1FADE), (0x1FAEA, 0x1FAEF),
    (0x1FAF9, 0x1FAFF),
)

# Emoji_Modifier_Base: the emoji a skin tone may follow.
_MODIFIER_BASES = (
    (0x261D, 0x261D), (0x26F9, 0x26F9), (0x270A, 0x270D), (0x1F385, 0x1F385), (0x1F3C2, 0x1F3C4), (0x1F3C7, 0x1F3C7),
    (0x1F3CA, 0x1F3CC), (0x1F442, 0x1F443), (0x1F446, 0x1F450), (0x1F466, 0x1F478), (0x1F47C, 0x1F47C),
    (0x1F481, 0x1F483), (0x1F485, 0x1F487), (0x1F48F, 0x1F48F), (0x1F491, 0x1F491), (0x1F4AA, 0x1F4AA),
    (0x1F574, 0x1F575), (0x1F57A, 0x1F57A), (0x1F590, 0x1F590), (0x1F595, 0x1F596), (0x1F645, 0x1F647),
    (0x1F64B, 0x1F64F), (0x1F6A3, 0x1F6A3), (0x1F6B4, 0x1F6B6), (0x1F6C0, 0x1F6C0), (0x1F6CC, 0x1F6CC),
    (0x1F90C, 0x1F90C), (0x1F90F, 0x1F90F), (0x1F918, 0x1F91F), (0x1F926, 0x1F926), (0x1F930, 0x1F939),
    (0x1F93C, 0x1F93E), (0x1F977, 0x1F977), (0x1F9B5, 0x1F9B6), (0x1F9B8, 0x1F9B9), (0x1F9BB, 0x1F9BB),
    (0x1F9CD, 0x1F9CF), (0x1F9D1, 0x1F9DD), (0x1FAC3, 0x1FAC5), (0x1FAF0, 0x1FAF8),
)

# The emoji that follow a joiner in some RGI ZWJ sequence (person, gender, hair, objects): the second and later
# parts of a joined sequence are one of these, so two emoji that happen to be joined are not an emoji.
_JOINED = frozenset(
    (
        0x2194, 0x2195, 0x2620, 0x2640, 0x2642, 0x2695, 0x2696, 0x26A7, 0x2708, 0x2744, 0x2764, 0x27A1, 0x2B1B, 0x1F308,
        0x1F32B, 0x1F33E, 0x1F373, 0x1F37C, 0x1F384, 0x1F393, 0x1F3A4, 0x1F3A8, 0x1F3EB, 0x1F3ED, 0x1F466, 0x1F467,
        0x1F468, 0x1F469, 0x1F48B, 0x1F4A5, 0x1F4A8, 0x1F4AB, 0x1F4BB, 0x1F4BC, 0x1F525, 0x1F527, 0x1F52C, 0x1F5E8,
        0x1F680, 0x1F692, 0x1F7E9, 0x1F7EB, 0x1F91D, 0x1F9AF, 0x1F9B0, 0x1F9B1, 0x1F9B2, 0x1F9B3, 0x1F9BA, 0x1F9BC,
        0x1F9BD, 0x1F9D1, 0x1F9D2, 0x1FA79, 0x1FAF2,
    )
)

# The flags: the two-letter regions of the 259 RGI flag sequences (a pair of regional indicators).
_FLAGS = frozenset(
    (
        "AC AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW "
        "BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CP CQ CR CU CV CW CX CY CZ DE DG DJ DK DM DO DZ EA EC EE EG EH ER "
        "ES ET EU FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU IC ID "
        "IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA "
        "MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA "
        "PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST "
        "SV SX SY SZ TA TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM UN US UY UZ VA VC VE VG VI VN VU WF "
        "WS XK YE YT ZA ZM ZW"
    ).split()
)

_JOINER = "\u200d"
_EMOJI_STYLE = "\ufe0f"
_KEYCAP_MARK = "\u20e3"
_KEYCAP_BASES = frozenset("0123456789#*")
_SKIN_TONES = frozenset(chr(code) for code in range(0x1F3FB, 0x1F400))
_REGIONAL_A = 0x1F1E6
_REGIONAL_Z = 0x1F1FF
# The subdivision flags of RGI: a black flag, the tag characters of a region and a subdivision, a cancel tag.
_TAG_FLAGS = frozenset(
    "\U0001f3f4" + "".join(chr(0xE0000 + ord(letter)) for letter in region) + "\U000e007f"
    for region in ("gbeng", "gbsct", "gbwls")
)
# The longest RGI ZWJ sequence has four parts (a couple kissing, a family); an emoji is never longer than ten
# code points.
_MOST_PARTS = 4
_LONGEST = 16

_EMOJI_STARTS = tuple(first for first, _ in _EMOJI)
_EMOJI_ENDS = tuple(last for _, last in _EMOJI)
_HOLE_STARTS = tuple(first for first, _ in _UNASSIGNED_IN_EMOJI_BLOCKS)
_HOLE_ENDS = tuple(last for _, last in _UNASSIGNED_IN_EMOJI_BLOCKS)
_BASE_STARTS = tuple(first for first, _ in _MODIFIER_BASES)
_BASE_ENDS = tuple(last for _, last in _MODIFIER_BASES)


def _within(starts: tuple[int, ...], ends: tuple[int, ...], code: int) -> bool:
    position = bisect_right(starts, code) - 1
    return position >= 0 and code <= ends[position]


def _pictograph(code: int) -> bool:
    """Whether a code point is an emoji of its own, or a place a later version puts one."""

    return _within(_EMOJI_STARTS, _EMOJI_ENDS, code) or _within(_HOLE_STARTS, _HOLE_ENDS, code)


def _emoji_part(part: str, *, joined: bool) -> bool:
    """One piece of an emoji: a base, then at most an emoji-style mark and, on a base that takes one, a skin tone.

    After a joiner (``joined``) the base is one that follows a joiner in some RGI sequence.
    """

    if not part:
        return False
    base = ord(part[0])
    if not (base in _JOINED if joined else _pictograph(base)):
        return False
    rest = part[1:]
    if part[0] in _SKIN_TONES:
        return rest == ""  # a skin tone alone is a swatch: nothing follows it
    if rest[:1] == _EMOJI_STYLE:
        rest = rest[1:]
    if rest == "":
        return True
    return len(rest) == 1 and rest in _SKIN_TONES and _within(_BASE_STARTS, _BASE_ENDS, base)


def is_one_emoji(value: Any) -> bool:
    """Whether ``value`` is exactly one emoji, nothing more and nothing less.

    Every sequence of RGI_Emoji passes (a test plays all 3,790 of Unicode 16.0), and what no room would take
    does not: a word, a ``:name:`` code, a symbol that is no emoji (a check mark, a star, a degree sign), a
    letter or digit alone, two emoji, two skin tones, or two emoji joined by a joiner. One emoji is:

    - a single emoji (``_EMOJI``, or an unassigned place for a later one in the emoji blocks), with an
      emoji-style mark, and a skin tone where it takes one;
    - a joined sequence of up to four parts, each such a piece, the second and later ones among the emoji
      that follow a joiner in RGI (``_JOINED``);
    - a flag (a pair of regional indicators for a region RGI has), a lone regional indicator, or one of the
      three subdivision flags (England, Scotland, Wales);
    - a keycap (``0``-``9``, ``#`` or ``*``, the emoji-style mark, the keycap mark).

    The standard library has no emoji data, so this is Unicode 16.0's: an emoji sequence newer than that
    (a flag, a joined sequence) is refused, and the agent can pick another. Which emoji a room has is still
    the room's to say.
    """

    if not isinstance(value, str) or not value or len(value) > _LONGEST:
        return False
    first = value[0]
    if first in _KEYCAP_BASES:
        return value[1:] in (_KEYCAP_MARK, _EMOJI_STYLE + _KEYCAP_MARK)
    if _REGIONAL_A <= ord(first) <= _REGIONAL_Z:
        if len(value) == 1:
            return True
        letters = "".join(chr(ord(c) - _REGIONAL_A + 65) for c in value if _REGIONAL_A <= ord(c) <= _REGIONAL_Z)
        return len(value) == 2 and letters in _FLAGS
    if value in _TAG_FLAGS:
        return True
    parts = value.split(_JOINER)
    if len(parts) > _MOST_PARTS:
        return False
    return all(_emoji_part(part, joined=index > 0) for index, part in enumerate(parts))


def reaction_refusal(reaction: Any) -> str | None:
    """Why ``reaction`` is not a reaction, or None when it is exactly one emoji (`is_one_emoji`)."""

    return None if is_one_emoji(reaction) else REACTION_RULE


@dataclass(frozen=True)
class ReactionCapability:
    """Authenticated native reaction facts supplied by a platform adapter."""

    supported: bool
    authenticated: bool
    operations: tuple[str, ...] = ()
    reactions: tuple[str, ...] = ()
    permissions_revision: str = "unavailable"
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.supported, bool) or not isinstance(self.authenticated, bool):
            raise ValueError("reaction capability booleans are invalid")
        if any(item not in ("add", "remove") for item in self.operations):
            raise ValueError("reaction capability operation is unsupported")
        if len(self.operations) != len(set(self.operations)):
            raise ValueError("reaction capability operations must be unique")
        if not all(isinstance(item, str) and item for item in self.reactions):
            raise ValueError("reaction capability reactions must be non-empty strings")
        if not isinstance(self.permissions_revision, str) or not self.permissions_revision:
            raise ValueError("reaction permissions revision must be non-empty")
        if not isinstance(self.detail, str):
            raise ValueError("reaction capability detail must be a string")

    def allows(self, reaction: str, operation: str = "add") -> bool:
        return self.permits(operation) and (
            "*" in self.reactions or reaction in self.reactions
        )

    def permits(self, operation: str = "add") -> bool:
        """Whether the participant may add or remove some reaction."""

        return (
            self.supported
            and self.authenticated
            and operation in self.operations
            and bool(self.reactions)
        )

    def document(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "authenticated": self.authenticated,
            "operations": list(self.operations),
            "reactions": list(self.reactions),
            "permissions_revision": self.permissions_revision,
            **({"detail": self.detail} if self.detail else {}),
        }


UNAVAILABLE_REACTION_CAPABILITY = ReactionCapability(
    supported=False,
    authenticated=False,
    permissions_revision="unavailable",
    detail="adapter did not attest native reaction capability",
)


def reaction_capability(value: Any) -> ReactionCapability:
    if isinstance(value, ReactionCapability):
        return value
    if value is None:
        return UNAVAILABLE_REACTION_CAPABILITY
    if not isinstance(value, Mapping):
        raise ValidationError("reaction capability must be an object")
    required = {
        "supported",
        "authenticated",
        "operations",
        "reactions",
        "permissions_revision",
    }
    optional = {"detail"}
    if required - set(value) or set(value) - (required | optional):
        raise ValidationError("reaction capability has a missing or unexpected field")
    try:
        return ReactionCapability(
            supported=value["supported"],
            authenticated=value["authenticated"],
            operations=tuple(value["operations"]),
            reactions=tuple(value["reactions"]),
            permissions_revision=value["permissions_revision"],
            detail=value.get("detail", ""),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"reaction capability is invalid: {exc}") from exc
