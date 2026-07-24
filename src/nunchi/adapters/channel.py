"""Installed generic V2 JSONL host adapter."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

from .. import __version__
from ..errors import NunchiError, ValidationError
from .runtime import CAPABILITIES, JsonLineTransport, ReferenceAdapterRuntime, load_pinned_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi-channel")
    parser.add_argument("--config")
    parser.add_argument(
        "--config-sha256",
        default=os.environ.get("NUNCHI_ADAPTER_CONFIG_SHA256"),
    )
    parser.add_argument("--probe", action="store_true")
    return parser


def _static_probe() -> dict:
    return {
        "product": "nunchi",
        "product_version": __version__,
        "generation": 2,
        "surface": "channel",
        "capabilities": CAPABILITIES["channel"],
        "configured": False,
        "v1_fallback": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.config:
            if args.probe:
                print(json.dumps(_static_probe(), sort_keys=True, separators=(",", ":")))
                return 0
            raise ValidationError("--config is required outside static probe mode")
        if not args.config_sha256:
            raise ValidationError("--config-sha256 or NUNCHI_ADAPTER_CONFIG_SHA256 is required")
        config = load_pinned_config(args.config, args.config_sha256)
        runtime = ReferenceAdapterRuntime(
            surface="channel",
            config=config,
            transport=JsonLineTransport(),
        )
        if args.probe:
            print(json.dumps(runtime.probe(), sort_keys=True, separators=(",", ":")))
            return 0
        failed = False
        for line_number, line in enumerate(sys.stdin, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                runtime.process(payload)
            except (json.JSONDecodeError, NunchiError, ValueError) as exc:
                failed = True
                print(
                    json.dumps(
                        {
                            "error": "adapter-delivery-failed",
                            "line": line_number,
                            "detail": str(exc),
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
        return 1 if failed else 0
    except NunchiError as exc:
        print(f"{exc.label}: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
