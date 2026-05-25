import json


def provider_env(verdict, *, checked, reasons=None, confidences=None, model=None):
    default_confidences = {candidate: 0.05 for candidate in ("PASS", "ACK", "ASK", "SPEAK")}
    default_confidences[verdict] = 0.85
    payload = {
        "verdict": verdict,
        "confidences": confidences or default_confidences,
        "context_checked": list(checked),
        "reasons": reasons or [f"Fixture provider selected {verdict}."],
    }
    env = {"TURNAWARE_CLASSIFIER_TEST_RESULT": json.dumps(payload)}
    if model is not None:
        env["TURNAWARE_CLASSIFIER_MODEL"] = model
    return env


def fixture_case(fixture_name, verdict, *, checked=None, reasons=None, confidences=None):
    checked = checked or [f"trigger:trigger-{fixture_name}"]
    return provider_env(verdict, checked=checked, reasons=reasons, confidences=confidences)
