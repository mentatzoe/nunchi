# TurnAware

Pre-reply judgment for turn-aware agents.

TurnAware is a portable CLI/library for deciding whether an agent should visibly
participate on an unstructured shared surface before ordinary reply generation.
It returns an auditable admission verdict:

- `PASS` — hard stop; no ordinary visible reply
- `ACK` — brief acknowledgement is warranted
- `ASK` — clarification is warranted
- `SPEAK` — substantive contribution is warranted

## Status

Repository bootstrap is in progress. The product implementation has not shipped
yet. The first product slice is expected to be a vertical CLI release candidate,
not a collection of isolated internals.

## Product contract

The core output contract is:

- `trigger`
- `verdict`
- `confidences`
- `context_checked`

TurnAware owns admission, not composition. It does not draft the final reply and
it does not prescribe speech shape beyond the admission verdict.

## Development method

This repository uses Spec Kit. The constitution at
`.specify/memory/constitution.md` is the source of governance for all specs,
plans, tasks, implementation, documentation, and release claims.

For production work, use:

```text
constitution -> specify -> clarify -> checklist -> plan -> tasks -> analyze -> implement
```

The first product spec should prove an end-to-end runnable path from supplied
conversation context to a verdict a harness can obey.

## License

TurnAware is dual-licensed under MIT OR Apache-2.0, at your option. See
`LICENSE-MIT` and `LICENSE-APACHE`.
