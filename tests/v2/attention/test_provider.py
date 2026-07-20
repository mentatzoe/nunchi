from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from nunchi.classifiers import classify_attention_v2
from nunchi.policy import load_operator_policy
from tests.v2.security.helpers import clone_policy, write_policy


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def provider_response():
    content = {
        "disposition": "WAKE",
        "reasons": ["current moment warrants attention"],
        "evidence_event_ids": ["e1"],
    }
    return Response({"choices": [{"message": {"content": json.dumps(content)}}]})


class ProviderTransportCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.document = clone_policy()
        self.path = write_policy(self.temporary.name, self.document)
        self.config = load_operator_policy(self.path).classifier
        self.projection = {"request_id": "r1", "events": [{"id": "e1"}]}

    @staticmethod
    def http_error(status):
        return urllib.error.HTTPError(
            "https://provider.invalid",
            status,
            "failed",
            {},
            io.BytesIO(b"provider detail must remain private"),
        )

    def test_success_uses_trusted_endpoint_model_and_secret(self):
        requests = []

        def open_request(request, timeout):
            requests.append((request, timeout))
            return provider_response()

        with patch("nunchi.classifiers.urllib.request.urlopen", side_effect=open_request):
            result = classify_attention_v2(self.projection, self.config)
        self.assertEqual(result["disposition"], "WAKE")
        request, timeout = requests[0]
        self.assertEqual(request.full_url, self.config.endpoint)
        self.assertEqual(timeout, self.config.timeout_seconds)
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.config.api_key}")
        sent = json.loads(request.data)
        self.assertEqual(sent["model"], self.config.model)
        self.assertNotIn(self.config.api_key, request.data.decode("utf-8"))

    def test_retryable_statuses_use_fixed_delays_and_identical_body(self):
        for status in (429, 500, 599):
            with self.subTest(status=status):
                requests = []

                def open_request(request, timeout):
                    requests.append(bytes(request.data))
                    if len(requests) < 3:
                        raise self.http_error(status)
                    return provider_response()

                with (
                    patch("nunchi.classifiers.urllib.request.urlopen", side_effect=open_request),
                    patch("nunchi.classifiers.time.sleep") as sleep,
                ):
                    result = classify_attention_v2(self.projection, self.config)
                self.assertEqual(result["disposition"], "WAKE")
                self.assertEqual(len(requests), 3)
                self.assertEqual(requests[0], requests[1])
                self.assertEqual(requests[1], requests[2])
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1.0])

    def test_non_retryable_statuses_never_sleep(self):
        for status in (499, 600):
            with self.subTest(status=status):
                with (
                    patch(
                        "nunchi.classifiers.urllib.request.urlopen",
                        side_effect=self.http_error(status),
                    ) as opened,
                    patch("nunchi.classifiers.time.sleep") as sleep,
                ):
                    with self.assertRaises(Exception):
                        classify_attention_v2(self.projection, self.config)
                self.assertEqual(opened.call_count, 1)
                sleep.assert_not_called()

    def test_retry_exhaustion_stops_after_configured_attempts(self):
        self.document["classifier"]["max_retries"] = 1
        self.config = load_operator_policy(write_policy(self.temporary.name, self.document)).classifier
        with (
            patch(
                "nunchi.classifiers.urllib.request.urlopen",
                side_effect=urllib.error.URLError("private failure"),
            ) as opened,
            patch("nunchi.classifiers.time.sleep") as sleep,
        ):
            with self.assertRaises(Exception) as caught:
                classify_attention_v2(self.projection, self.config)
        self.assertEqual(opened.call_count, 2)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5])
        self.assertNotIn("private failure", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
