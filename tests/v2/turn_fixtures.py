"""Shared fixtures for core turn and local socket tests."""

import http.client
import json
import socket

from nunchi.attention import ParticipantProfile


PARTICIPANT_ID = "vigil"
ACTOR_ID = "discord:actor:9"
ROOM_ID = "42"
SCOPE_ID = "discord:channel:42"


PROFILE = ParticipantProfile(
    profile_id="vigil-default",
    participant_id=PARTICIPANT_ID,
    actor_id=ACTOR_ID,
    instructions="Contribute on security and implementation correctness.",
    provenance="trusted:test",
    sha256="a" * 64,
)


def test_wake(request_id="r1"):
    """One complete core wake for direct participant tests."""

    return {
        "request_id": request_id,
        "self": {"participant_id": PARTICIPANT_ID, "actor_id": ACTOR_ID},
        "room": {
            "platform": "discord",
            "id": ROOM_ID,
            "continuity_scope_id": SCOPE_ID,
        },
        "actors": {
            ACTOR_ID: {"display_name": "Vigil", "kind": "bot"},
            "discord:actor:42": {"display_name": "Alice", "kind": "human"},
        },
        "events": [
            {
                "id": "e1",
                "type": "message",
                "author_id": "discord:actor:42",
                "text": "Can you take a look?",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            }
        ],
        "trigger_event_id": "e1",
        "coverage": {
            "has_more_before": True,
            "has_more_after": False,
            "has_gaps": False,
            "truncated_by": [],
            "continuity": "restart-safe",
            "has_restart_gap": False,
        },
        "attention": {"source": "WAKE"},
    }


OPPORTUNITY = {
    "generation": 1,
    "lifecycle_id": "lifecycle-1",
    "deadline_id": "deadline-1",
    "permissions": {
        "revision": "rev-1",
        "ordinary_actions": ["message", "reply", "reaction"],
        "privileged_proposals": False,
    },
}


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("nunchi-gate", timeout=10)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._path)


def gate_post(socket_path, route, body, secret):
    connection = _UnixConnection(str(socket_path))
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        headers["X-Nunchi-Session"] = secret
    connection.request("POST", route, json.dumps(body), headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, json.loads(data)
