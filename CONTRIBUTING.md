# Contributing

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov
```

No service is needed. `VTEL_TEST_DRAWS` and `VTEL_TEST_SEED` run the same tests with more (or different) random logs
(CI also uses 150 logs with seed 11).

Rules that keep the project honest:

- **A change to the analysis needs both implementations.** Change `pipeline.py` (vectorised) and `reference.py` (plain loops) the
  same way, add a hand-computed case to `tests/test_pipeline.py` (it runs through both), and let `vtel verify` compare them.
- **A new detector needs a truth.** Inject the fault in `generate.py`, record it in the truth, and score it in `score.py`.
- **Numbers in the README and `docs/analysis.md` come from `docs/report.json` and `docs/bench.json`**, and `tests/test_docs.py` checks
  them. After a change to the generator or the analysis, regenerate them (`vtel analyze --out`, then `tools/run_full.ps1` for the
  benchmark) and update the text where a number moved.
- **The demo log must not depend on the NumPy version.** It is identical with NumPy 2.4 and 2.5; keep it that way (use the
  `Generator` methods already in use, and round to whole milliseconds).
