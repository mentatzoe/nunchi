# Quickstart: Admission Classifier Completion

These commands are the intended verification evidence for the TUR-11 slice once tasks are implemented.

## 1. Install from a clean environment

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
turnaware --help
```

## 2. Run deterministic provider-fixture tests

```sh
python -m unittest
```

Expected coverage includes:
- representative PASS, ACK, ASK, SPEAK;
- false ACK guard for `comment back with results` assignment text;
- false PASS guard for resolved-looking trigger plus contradictory missing-work context;
- invalid classifier configuration with no silent fallback;
- CLI/core contract equivalence.

## 3. Verify selected classifier/provider identity in CLI output

Product/default path evidence with a real provider requires model and API-key configuration:

```sh
export TURNAWARE_CLASSIFIER_MODEL="your/provider-model"
export OPENROUTER_API_KEY="..."
turnaware admit --input tests/fixtures/speak.json
```

Offline deterministic evidence uses the product path with a fixture provider result, not a `deterministic` classifier:

```sh
TURNAWARE_CLASSIFIER_TEST_RESULT='{"verdict":"SPEAK","confidences":{"PASS":0.05,"ACK":0.05,"ASK":0.05,"SPEAK":0.85},"context_checked":["trigger:trigger-speak"],"reasons":["Fixture provider selected SPEAK."]}' \
turnaware admit --input tests/fixtures/speak.json
```

Expected result shape:
- JSON stdout;
- exit 0 when the selected path is configured and available;
- `classifier` identifies `product`;
- `classifier_provider` and `classifier_model` identify the provider/fixture transport used;
- `verdict` is one of PASS/ACK/ASK/SPEAK;
- no reply/draft/message prose fields.

If the product/default path is not configured in the test environment, the first command must fail clearly and must not silently use deterministic/local fallback behavior.

## 4. Verify known false ACK case

```sh
TURNAWARE_CLASSIFIER_TEST_RESULT='{"verdict":"SPEAK","confidences":{"PASS":0.05,"ACK":0.05,"ASK":0.05,"SPEAK":0.85},"context_checked":["trigger:trigger-false-ack-comment-back","context:ctx-false-ack-assignment"],"reasons":["Provider inspected assignment context and rejected ACK."]}' \
turnaware admit --input tests/fixtures/false_ack_comment_back.json
```

Expected:
- verdict is `SPEAK`, not `ACK`;
- reasons explain substantive assignment/work, not visible acknowledgement;
- context evidence names inspected assignment material truthfully.

## 5. Verify known false PASS case

```sh
TURNAWARE_CLASSIFIER_TEST_RESULT='{"verdict":"SPEAK","confidences":{"PASS":0.05,"ACK":0.05,"ASK":0.20,"SPEAK":0.70},"context_checked":["trigger:trigger-false-pass-contradicted-done","context:ctx-false-pass-missing-work"],"reasons":["Provider found contradicted missing-work evidence before allowing PASS."]}' \
turnaware admit --input tests/fixtures/false_pass_contradicted_done.json
```

Expected:
- verdict is not `PASS`;
- contradictory missing-work/evidence context is present in `context_checked` or equivalent audit evidence;
- confidence/reasons reflect conflict rather than high-confidence fake done.

## 6. Verify invalid classifier failure

```sh
turnaware admit --classifier does-not-exist --input tests/fixtures/speak.json
```

Expected:
- non-zero exit;
- clear stderr error;
- no successful admission result;
- no silent fallback to local/default classifier behavior.
