# Platform host snippet

Nunchi V2 belongs in deterministic host code, not in participant standing
instructions or a pre-send hook.

```python
result = pipeline.handle_delivery(
    delivery_id=native_delivery_id,
    event=canonical_event,
    actors=canonical_actor_map,
    authorized_route=trusted_router_accepts_room,
)
```

The host supplies exact participant binding, a pinned profile, delegated
attention model, normal participant, stable receipt/observation paths, and
native transport. The participant receives a wake only after the shared
pipeline decides WAKE, DEFER, bypass, or configured error fallback. It returns
one action or silence. It never calls room transport around the host.

See [`docs/platform-v2.md`](../docs/platform-v2.md) for the complete interface
and conformance requirements.
