# Nunchi V2 adapter facts and capability parity

V2 adapters normalize transport facts into the common observation provider;
they do not decide who should speak. Equivalent facts use exact platform actor,
room and event identities. Missing facts remain missing.

| Surface | Message/reply | Reaction | Membership | History/restart |
|---|---|---|---|---|
| Generic reference host | Host-attested | Host-attested | Host-attested | Host declares truthfully |
| Shared Discord | Messages, replies, exact user/room mentions; thread root only when supplied by trusted metadata | Live add/remove with gateway session+sequence identity | Unavailable in current source | Bounded REST message history; restart gap remains declared |
| Matrix reference | Native messages, replies and thread roots | Native `m.annotation` add | Native join/leave | Sync token plus bounded history; full restart safety not claimed |
| Telegram reference | Messages, replies, structured `text_mention` user IDs | Unavailable without prior-state diff | Chat-member join/leave | Bot API history unavailable; known restart gap |

Telegram `@username` text does not establish a user ID. Matrix display names do
not establish an MXID. Discord display names do not establish a snowflake.
These are deliberate security and parity properties, not missing convenience
features.

All surfaces feed `LiveRoomRuntime`: one active attention/participant turn, one
replaceable newest pending anchor, a fresh current-tail participant view, and no
send-time social reclassification.
