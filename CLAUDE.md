# Nunchi Claude guidance

Follow `AGENTS.md`. Claude owns the Claude Code integration and security
assurance, not the shared V2 foundation or other platform implementations.

## Goal-first working style

Start from the product outcome, not the current mechanism. Treat inherited
design, version, installation, and process assumptions as changeable unless
Zoe explicitly fixed them. Bugs in an implementation are bugs to repair; they
are not proof that the approach is impossible.

Reviews must state what actually breaks, whether it prevents the goal, and the
smallest concrete fix. Documentation and status reports state the outcome
first, then the decision-changing technical facts. Keep the language concise,
plain, and technically exact. Avoid jargon, doublespeak, inflated severity,
and process theatre.

Before platform work:

1. start from current `integration/v2`;
2. confirm every declared upstream behavior is implemented, reviewed, and
   integrated;
3. read `docs/v2-completion-goal.md`, the selected design and contract, and the
   relevant reference specification;
4. inspect ordinary source and installed-runtime truth.

Use ordinary branches, commits, pull requests, tests, and runtime evidence.
There is no SpecKit workflow or slice lifecycle to operate. Planning artifacts
are reference material, not work authorization or evidence of completion.

Claude may implement only its owned platform surface and assurance tooling.
Security defects in another component return to that owner for repair. Because
Claude authors the Claude Code integration, Claude's own assessment cannot be
the independent review of that surface or of the final security candidate.

The core is Python 3.11+ and stdlib-only unless a reviewed product change says
otherwise. Run:

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

Live calls require explicit provider/platform credentials and must record the
installed candidate, identity, configuration, command, and complete result.
