# Quickstart: Core CLI MVP

> **Historical archive:** commands use the retired TurnAware package name and
> are preserved from SpecKit feature `001`; they are not current instructions.

## Run With stdin

```sh
PYTHONPATH=src python3 -m turnaware admit < tests/fixtures/speak.json
```

Expected behavior: stdout contains one JSON object with `"verdict": "SPEAK"` and audit fields.

## Run With a File

```sh
PYTHONPATH=src python3 -m turnaware admit --input tests/fixtures/pass.json
```

Expected behavior: stdout contains one JSON object with `"verdict": "PASS"` and no reply-message fields.

## Verify the Suite

```sh
python3 -m unittest
```

The suite must cover all four verdict fixtures, schema shape, PASS hard-stop behavior, truthful `context_checked`, stdin/file parity, and invalid input failures.

## Failure Example

```sh
printf '{}' | PYTHONPATH=src python3 -m turnaware admit
```

Expected behavior: stderr contains a validation diagnostic, stdout does not contain a success verdict, and the process exits with status `3`.

## Scope

This quickstart covers the runnable CLI and internal core only. Downstream adapters, reply composition, central orchestration, and live provider evaluation are intentionally outside this MVP.
