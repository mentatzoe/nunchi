# Starting evaluation design

The scene-authoring review is complete: 42 retained specifications are approved.
The [scene collection](scenes/README.md) is the starting material for a separate
evaluation-design session. No protagonist runs, scoring, new runner or framework
selection were part of this publication.

## Read first

1. [Social behavior](../../AGENTS.md#social-behavior) sets the product intent.
2. The [scene spec](scene-spec.md) defines what a scene contains and why.
3. The [approved collection](scenes/README.md) holds the situations, transcripts,
   outcomes and actual preparation artifacts.
4. The [scene-design skill](../../skills/nunchi-scenes/SKILL.md) preserves the
   lessons from authoring and review when a scene needs revision.

The approved high-level situations and purposes are settled. Concrete changes
must preserve those anchors and accumulated review decisions. Some scenes have
specific outcomes; others deliberately leave outcome fields blank to observe
what emerges. Do not fill those blanks with compulsory helpfulness, politeness,
reconciliation or a preferred interpretation.

`docs/behavior.md` remains a draft except for explicitly agreed statements.
Its unagreed prescriptions do not become evaluation criteria through this
publication; the authority order in `AGENTS.md` still applies.

## What the saved artifacts establish

All 42 scenes pin Nunchi 2.0.0 at
`365c0d966019c29f601362e62aec9e20f0beea50`. Their JSON was prepared using a
noneditable installed copy and `gpt-6-luna` at low reasoning through
`HostTextAttentionModel`. The JSON retains configuration, model-visible inputs,
actual attention output and the resulting participant request, where one exists.

There are 44 saved attention decisions: 21 WAKE, 22 DEFER and one SUPPRESS.
These are preparation observations, not expected labels, scores, or measurements
of reliability. No protagonist was invoked. A future run may produce another
reading; retain the saved output rather than resampling away a failure.

Read each timeline literally. Cold snapshots do not imply generated prior turns.
Authored protagonist messages are setup, not evidence of a previous model's
behavior. A pause does not prove activation. Continuing-conversation scenes keep
their opening input separate from later room updates; older retrievable context
is also separate. Preserve these visibility boundaries when designing execution.
Receiving an update and choosing to use it are distinct observations. A redundant
context fetch is not required when the full update was already delivered.

## Known findings and runtime limits

- [Issue #218](https://github.com/mentatzoe/nunchi/issues/218) records scene 46's
  SUPPRESS result. The model described an absent-person exchange as unkind and
  private-feeling and rated it low as conversation. The saved participant request
  is `null`. This is one observed gate failure, not proof of a categorical code
  rule or a requirement that the protagonist defend someone.
- In [scene 32](scenes/32-receiving-familiar-teasing/scene.md), attention assigns
  the teasing remark to `someone_else` with probability 0.9 even though Hermes
  is the protagonist being teased. The actual output remains intact. Scene
  approval does not endorse that classification.
- Fifteen scenes designate Hermes as protagonist with integration `TBD`.
  Codex and Claude Code runtime/version fields also describe approved scene
  targets, not verified execution support. All supplied harness integrations
  have since been retired. Preserve the approved casting while resolving
  execution support explicitly. The saved preparation and continuation tabs
  do not prove live update delivery or protagonist use.

## What remains for the separate session

Evaluation design must establish how to run the installed library and production
participants, observe activations and later updates, judge behavior, and report
uncertainty and failures. The earlier conversation runners, fixtures and scoring have been removed;
Git retains them. Their fixed move expectations and rubrics do not decide the
new design. Isolated component tests remain, but do not execute this collection.

Keep scene purpose separate from measurement choices. The scene-spec question
about when context-delivery assertions belong in ordinary tests remains open;
publishing the scenarios does not settle that boundary or choose a framework.
