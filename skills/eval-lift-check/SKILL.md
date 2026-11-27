---
name: eval-lift-check
description: Pairs per-item results of two or more eval runs by item id and decides with bundled scripts whether the candidate really beats the baseline (exact McNemar or paired t, bootstrap and cluster-robust intervals, Holm correction, required sample size), returning one verdict - improved, regressed, bounded-null or underpowered. Reads JSONL, CSV, lm-evaluation-harness samples, Inspect logs and promptfoo results. Use when someone re-ran an eval after changing a prompt, model, checkpoint or skill and asks whether the gain is real or significant, wants to write that an eval result improved, asks how many eval items are needed, or compares several variants against a baseline. Not for scoring a single run, writing judge rubrics, judge-human agreement, running evals, fixed-threshold CI gates, or independent-sample A/B tests.
license: MIT
compatibility: Python 3.10+ (standard library only). No network access.
---

# Eval lift check

Two accuracy numbers side by side do not say whether B beat A. The same questions were asked twice, so only the items where the runs disagree carry information. Doing this by hand gives the wrong test (for example an unpaired z test) and invented p values, so run the scripts and quote their output.

## Scripts

**Always run the bundled script for the numbers. Do not compute them yourself** - not in your head, not with a formula from the references, not with your own Python, not by reading the script source and re-doing its steps. The answer quotes the numbers, method and assumptions the script printed.

| Question | Script |
|---|---|
| Did B beat A? Is the gain real? Which variants beat the baseline? | `scripts/compare.py` |
| How many items do I need? Smallest detectable difference? Sizing from a pilot | `scripts/plan_n.py` |

Both are inside this skill's folder. Run them by their full path from the user's working folder; do not `cd` into the skill folder, because input paths and `--json` paths are relative to the folder you run in. Each command runs the script file itself and spells its path out so that it ends in `scripts/compare.py` or `scripts/plan_n.py`: do not `cd` into `scripts/` either, do not keep the folder in a shell variable, do not copy the scripts elsewhere, and do not import them from `python3 -c` or a heredoc. The examples below write them as `python3 scripts/compare.py ...`.

## Workflow

1. Find the per-item result files of both runs (not the summary). Ask for them if only averages exist: without item-level results nothing can be tested.
2. Run `python3 scripts/compare.py BASELINE CANDIDATE [CANDIDATE ...]` (full path, from the user's folder). It detects JSONL, CSV, lm-eval samples (file or folder), Inspect `.json`/`.eval` logs and promptfoo `results.json`/`.jsonl`. Use `--id-key`, `--score-key`, `--metric` when the fields differ. See `references/formats.md` for fields and known pitfalls.
3. Read the join diagnostics first and tell the user what they say: items missing on one side, duplicate ids, `doc_hash` mismatches, epochs per item. If the script stops with `duplicate-id`, show the ids and ask which policy is right when the user can answer. If nobody can answer (non-interactive run) or the user did not say, do not stop: re-run with `--dup first`, save the report anyway, and state the policy you used and that `--dup mean` is the alternative.
4. If items come in groups that share a source (several questions per passage, epochs of one item), pass `--cluster-key FIELD` (or `--epochs cluster`). Then the cluster-robust result is the primary one. With fewer than 10 clusters the script warns; prefer the cluster bootstrap interval.
   Do not cluster by benchmark task when there are only a few tasks: tasks are separate test sets, not a shared source.
   lm-eval with several tasks: pass both whole folders in one run; the verdict is pooled, per-task lines are Holm-adjusted and secondary (do not run tasks one by one and report the best).
   When the user asks for a saved report, add `--json report.json` (the path they named) to the same run whose numbers you quote, and do not overwrite it with an exploratory run. The script prints where it wrote the file.
5. Report using only numbers printed by the script: number of paired items, both means and the difference, the confidence interval with its method, p with its test name (Holm-adjusted p when there are several candidates), the disagreement counts, required N with method and assumptions, and the verdict word exactly as printed (`improved`, `regressed`, `bounded-null` or `underpowered`).
6. Before the evaluation, to size it, run `python3 scripts/plan_n.py --discordant-rate R --delta D` (or `--n N` for the smallest detectable difference). With pilot result files, let the script estimate R: `python3 scripts/plan_n.py --from-runs PILOT_A PILOT_B --delta 0.02` (add `--json plan.json` when a saved plan is wanted). Do not count disagreements or apply a formula by hand even when it looks simple. Quote the printed N*, method and assumptions; required N differs a lot between formulas.

## Verdicts and wording

- `improved` / `regressed`: p (Holm-adjusted for several candidates) is below alpha 0.05 and the sign of the difference decides which. Say "improved by X points (95% CI a to b, p = ...)".
- `bounded-null`: not significant and the whole 95% CI lies inside the margin (default 2 points for 0/1 scores). Say "any difference is smaller than the margin". For continuous scores this needs `--margin`.
- `underpowered`: everything else. Say "the data cannot tell", quote N* and N/N*, and never write "no difference" or "no improvement".
- Never write that an improvement is significant when the verdict is not `improved`. Never replace the script's p value with your own estimate. `p_unpaired_z_reference` in the JSON report is only a warning sign for people who compared averages; do not cite it as a result.
- Several candidates: only those marked `improved` after Holm correction may be called better than the baseline.

## Options worth knowing

`--json PATH` writes the full report (`-` prints only JSON). `--seed` and `--reps` control the bootstrap; the same input and seed give identical output. `--lang en|ko` or the `EVAL_LIFT_CHECK_LANG` variable picks the language; the JSON report has no translated text. `--alpha`, `--power`, `--margin` change the decision rules. Exit code 0 means the analysis ran (whatever the verdict), 2 means an input or usage problem, 3 means the join failed.

## Errors

If a script exits with an error, show the `error: <code>: ...` line as is (quote the code and the counts it prints): it says how to fix the input. When the user asks to keep the output, save stdout and stderr unedited (for example `> output.txt 2>&1`). When the join fails because almost no item ids are shared, check whether the two runs use different id schemes (for example `q-7` against `Q_0007`) and report that; do not invent numbers or p values. For `inspect-zstd`, run the `inspect log dump` command the message gives and pass the resulting `.json`.

The statistics, formulas and sources are in `references/statistics.md`.
