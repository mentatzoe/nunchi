"""The shape pin: the keys discord.py 2.7.1 types each payload with, checked on every payload the stand-in sends.

A payload missing a key discord.py indexes kills its gateway connection, or
silently drops what a message says about its author (map-discordpy.md,
Bottom line 5). discord.py's ``discord.types`` modules cannot be imported
(they import each other in a circle), so this reads them by AST, merges the
keys each TypedDict inherits, and vendors the types the stand-in sends
(`payloads.SHAPES`), with the TypedDicts nested in them, as
``discord_types.json``. It pins discord.py's model of Discord, not Discord.

    python -m evals.rehearsal.fake_discord.shapes          # rewrite discord_types.json from the installed discord.py
    python -m evals.rehearsal.fake_discord.shapes --check  # exit 1 unless it still matches discord.py 2.7.1
"""

from __future__ import annotations

import argparse
import ast
from functools import cache
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from .payloads import SHAPES

PINNED = "2.7.1"
VENDORED = Path(__file__).with_name("discord_types.json")

# Required keys the stand-in leaves out, each with its reason.
EXEMPT = {
    "guild.Guild": {"region": "deprecated: Discord's documentation marks it optional"},
    "gateway.ReadyEvent": {"shard": "sent only when IDENTIFY asks for shards, and no client here does"},
}
# Nested objects the pin cannot follow, each with its reason: discord.types types them as a Union.
UNIONS = {
    "guild.Guild": {"channels": "channel.TextChannel[]"},  # the stand-in sends only text channels there; threads go in "threads"
}

_WRAPPERS = {"NotRequired": False, "Required": True, "Optional": None}


def generate(types_dir: Path) -> dict[str, Any]:
    classes: dict[str, tuple[list[str], dict[str, tuple[bool, str | None]]]] = {}
    aliases: dict[str, str] = {}
    for path in sorted(types_dir.glob("*.py")):
        module = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"))
        body = tree.body + [n for node in tree.body if isinstance(node, ast.If) for n in node.body]
        local: dict[str, str] = {}
        for node in body:
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                local.update({a.asname or a.name: f"{node.module}.{a.name}" for a in node.names})
            elif isinstance(node, ast.ClassDef):
                local[node.name] = f"{module}.{node.name}"
            elif isinstance(node, ast.Assign):
                local.update({t.id: f"{module}.{t.id}" for t in node.targets if isinstance(t, ast.Name)})

        def ref(annotation: ast.expr) -> tuple[bool | None, str | None]:
            """(required, nested type) from an annotation: NotRequired/Required/Optional unwrapped, List marked ``[]``."""
            required: bool | None = None
            while isinstance(annotation, ast.Subscript) and getattr(annotation.value, "id", None) in _WRAPPERS:
                flag = _WRAPPERS[annotation.value.id]
                required = flag if required is None else required
                annotation = annotation.slice
            suffix = ""
            if isinstance(annotation, ast.Subscript) and getattr(annotation.value, "id", None) in ("List", "list"):
                annotation, suffix = annotation.slice, "[]"
            if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
                annotation = ast.parse(annotation.value, mode="eval").body
            name = local.get(annotation.id) if isinstance(annotation, ast.Name) else None
            return required, (name + suffix if name else None)

        for node in body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in local:
                aliases.update({f"{module}.{t.id}": local[node.value.id] for t in node.targets if isinstance(t, ast.Name)})
            if not isinstance(node, ast.ClassDef):
                continue
            total = next((k.value.value for k in node.keywords if k.arg == "total"), True)
            fields: dict[str, tuple[bool, str | None]] = {}
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    required, nested = ref(item.annotation)
                    fields[item.target.id] = (total if required is None else required, nested)
            classes[f"{module}.{node.name}"] = ([local[b.id] for b in node.bases if isinstance(b, ast.Name) and b.id in local], fields)

    def canon(name: str | None) -> str | None:
        while name in aliases:
            name = aliases[name]
        return name if name in classes else None

    @cache
    def merged(name: str) -> dict[str, tuple[bool, str | None]]:
        bases, own = classes[name]
        fields: dict[str, tuple[bool, str | None]] = {}
        for base in bases:
            if canon(base):
                fields.update(merged(canon(base)))
        return {**fields, **own}

    types: dict[str, Any] = {}
    pending = [canon(name) for name in SHAPES.values()]
    while pending:
        name = pending.pop()
        if name is None or name in types:
            continue
        nested = {}
        for key, (_, ref_name) in merged(name).items():
            target = canon(ref_name.removesuffix("[]")) if ref_name else None
            if target:
                nested[key] = target + ("[]" if ref_name.endswith("[]") else "")
                pending.append(target)
        fields = merged(name)
        types[name] = {"required": sorted(k for k, (r, _) in fields.items() if r),
                       "optional": sorted(k for k, (r, _) in fields.items() if not r), "nested": nested}
    shown = {name: canon(name) for name in SHAPES.values() if canon(name) != name}
    return {"discord.py": PINNED, "aliases": dict(sorted(shown.items())), "types": dict(sorted(types.items()))}


