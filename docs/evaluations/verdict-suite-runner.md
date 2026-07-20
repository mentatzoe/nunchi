# Archived V1 verdict runner

The V1 verdict runner is list-only. It validates and enumerates the historical
fixture/meta pairs without importing a product classifier or executing a V1
CLI:

```sh
python3 -m evals.verdict_suite.runner --list
```

Current evaluation belongs to [`v2.md`](v2.md). The V1 requirements and data
model are retained solely for historical traceability:

- [`../contracts/verdict-suite-requirements-v1.md`](../contracts/verdict-suite-requirements-v1.md)
- [`../contracts/verdict-suite-data-model-v1.md`](../contracts/verdict-suite-data-model-v1.md)
- [`../../evidence/verdict-suite/README.md`](../../evidence/verdict-suite/README.md)
