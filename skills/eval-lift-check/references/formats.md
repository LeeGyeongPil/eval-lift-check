# Input formats

`compare.py` and `plan_n.py` detect the format from the extension and keys. `inputs[].format_detected` in the report says what was used. Pass `--format jsonl|csv|lm-eval|inspect|promptfoo` to be explicit.

## Contents

1. Generic JSONL / CSV / JSON list
2. lm-evaluation-harness
3. Inspect
4. promptfoo
5. Score values

## 1. Generic JSONL / CSV / JSON list

One row per item. Defaults: id field `id`, score field `score` (`--id-key`, `--score-key`). `--cluster-key` names a field that groups items. Duplicate ids follow `--dup`. Example row: `{"id": "p00-q3", "passage": "p00", "score": 1}`.

## 2. lm-evaluation-harness

Input: the files written by `--log_samples`, named `samples_<task>_<timestamp>.jsonl`, either one file or a folder (searched recursively). Key = `<task>/<doc_id>`, because `doc_id` restarts at 0 in every task. Per task the latest timestamp is used and a warning says so. The score field is `--metric` if given, otherwise the first entry of the row's `metrics` list, otherwise the first of `acc`, `exact_match`, `acc_norm`. If none is found the error `score-missing` lists the keys that were seen. When both runs carry `doc_hash` and the values differ, the item is a different question and is excluded (listed under `hash_mismatch`). With two or more tasks every comparison also gets `per_task` (items, means, difference, p and `p_holm_tasks`, the p adjusted with Holm over the tasks). These lines are secondary: the verdict is computed on all items pooled. The task is not a row field, so `--cluster-key task` stops with a message that explains why a few tasks are not clusters. Fields differ between lm-eval versions; the lm-eval fixtures used to test this skill (one task in the evaluation set, two tasks in the unit tests) are written by hand from the documented layout (https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/interface.md, checked 2026-11-27).

## 3. Inspect

Input: a JSON log (`--log-format json`, or the output of `inspect log dump FILE`) or a `.eval` archive. `.eval` files are zip archives whose `samples/*.json` members are read with the standard library. Recent versions compress members with zstd; Python 3.14 and newer can read them, older Pythons stop with `inspect-zstd` and the exact `inspect log dump` command. Key = sample `id`; `epoch` is read from each sample. `--metric` names the scorer (default: the first scorer of each sample). Values `C`, `I`, `P`, `N` become 1, 0, 0.5, 0.

Epochs: `--epochs mean` (default) averages the epochs of an item, which makes a 0/1 score continuous; `--epochs cluster` keeps every epoch as a row and uses the item as the cluster.

The real sample in `tests/fixtures/real/inspect_log.json` and `.eval` was produced with inspect_ai 0.3.292 and a deterministic scorer (no model call).

## 4. promptfoo

Input: `results.json` (rows under `results.results`) or `results.jsonl` (one row per line). Key = `testIdx`, or the variable named by `--id-key`. The score is `success`, else `gradingResult.pass`, else `pass`; `--score-key score` uses the numeric `score` instead. The field actually used is recorded in `inputs[].score_field`. A file with several prompts warns; select one with `--prompt-idx`. The real samples in `tests/fixtures/real/promptfoo_results.json` and `.jsonl` were produced with promptfoo 0.126.0 and the `echo` provider.

## 5. Score values

Accepted: booleans, numbers, the strings `true`/`false`, `yes`/`no`, `pass`/`fail`, `correct`/`incorrect`, `C`/`I`, and numeric strings. If every score is 0 or 1 the data is binary (exact McNemar), otherwise continuous (paired t). Anything else stops with `score-not-numeric` and names the row.