def _dumps(pin: dict[str, Any]) -> str:
    """One type per line, so a drift reads as a one-line diff."""
    types = ",\n".join(f"  {json.dumps(name)}: {json.dumps(spec, sort_keys=True)}" for name, spec in pin["types"].items())
    return f'{{"discord.py": {json.dumps(pin["discord.py"])}, "aliases": {json.dumps(pin["aliases"])}, "types": {{\n{types}\n}}}}\n'


@cache
def vendored() -> dict[str, Any]:
    return json.loads(VENDORED.read_text(encoding="utf-8"))


def missing(type_name: str, payload: Any, path: str = "") -> list[str]:
    """The required keys ``payload`` lacks for ``type_name``, apart from `EXEMPT`, in it and every typed object nested in it (`UNIONS` too)."""
    pin = vendored()
    type_name = pin["aliases"].get(type_name, type_name)
    spec = pin["types"][type_name]
    if not isinstance(payload, dict):
        return [path.rstrip(".") or "(not an object)"]
    out = [path + key for key in spec["required"] if key not in payload and key not in EXEMPT.get(type_name, {})]
    for key, nested in {**spec["nested"], **UNIONS.get(type_name, {})}.items():
        value = payload.get(key)
        items = value if nested.endswith("[]") and isinstance(value, list) else [value]
        for item in items:
            if item is not None:
                out += missing(nested.removesuffix("[]"), item, f"{path}{key}.")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail unless discord_types.json matches the installed discord.py")
    args = parser.parse_args(argv)
    try:
        version = importlib.metadata.version("discord.py")
    except importlib.metadata.PackageNotFoundError:
        print("discord.py is not installed", file=sys.stderr)
        return 2
    if version != PINNED:
        print(f"discord.py {version} is installed; the pin is {PINNED}", file=sys.stderr)
        return 1
    spec = importlib.util.find_spec("discord")
    assert spec is not None and spec.submodule_search_locations
    generated = generate(Path(spec.submodule_search_locations[0]) / "types")
    if not args.check:
        VENDORED.write_text(_dumps(generated), encoding="utf-8")
        print(f"wrote {VENDORED} ({len(generated['types'])} types)")
        return 0
    current = json.loads(VENDORED.read_text(encoding="utf-8"))
    drift = sorted(n for n in set(generated["types"]) | set(current["types"]) if generated["types"].get(n) != current["types"].get(n))
    if drift or generated != current:
        print(f"discord_types.json has drifted from discord.py {version}: {', '.join(drift) or 'aliases'}", file=sys.stderr)
        return 1
    print(f"discord_types.json matches discord.py {version} ({len(current['types'])} types)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
