# Validation evidence

These files demonstrate that the v0.1 implementation runs. They do not establish a language effect or a general defense success rate.

- `mock-demo-report.md`: 144 deterministic mock calls, two fixture names, six development questions. **Not model performance.** Mock normal responses are placeholders.
- `qwen3-smoke/`: 12 real local inference calls using `qwen3:8b`, one synthetic development question, four input conditions, three defenses, one repeat. No provider errors. All raw inputs/outputs, frozen configuration and model digest are included. Human labels remain blank.

The real smoke run returned the expected factual answer in all twelve calls and did not meet the injection target. This is only a wiring check: with one question, one template and one repetition it supports no conclusion about Chinese versus English robustness. No test-split inference was performed.

Validation on Windows with Python 3.12: nine automated tests passed. GitHub Actions is configured separately for Python 3.10 and 3.12; a workflow definition alone is not evidence that remote CI has passed.

Reproduce from the project directory with a fresh output path:

```powershell
python -m bench run --lock examples/qwen3-smoke/lock.json --out runs/reproduced-smoke
```

This requires the same source hash and an installed `qwen3:8b` model. Compare its weight digest with `model.json`; model name equality is insufficient. Hardware/runtime changes may alter outputs even with the same seed.
