from __future__ import annotations

import json
import unittest
import urllib.error
from unittest import mock

import nunchi.integrations.mcp_transport_v2 as transport_v2
from nunchi.integrations.mcp_transport_v2 import (
    MCPTransportClientV2,
    MCPTransportV2Error,
    iter_sse_data,
)
from nunchi.mcp_discord.events import V2_NOTIFICATION_METHOD


AUTH = "mcp-client-auth-secret-0123456789abcdef"


class Response:
    def __init__(self, payload=b"", *, headers=None, lines=None):
        self.payload = payload
        self.headers = headers or {}
        self.lines = list(lines or [])

    def read(self, _size=-1):
        return self.payload

    def __iter__(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class ScriptedOpen:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class MCPTransportClientCases(unittest.TestCase):
    @staticmethod
    def jsonrpc_response(request_id, result):
        return Response(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "result": result}
            ).encode("utf-8")
        )

    @classmethod
    def initialize_response(cls, *, headers=None):
        response = cls.jsonrpc_response(
            1,
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "serverInfo": {"name": "nunchi-mcp-discord", "version": "2"},
            },
        )
        response.headers = headers or {"mcp-session-id": "session-1"}
        return response

    @classmethod
    def tools_response(cls):
        return cls.jsonrpc_response(
            2,
            {
                "tools": [
                    {"name": name}
                    for name in (
                        "send_message",
                        "reply_message",
                        "add_reaction",
                        "read_history",
                    )
                ]
            },
        )

    def test_every_handshake_tool_and_stream_request_is_bearer_authenticated(self):
        tool_document = {
            "jsonrpc": "2.0",
            "id": 10,
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps({"messages": []})}
                ]
            },
        }
        event_document = {
            "jsonrpc": "2.0",
            "method": V2_NOTIFICATION_METHOD,
            "params": {"schema_version": 2, "platform": "discord"},
        }
        scripted = ScriptedOpen(
            [
                self.initialize_response(),
                Response(),
                self.tools_response(),
                Response(json.dumps(tool_document).encode("utf-8")),
                Response(
                    lines=[
                        f"data: {json.dumps(event_document)}\n".encode("utf-8"),
                        b"\n",
                    ]
                ),
            ]
        )
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        self.assertEqual(client.initialize(), "session-1")
        self.assertEqual(client.call_tool("read_history", {"channel_id": "42"}), {"messages": []})
        self.assertEqual(next(client.stream_events())["schema_version"], 2)
        for request, _timeout in scripted.requests:
            self.assertEqual(request.get_header("Authorization"), f"Bearer {AUTH}")

    def test_cross_origin_redirect_is_refused_without_forwarding_credential(self):
        redirect = urllib.error.HTTPError(
            "http://127.0.0.1:3993/mcp",
            307,
            "redirect",
            {"Location": "https://attacker.example/mcp"},
            None,
        )
        scripted = ScriptedOpen([redirect])
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        with self.assertRaisesRegex(MCPTransportV2Error, "cross-origin"):
            client.initialize()
        self.assertEqual(len(scripted.requests), 1)
        self.assertNotIn(AUTH, str(redirect))

    def test_plain_http_is_loopback_only_and_credentials_are_strict(self):
        with self.assertRaises(MCPTransportV2Error):
            MCPTransportClientV2("http://transport.example/mcp", AUTH)
        for endpoint in (
            "https://transport.example/bad\npath",
            "https://transport.example:bad/mcp",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(MCPTransportV2Error):
                    MCPTransportClientV2(endpoint, AUTH)
        with self.assertRaises(MCPTransportV2Error):
            MCPTransportClientV2("http://127.0.0.1:3993/mcp", "short")

    def test_sse_and_tool_json_are_bounded_and_strict(self):
        with mock.patch.object(transport_v2, "MAX_SSE_EVENT_BYTES", 16):
            with self.assertRaisesRegex(MCPTransportV2Error, "size budget"):
                tuple(iter_sse_data(["data: " + "x" * 17, ""]))
        duplicate = b'{"id":10,"id":10,"result":{}}'
        scripted = ScriptedOpen([Response(duplicate)])
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        client.session_id = "session-1"
        with self.assertRaises(MCPTransportV2Error):
            client.call_tool("read_history", {"channel_id": "42"})

        scripted = ScriptedOpen(
            [Response(b'{"id":10,"result":{"messages":[]}}')]
        )
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        client.session_id = "session-1"
        with self.assertRaises(MCPTransportV2Error):
            client.call_tool("read_history", {"channel_id": "42"})

    def test_tool_result_rejects_missing_multiple_or_conflicting_content(self):
        cases = (
            {"content": []},
            {"content": [{"type": "image", "data": "ignored"}]},
            {
                "content": [
                    {"type": "text", "text": '{"messages":[]}'},
                    {"type": "text", "text": '{"messages":[{"message_id":"other"}]}'},
                ]
            },
            {
                "content": [{"type": "text", "text": '{"messages":[]}'}],
                "structuredContent": {"messages": [{"message_id": "other"}]},
            },
            {
                "content": [{"type": "text", "text": '{"count":1}'}],
                "structuredContent": {"count": True},
            },
            {
                "content": [{"type": "text", "text": '{"messages":[]}'}],
                "isError": "false",
            },
        )
        for result in cases:
            with self.subTest(result=result):
                scripted = ScriptedOpen([self.jsonrpc_response(10, result)])
                client = MCPTransportClientV2(
                    "http://127.0.0.1:3993/mcp",
                    AUTH,
                    open_request=scripted,
                )
                client.session_id = "session-1"
                with self.assertRaises(MCPTransportV2Error):
                    client.call_tool("read_history", {"channel_id": "42"})

    def test_tool_result_accepts_matching_structured_content(self):
        payload = {"messages": []}
        scripted = ScriptedOpen(
            [
                self.jsonrpc_response(
                    10,
                    {
                        "content": [
                            {"type": "text", "text": json.dumps(payload)}
                        ],
                        "structuredContent": payload,
                        "isError": False,
                    },
                )
            ]
        )
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        client.session_id = "session-1"
        self.assertEqual(
            client.call_tool("read_history", {"channel_id": "42"}),
            payload,
        )

    def test_empty_data_lines_cannot_exceed_sse_event_budget(self):
        with mock.patch.object(transport_v2, "MAX_SSE_EVENT_BYTES", 4):
            with self.assertRaisesRegex(MCPTransportV2Error, "size budget"):
                tuple(iter_sse_data(["data:\n"] * 6 + ["\n"]))

    def test_initialize_rejects_uncorrelated_error_and_incomplete_handshakes(self):
        cases = (
            Response(
                json.dumps(
                    {"jsonrpc": "2.0", "id": 99, "result": {}}
                ).encode("utf-8"),
                headers={"mcp-session-id": "session-1"},
            ),
            Response(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "error": {"code": -32000, "message": "no"},
                    }
                ).encode("utf-8"),
                headers={"mcp-session-id": "session-1"},
            ),
        )
        for response in cases:
            with self.subTest(payload=response.payload):
                client = MCPTransportClientV2(
                    "http://127.0.0.1:3993/mcp",
                    AUTH,
                    open_request=ScriptedOpen([response]),
                )
                with self.assertRaises(MCPTransportV2Error):
                    client.initialize()
                self.assertIsNone(client.session_id)

        scripted = ScriptedOpen(
            [
                self.initialize_response(),
                Response(),
                self.jsonrpc_response(2, {"tools": [{"name": "read_history"}]}),
            ]
        )
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        with self.assertRaisesRegex(MCPTransportV2Error, "incomplete"):
            client.initialize()
        self.assertIsNone(client.session_id)

    def test_initialize_accepts_strict_sse_jsonrpc_result(self):
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "serverInfo": {"name": "nunchi-mcp-discord", "version": "2"},
            },
        }
        tools = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {"name": name}
                    for name in (
                        "send_message",
                        "reply_message",
                        "add_reaction",
                        "read_history",
                    )
                ]
            },
        }
        scripted = ScriptedOpen(
            [
                Response(
                    f"event: message\ndata: {json.dumps(initialize)}\n\n".encode(),
                    headers={"mcp-session-id": "session-1"},
                ),
                Response(),
                Response(f"data: {json.dumps(tools)}\n\n".encode()),
            ]
        )
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        self.assertEqual(client.initialize(), "session-1")

    def test_stream_eof_is_operational_failure_not_successful_completion(self):
        scripted = ScriptedOpen([Response(lines=[])])
        client = MCPTransportClientV2(
            "http://127.0.0.1:3993/mcp",
            AUTH,
            open_request=scripted,
        )
        client.session_id = "session-1"
        with self.assertRaisesRegex(MCPTransportV2Error, "stream ended"):
            tuple(client.stream_events())


if __name__ == "__main__":
    unittest.main()
