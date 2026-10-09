"""The key and canary scan over every output file (step 9f, PR 1).

Before anything is uploaded, every file under the output directory is read
for each secret's value, in three copies of the file: as written; normalized
(`normalized`: JSON escapes undone, whitespace and backslashes removed), so a
value split across lines or spaces, line-wrapped base64 or a hex dump, or a
value inside a JSON string reads as one run of characters; and that copy in
lower case, for hex. In each copy it looks for the value as written,
base64-encoded at each of the three byte alignments a value can take inside
a longer base64 text (standard and URL-safe alphabets), and hex-encoded. A
symlink among the outputs, or a file that cannot be read, counts as a hit.
A hit deletes every output and fails the run; the result names the file and
the variable, never the value.

    python -m evals.rehearsal.scan --out rehearsal-out \\
        --env NUNCHI_ATTENTION_API_KEY --env REHEARSAL_CANARY

writes ``scan.json``, and exits 0 when the outputs are clean, 1 after a hit
(the outputs are gone, and nothing is left but the leak notice and
``scan.json``, checked again after deleting), and 2 when no value to look
for was set.

No scan finds every encoding: a hex dump with an address or a text column
between its lines (``xxd``'s default), or an encryption, is not matched.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Iterable, Mapping, Sequence
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

# A value shorter than this is too short to look for without false hits.
MIN_SECRET_LENGTH = 12


def encodings(value: str) -> list[tuple[str, bytes]]:
    """The forms of ``value`` the scan looks for: raw, base64 at each alignment, and hex.

    Inside a longer base64 text a value starts at byte offset 0, 1 or 2 of a
    3-byte group. For each offset, only the characters that depend on the
    value's bytes alone are kept, so the fragment matches wherever the value
    sits. Surrounding whitespace is not part of the value.
    """

    raw = value.strip().encode("utf-8")
    forms = [("raw", raw)]
    for offset in range(3):
        padded = b"\0" * offset + raw
        for encode in (base64.b64encode, base64.urlsafe_b64encode):
            text = encode(padded)
            start = (offset * 8 + 5) // 6
            end = (len(padded) * 8) // 6
            fragment = text[start:end]
            if len(fragment) >= MIN_SECRET_LENGTH:
                forms.append(("base64", fragment))
    forms.append(("hex", raw.hex().encode("ascii")))
    return list(dict.fromkeys(forms))


# JSON's escapes of whitespace, and of an ASCII character, at any depth of nesting.
_ESCAPED_SPACE = re.compile(rb"\\+[nrt]")
_ESCAPED_ASCII = re.compile(rb"\\+u00([0-7][0-9a-fA-F])")
_BACKSLASHES = re.compile(rb"\\+")
_WHITESPACE = re.compile(rb"\s+")


def normalized(data: bytes) -> bytes:
    """``data`` as one unbroken run: JSON escapes undone, whitespace and backslashes removed.

    Line-wrapped base64 or hex, a value split by spaces or newlines, and a
    value in a JSON string (or a JSON string inside one) all come out whole.
    It is only searched, never written.
    """

    text = _ESCAPED_ASCII.sub(lambda match: bytes.fromhex(match.group(1).decode("ascii")), data)
    text = _ESCAPED_SPACE.sub(b"", text)
    text = _BACKSLASHES.sub(b"", text)
    return _WHITESPACE.sub(b"", text)


def scan(directory: Path, secrets: Mapping[str, str]) -> dict[str, Any]:
    """Look for every secret in every file under ``directory``.

    ``secrets`` maps a variable's name to its value. Returns the result:
    ``clean``, the files read, and each hit as ``{"file", "variable",
    "form"}`` (``raw``, ``base64`` or ``hex``). Values shorter than
    `MIN_SECRET_LENGTH` are not looked for, and are listed as skipped. A
    file that cannot be read, or a symlink, is listed under ``unreadable``
    and the outputs are not clean.
    """

    looked_for: dict[str, list[tuple[str, bytes]]] = {}
    skipped: list[str] = []
    for name, value in secrets.items():
        if isinstance(value, str) and len(value.strip()) >= MIN_SECRET_LENGTH:
            looked_for[name] = encodings(value)
        else:
            skipped.append(name)
    hits: list[dict[str, str]] = []
    files = 0
    unreadable: list[str] = []
    for path in sorted(directory.rglob("*")) if directory.exists() else ():
        relative = str(path.relative_to(directory))
        if path.is_symlink():
            # The upload would follow it to whatever it points at, which nothing here read.
            unreadable.append(f"{relative} (a symlink)")
            continue
        if not path.is_file():
            continue
        files += 1
        try:
            data = path.read_bytes()
        except OSError:
            unreadable.append(relative)
            continue
        flat = normalized(data)
        copies = (data, flat, flat.lower())
        for name, forms in looked_for.items():
            found = next((label for label, form in forms if any(form in copy for copy in copies)), None)
            if found is not None:
                hits.append({"file": relative, "variable": name, "form": found})
    return {
        "clean": not hits and not unreadable,
        "files_scanned": files,
        "variables": sorted(looked_for),
        "skipped_variables": sorted(skipped),
        "hits": hits,
        "unreadable": unreadable,
    }


def delete_outputs(directory: Path) -> None:
    """Remove everything under ``directory``, keeping the directory itself."""

    if not directory.exists():
        return
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def secrets_from_env(names: Iterable[str], environ: Mapping[str, str] | None = None) -> dict[str, str]:
    environ = os.environ if environ is None else environ
    return {name: environ[name] for name in names if environ.get(name)}


def leak_notice(result: Mapping[str, Any]) -> str:
    """What summary.md says after a hit: where, and which variable, never the value."""

    lines = [
        "# Rehearsal outputs deleted",
        "",
        "**Failed: a secret was found in the outputs, so every output was deleted.**",
        "",
        "| File | Variable | Form |",
        "|---|---|---|",
    ]
    lines += [f"| `{hit['file']}` | `{hit['variable']}` | {hit['form']} |" for hit in result.get("hits", ())]
    for name in result.get("unreadable", ()):
        lines.append(f"| `{name}` | (unreadable) | |")
    return "\n".join(lines) + "\n"


def enforce(directory: Path, secrets: Mapping[str, str]) -> dict[str, Any]:
    """Scan every output, and write the result to ``scan.json``.

    After a hit every output is deleted, ``summary.md`` says where and which
    variable (`leak_notice`), and the directory is listed again: anything
    left but the notice is named under ``left_after_deleting`` and in the
    notice. The probe and this command both end with it.
    """

    result = scan(directory, secrets)
    directory.mkdir(parents=True, exist_ok=True)
    if not result["clean"]:
        delete_outputs(directory)
        (directory / "summary.md").write_text(leak_notice(result), encoding="utf-8")
        left = sorted(str(path.relative_to(directory)) for path in directory.rglob("*") if path != directory / "summary.md")
        result["left_after_deleting"] = left
        if left:
            with open(directory / "summary.md", "a", encoding="utf-8") as notice:
                notice.write("\n**Not every output could be deleted:** " + ", ".join(f"`{name}`" for name in left) + "\n")
    (directory / "scan.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.rehearsal.scan")
    parser.add_argument("--out", required=True, help="the output directory to scan")
    parser.add_argument("--env", action="append", default=[], help="a variable whose value to look for (repeat)")
    args = parser.parse_args(argv)
    directory = Path(args.out)
    secrets = secrets_from_env(args.env)
    if not secrets:
        print("scan: none of the named variables is set; nothing to look for", file=sys.stderr)
        return 2
    result = enforce(directory, secrets)
    if not result["clean"]:
        print(
            f"scan: {len(result['hits'])} hit(s), {len(result['unreadable'])} unreadable; the outputs were deleted",
            file=sys.stderr,
        )
        return 1
    print(f"scan: clean ({result['files_scanned']} files, {', '.join(result['variables'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
