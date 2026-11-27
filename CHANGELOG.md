# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-27

### Added
- `compare.py`: pairs per-item results of a baseline and one or more candidates by id and reports join diagnostics (missing, duplicate and hash-mismatched items, epochs).
- Exact McNemar test, paired t test, percentile bootstrap intervals (item and cluster), CRV1 cluster-robust standard error, Connor (1987) required sample size, minimum detectable difference and Holm correction, all with the standard library only.
- Verdicts `improved`, `regressed`, `bounded-null` and `underpowered`. `bounded-null` also needs an analytic check interval inside the margin (Tango score interval for 0/1 scores, t interval for continuous scores), so a few identical items are `underpowered`, not a tight null.
- Input adapters for JSONL, CSV, lm-evaluation-harness samples, Inspect JSON logs and `.eval` archives, and promptfoo results.
- lm-evaluation-harness runs with several tasks get a secondary per-task breakdown (`per_task`, Holm-adjusted over the tasks); the verdict stays the pooled one.
- Both scripts print the absolute path of the report written with `--json PATH`.
- `plan_n.py`: required number of items or minimum detectable difference before running an evaluation.
- English and Korean output (`--lang`, `EVAL_LIFT_CHECK_LANG`, locale variables); the JSON report is language independent.
- Agent skill `SKILL.md`, references, Claude Code plugin and marketplace manifests, evaluation set and fixtures.

### Known issues
- Korean README screenshots use a fallback font for some glyphs; the text is readable but the typeface differs from the English images.
- The README does not show a side-by-side comparison of the 304 / 432 / 4120 item examples; each is described on its own.
