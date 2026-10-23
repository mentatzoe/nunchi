# Approved social scenes

**42 approved specifications, published 2026-10-23.** This is the reviewed scene
collection for the next evaluation-design session. It supersedes the raw scene
ideas and earlier generated drafts as the authoring baseline. The older runnable
fixtures remain in `evals/`; they have not been converted into this collection.

Start with [Social behavior](../../../AGENTS.md#social-behavior), the
[scene spec](../scene-spec.md), and the [evaluation-design handoff](../eval-design-handoff.md).
For authoring or revision, use the [Nunchi scenes skill](../../../skills/nunchi-scenes/SKILL.md).

## Reading the collection

Each scene has a readable `scene.md` and a structured `scene.json` containing the
same approved fields, transcript and timeline. Its JSON artifacts are linked
beside the relevant capture. `index.json` lists the collection; each scene's
artifact entries include SHA-256 hashes of the saved JSON files. This is a
publication format, not a runner contract or a scoring schema.

Scene numbers preserve their review identity, so gaps are intentional. Scene 51,
*An old joke returns during an introduction*, was discarded and is excluded.
The 42 retained scenes and their saved artifacts were exported from their final
approved tabs without rewriting the situations, dialogue, outcomes or model
results. Private source conversations and review comment histories are not part
of this collection.

The four scene parts remain description; static components; dynamic participant
and frozen library; purpose and outcomes. Separate situation, tension and
behavior fields elaborate the description. Blank outcome fields are intentional
where the scene observes what emerges; they do not invite invented ideal replies.

## Preparation is not evaluation

All scenes pin Nunchi 2.0.0 at
`365c0d966019c29f601362e62aec9e20f0beea50`. The 180 JSON files retain the actual
configuration and preparation results from the installed library. There are 44
attention captures, five later room-update artifacts and one older-context
artifact. No protagonist was run, and these outputs are neither reference answers
nor proof that the library works socially.

Attention decisions, including failures, are preserved. A `null` participant
request means the saved decision suppressed activation. DEFER still supplies a
participant turn in this pinned library; it is not interchangeable with SUPPRESS.
Continuation artifacts keep later messages outside the opening snapshot. See the
[handoff](../eval-design-handoff.md) for known findings and runtime limitations.

## Scenes

| ID | Approved scene | Revision |
| --- | --- | --- |
| 03 | [Story across messages](03-story-across-messages/scene.md) | 0.4 |
| 06 | [Never mind while composing](06-never-mind-while-composing/scene.md) | 0.2 |
| 07 | [Addressed, but a peer answers](07-addressed-but-a-peer-answers/scene.md) | 0.6 |
| 08 | [A complaint reopens an unanswered question](08-a-complaint-reopens-an-unanswered-question/scene.md) | 0.4 |
| 13 | [Another question while answering](13-another-question-while-answering/scene.md) | 0.2 |
| 14 | [Venting without wanting solutions](14-venting-without-wanting-solutions/scene.md) | 0.3 |
| 15 | [Technical thinking aloud, no solutions yet](15-technical-thinking-aloud-no-solutions-yet/scene.md) | 0.4 |
| 16 | [A peer fulfils your commitment](16-a-peer-fulfils-your-commitment/scene.md) | 0.7 |
| 17 | [A nod leaves a complaint unsettled](17-a-nod-leaves-a-complaint-unsettled/scene.md) | 0.4 |
| 18 | [A complaint about not being heard](18-a-complaint-about-not-being-heard/scene.md) | 0.1 |
| 21 | [A matter of taste treated as settled](21-a-matter-of-taste-treated-as-settled/scene.md) | 0.2 |
| 22 | [An announcement that shares relief](22-an-announcement-that-shares-relief/scene.md) | 0.1 |
| 23 | [Someone else explains the protagonist's choice](23-someone-else-explains-the-protagonist-s-choice/scene.md) | 0.1 |
| 24 | [Teasing or a hint to be brief](24-teasing-or-a-hint-to-be-brief/scene.md) | 0.3 |
| 25 | [Enthusiasm taken as volunteering](25-enthusiasm-taken-as-volunteering/scene.md) | 0.3 |
| 26 | [A joke about uneven praise](26-a-joke-about-uneven-praise/scene.md) | 0.3 |
| 27 | [A request interrupts a personal disclosure](27-a-request-interrupts-a-personal-disclosure/scene.md) | 0.3 |
| 29 | [A confident wrong answer](29-a-confident-wrong-answer/scene.md) | 0.2 |
| 30 | [Returning without the joke’s context](30-returning-without-the-joke-s-context/scene.md) | 0.4 |
| 31 | [Asked to take a side](31-asked-to-take-a-side/scene.md) | 0.3 |
| 32 | [Receiving familiar teasing](32-receiving-familiar-teasing/scene.md) | 0.5 |
| 33 | [Asked to interpret someone who is present](33-asked-to-interpret-someone-who-is-present/scene.md) | 0.3 |
| 34 | [A newcomer asks whether they are interrupting](34-a-newcomer-asks-whether-they-are-interrupting/scene.md) | 0.3 |
| 35 | [Opening up, then changing the subject](35-opening-up-then-changing-the-subject/scene.md) | 0.3 |
| 36 | [Seeking support through an explanation](36-seeking-support-through-an-explanation/scene.md) | 0.4 |
| 37 | [A shared joke gains a new participant](37-a-shared-joke-gains-a-new-participant/scene.md) | 0.1 |
| 38 | [A peer starts judging shared play](38-a-peer-starts-judging-shared-play/scene.md) | 0.3 |
| 39 | [A peer invites teasing about someone present](39-a-peer-invites-teasing-about-someone-present/scene.md) | 0.4 |
| 40 | [A disagreement becomes a personal dismissal](40-a-disagreement-becomes-a-personal-dismissal/scene.md) | 0.2 |
| 42 | [Conceding to leave an argument](42-conceding-to-leave-an-argument/scene.md) | 0.3 |
| 43 | [Playful appreciation lands as dismissal](43-playful-appreciation-lands-as-dismissal/scene.md) | 0.3 |
| 44 | [Bystander asked to confirm victory](44-bystander-asked-to-confirm-victory/scene.md) | 0.2 |
| 45 | [Claiming another’s consent through familiarity](45-claiming-another-s-consent-through-familiarity/scene.md) | 0.4 |
| 46 | [An absent person becomes the target](46-an-absent-person-becomes-the-target/scene.md) | 0.3 |
| 47 | [Pressed to take the prank public](47-pressed-to-take-the-prank-public/scene.md) | 0.7 |
| 48 | [A boss claim interrupts your turn](48-a-boss-claim-interrupts-your-turn/scene.md) | 0.3 |
| 49 | [A newcomer adds an insult to teasing](49-a-newcomer-adds-an-insult-to-teasing/scene.md) | 0.2 |
| 50 | [A peer fulfils your commitment during your turn](50-a-peer-fulfils-your-commitment-during-your-turn/scene.md) | 0.4 |
| 52 | [A bystander hears a concession](52-a-bystander-hears-a-concession/scene.md) | 0.1 |
| 53 | [A newcomer is talked past](53-a-newcomer-is-talked-past/scene.md) | 0.2 |
| 54 | [A newcomer responds to silence](54-a-newcomer-responds-to-silence/scene.md) | 0.2 |
| 55 | [An authority claim is already contested](55-an-authority-claim-is-already-contested/scene.md) | 0.1 |
