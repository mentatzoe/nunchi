"""Behavioral evaluation: does a participant read the room? (#86)

`docs/behavior.md` defines the behavior. This suite checks it with
conversations and real models, not deterministic stubs.

A scene is a short conversation plus one or more moments to judge. Each
moment lists what a socially aware participant would notice, the moves that
fit, and the moves that clearly miss. Fitting is a range, not one answer:
different models may pick different fitting moves, and that spread is part of
what a run reports.

- `scene.py` loads and checks scene files.
- `litmus.py` converts the V1 litmus corpus into draft scenes.
- `score.py` grades what today's V2 did against a moment.
- `run.py` runs scenes against OpenAI-compatible models and writes a report.
"""
