"""Secret scanning for records before publication."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest import mock

from evals import scan_records as scan


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
