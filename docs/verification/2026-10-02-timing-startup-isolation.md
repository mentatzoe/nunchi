# Journal timing, native startup and installed-probe isolation

Implemented and verified locally; independent exact-artifact review is required before integration. This closes the three follow-up areas assigned to `t_17bbbfd5`, not whole-V2 release or live adoption. Base: reviewed `7351a91a136e93bebbaf8e07825857fccbf15396`.

## Repairs and red evidence

### Journal contention

The canonical failure is not exclusively prior-test pollution. The original journal also fails alone on this machine. Profiling found only the main thread alive. SQLite's busy handler counts requested sleep durations, not elapsed scheduler time: an isolated 250 ms busy timeout took 1.318 seconds; two blocked operations exceeded the unchanged two-second assertion. Evidence: `red-canonical.txt`, `isolated-journal.txt`, `profile-canonical.txt`, `sqlite-timing.txt`.

The plugin now disables SQLite's built-in busy waiting and shares a 250 ms monotonic contention budget across connection PRAGMA/schema access, `BEGIN IMMEDIATE`, and commit. Native effects and SQL mutations are not retried. Commit retries retain the same transaction; exhausted/error paths roll back and fail closed. Durable duplicate claims and unknown-effect semantics remain unchanged. This bounds contention waiting, not arbitrary filesystem latency or OS suspension.

A scheduler-delay regression fails before the repair. Broader testing caught two incomplete intermediate repairs: PRAGMA can meet an exclusive writer, and commit can meet a reader. Dedicated real-SQLite regressions reproduce both and pass with the final implementation. Failed intermediate runs remain in `candidate1-final-focused.txt`, `candidate2-focused-failure.txt`, `red-journal-setup.txt` and `red-journal-commit.txt`.

The inherited transient-contention test assumed a nominal 50 ms sleep could never exceed the 250 ms budget. Under concurrent installed-host tests it did, correctly causing fail-closed expiry (`focused-scheduler-overrun.txt`). The test now releases the real lock at the first busy retry, without increasing any timeout or replacing SQLite. Real-thread distinct native-call concurrency remains covered separately. Persistent contention still must finish under the original two-second assertion. Ten journal/native-tool stress runs passed before this test-only scheduling correction.

### Native startup

The plugin connection wrapper now forwards exactly the native keyword arguments instead of accepting only `is_reconnect`. Release startup's `initial=True` reaches its native cold-start timeout selector; omitted keywords still use the minimum host's defaults. Unsupported options remain the native signature's responsibility. Existing native profile ownership is never overwritten.

The new installed test executes actual `GatewayRunner.start()`, native adapter creation, wiring, ownership and connection-budget selection, plus reconnect. It runs separately in one-profile and real two-profile multiplex topologies on both stock hosts. Assertions check handler/auth/store wiring, default and secondary owners, cold-start/reconnect flags, and no external-connect attempts. The factory wrapper calls the native factory and replaces only each returned instance's network `connect`; independently running services and the optional Tirith downloader are explicit doubles.

The old release wheel fails the corrected initial startup fixture (`red-startup-release-corrected.txt`); the old minimum succeeds. Early fixture mistakes are retained, not product evidence. In particular, the first multiplex fixture patched one class, but release loads fresh per-profile classes: the secondary adapter attempted a Discord login with a synthetic, invalid token and received 401 (`green-startup-release-multiplex.txt`). No real credentials were used. The corrected fixture doubles every returned instance and forbids external socket connections. That guard also caught the stock optional binary downloader (`startup-download-blocked.txt`, `startup-network-trace.txt`); its installation entry point is now doubled before tool bootstrap. These failed probes are not authenticated live-platform validation.

### Native-tool repeatability

The old installed release fixture failed two of ten repeated full normal/attention runs. Captured requests in `repeat-red-9.txt` and `.requests.json` identify the extra request as the earlier cancellation test's `start something`, not the current peer-bot turn. Native logs show streaming interrupted before delivery followed by a delayed HTTP retry on `hermes-gateway_0`.

`ProbeHost.close()` previously closed stores without stopping/draining its gateway-owned executors. An asyncio session's cancellation does not stop its worker thread. That thread could consume a subsequent test's shared HTTP response script. Cleanup now uses native executor shutdown and waits for captured turn/housekeeping pools before closing storage, resetting scripts or unloading hooks. The controlled live-thread cleanup regression is red before and green after (`red-cleanup.txt`, `green-cleanup.txt`). No production retry policy, tools, native approval or call-count assertion was relaxed. The original author's exact 2-versus-3 native-tool assertion was not reproduced in the same test here; the same cross-test request leak was observed as 1-versus-2 in later turns. Request identity, native retry logs, cleanup regression and repeated full suites ground the diagnosis rather than a single rerun.

## Verification and reproduction

Evidence and runnable helpers are in the task workspace and attached evidence archive:
`/Users/zmll/.hermes/kanban/boards/nunchi-v2/workspaces/t_17bbbfd5/`.

- Full canonical: 766 tests, 30 explicitly gated installed-host skips, pass. Both final runs pass. These skips are not counted as installed validation.
- Focused boundary suite: 179 tests, pass, no skips.
- Evaluation listing: 11 V2 lifecycle scenarios; no live model evaluation claimed.
- Exact final wheel on minimum 0.19.0/Python 3.11 and release 0.21.5/Python 3.13: normal+attention 32/32 each, Discord/Telegram contracts 4/4 each, and single/multiplex native startup 1/1 each; no skips.
- Repeat-run logs and completed-run counts are enumerated in the companion manifest. Earlier candidate passes and failures are retained separately from final-wheel results.
- Stock integrity: 58 wheel payload members match source and both noneditable installs; all 942 minimum and 15 release host RECORD hashes verify. Stock source trees remain clean with original source digests. Before/after installed integrity matches.

Commands from the evidence workspace (create equivalent private environments when reproducing elsewhere):

```sh
python3 run_canonical.py canonical
python3 run_final.py minimum
python3 run_final.py release
python3 verify_followup.py artifacts/final/nunchi-2.0.0-py3-none-any.whl verify
# Repeat with distinct evidence labels; fail immediately on a failed suite.
python3 run_probe.py stock/release/.venv/bin/python repeat-1 \
  tests.v2.test_hermes_normal_turn tests.v2.test_hermes_attention_setup_installed
```

Canonical uses the normal repository test discovery and source imports. Installed probes run copied tests-only staging with `-I`, an environment allowlist, temporary homes and no product-source/PYTHONPATH dependency. The minimum dependency environment was privately copied then the wheel reinstalled; release dependencies were independently synced with its locked messaging extra. Stock source Git commits are local archive-integrity baselines, not upstream commit provenance. See prior verification reports for the original stock artifacts.

Final wheel SHA-256: `39ed326fbe352ab750c29bca3602841187bf4fe95c0b86506743063a3f832066`. The companion manifest records the exact final source commit, wheel and evidence digests.

No owner/author environments, live configuration/profiles/credentials, gateway signals, GitHub writes or `t_8df36093` work. No public-main host, live-model evaluation, authenticated real-platform interaction, CI publication, merge or adoption is claimed. The release stock emits its existing SQLite WAL-reset warning and selects DELETE journalling; no host patch was applied. Tool bootstrap in earlier normal-turn fixtures may perform stock optional downloads; final startup explicitly suppresses those services and enforces the socket guard.

Author runtime route: `openai-codex / gpt-6-astra`, from this session. Reviewer must record their actual runtime route; a profile name is not cross-family evidence. Owner `t_7041b201` retains integration, CI, publication and adoption responsibility after the separate developer-b review child completes.
