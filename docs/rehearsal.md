# Reference participant rehearsals

These tools exercise `nunchi-discord`, the standalone reference participant,
on a local Discord stand-in. They do not run Claude Code, Codex or Hermes and
do not show what a user of those harnesses would experience. The harness
rehearsals and their manual workflow have been removed with those integrations.

The reference's current turn and delivery mechanisms remain under architecture
review. A passing rehearsal checks those mechanisms; it does not approve them
as the library's design.

## Run a scripted rehearsal

The full Discord rehearsal needs a disposable Linux environment with `sudo`,
network namespaces, `unshare`, `mount`, `openssl`, and Python 3.12 or later. Install Nunchi
and the reference's pinned Discord dependencies in a virtual environment:

```sh
python3 -m venv /tmp/nunchi-reference-env
/tmp/nunchi-reference-env/bin/python -m pip install . discord.py==2.7.1 aiohttp==3.14.3
sudo -E /tmp/nunchi-reference-env/bin/python -m evals.rehearsal.discord_net --offline -- \
  /tmp/nunchi-reference-env/bin/python -m evals.rehearsal.probe \
  --harness reference --scripted --out /tmp/nunchi-reference-out
```

Run from the repository root: the rehearsal modules live in this checkout.
Use a new output directory for each run; the probe replaces its
`<out>/reference/` directory. The launcher maps Discord's names to its test
server in a private network namespace and restores its temporary setup when
it exits. `--offline` disables external networking. No Discord account or
provider credentials are needed.

The default script checks startup, a bot status message, a direct question,
a reply, a reaction across reconnect, and a thread question. Add
`--scene story-across-messages` to play one supported legacy behavior fixture.
The director can also hold a scripted model response while more messages
arrive, or have the reference produce an earlier line specified by the fixture.
Run `python3 -m evals.rehearsal.probe --help` for the remaining options.

## Live model runs

A live run uses the same reference participant and test Discord server, with
OpenRouter models for attention and participation. It still does not run an
agent harness. Live runs require explicit authorization and credentials.
There is no live rehearsal workflow to dispatch.

The existing launcher permits live scenes only on a disposable GitHub Actions
runner with `CI=true` and `GITHUB_ACTIONS=true`. Run the launcher without `--offline`, and the probe with `--scene`,
`--agent-model`, `--attention-model` and `--budget-usd`, without `--scripted`.
Set `NUNCHI_ATTENTION_API_KEY` and `NUNCHI_PARTICIPANT_API_KEY` for the requested
providers. `--wheel` records the installed wheel's hash when supplied.

Live egress is open: the launcher isolates the Discord stand-in but does not
limit outgoing traffic to OpenRouter. The budget is a soft stop between
moments, not a cap on an individual call. Provider usage can arrive late; the
last reading may miss later charges. Model names, configuration, calls,
provider reports and spend readings belong in the run record.

## Read the result

`<out>/reference/summary.md` leads with the result and any failures.
`run.json`, receipts, model records and the Discord wire log provide the
underlying evidence.

- Scripted passes check known actions, attention routing, delivery, context
  and timing against a simulated server. They do not measure social judgment.
- Live grades describe behavior against legacy draft expectations. Grades
  are reported; delivery, recording and secret-scan failures fail the run.
- Reference receipt reconstruction cannot show everything a real agent saw.
  For example, a live timing hold can be recorded without proving that the
  participant read every intervening message. The record marks those limits.
- These fixtures are separate from the approved
  [scene specifications](evaluations/scenes/README.md). Neither their grades
  nor the old rehearsal history establishes acceptance of that collection.

Exit codes: `0` checks passed; `1` a check or execution failed; `2` invalid
arguments; `3` missing prerequisites; `4` stopped at the budget.

## Scan before publishing

The probe scans output for its keys and canary. Scan again before publishing,
with every credential the run used:

```sh
python3 -m evals.rehearsal.scan --out /tmp/nunchi-reference-out \
  --env NUNCHI_ATTENTION_API_KEY --env NUNCHI_PARTICIPANT_API_KEY
```

A hit deletes the records and leaves a notice naming affected files and
variables, without secret values. Do not upload outputs from an interrupted
run until its processes have stopped and this scan passes.
