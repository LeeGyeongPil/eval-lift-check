"""Regenerate the synthetic fixtures (seeded, deterministic).

Run from the repository root:  python3 tests/fixtures/make_fixtures.py

Everything written here is synthetic data made for this repository (MIT, like the rest).
The files under tests/fixtures/real/ are NOT produced here; they are real tool output.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals" / "fixtures"
TESTS = ROOT / "tests" / "fixtures"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- reading (clustered, one missing, one duplicate)
def make_reading(folder: Path) -> None:
    """60 passages x 5 questions. Run B is slightly better than run A, item for item.

    Run B is missing one item (p03-q2) and run A lists one item twice (p00-q3)."""
    rng = random.Random(7)
    a_rows, b_rows = [], []
    for p in range(60):
        difficulty = rng.gauss(0, 1.2)  # shared by the 5 questions of a passage
        for q in range(5):
            item = f"p{p:02d}-q{q}"
            base = 1 / (1 + math.exp(-(0.9 + difficulty + rng.gauss(0, 0.5))))
            a = 1 if rng.random() < base else 0
            if a == 1:
                b = 1 if rng.random() < 0.93 else 0
            else:
                b = 1 if rng.random() < 0.30 else 0
            a_rows.append({"id": item, "passage": f"p{p:02d}", "score": a})
            b_rows.append({"id": item, "passage": f"p{p:02d}", "score": b})
    b_rows.pop(17)
    a_rows.append(dict(a_rows[3]))
    write_jsonl(folder / "run_a.jsonl", a_rows)
    write_jsonl(folder / "run_b.jsonl", b_rows)


# ---------------------------------------------------------------- exact disagreement counts
def binary_pair(n: int, a_only: int, b_only: int, both_correct: int, seed: int):
    """Scores for n items where exactly a_only items only A gets right, b_only only B, both_correct both."""
    rng = random.Random(seed)
    order = list(range(n))
    rng.shuffle(order)
    a = [0] * n
    b = [0] * n
    for i in order[:a_only]:
        a[i] = 1
    for i in order[a_only:a_only + b_only]:
        b[i] = 1
    for i in order[a_only + b_only:a_only + b_only + both_correct]:
        a[i] = b[i] = 1
    return a, b


def write_pair(folder: Path, a: list[int], b: list[int], names=("run_a.jsonl", "run_b.jsonl"), prefix="q") -> None:
    write_jsonl(folder / names[0], [{"id": f"{prefix}{i:04d}", "score": s} for i, s in enumerate(a)])
    write_jsonl(folder / names[1], [{"id": f"{prefix}{i:04d}", "score": s} for i, s in enumerate(b)])


def make_verdict_fixtures() -> None:
    a, b = binary_pair(40, 3, 5, 25, seed=1)            # +5 points on 40 items
    write_pair(EVALS / "task-small-sample", a, b)
    write_pair(EVALS / "task-plan-n", a, b, names=("pilot_a.jsonl", "pilot_b.jsonl"))
    a, b = binary_pair(2000, 60, 62, 1500, seed=2)      # no real difference, many items
    write_pair(TESTS / "bounded_null", a, b)
    a, b = binary_pair(400, 40, 15, 280, seed=3)        # B is worse
    write_pair(TESTS / "regressed", a, b)
    a, b = binary_pair(300, 12, 40, 190, seed=4)        # clearly better
    write_pair(TESTS / "improved", a, b)


# ---------------------------------------------------------------- several candidates (promptfoo results.json)
def promptfoo_file(path: Path, scores: list[int]) -> None:
    rows = [{"promptIdx": 0, "testIdx": i, "success": bool(s), "score": s,
             "vars": {"q": f"question {i}"}} for i, s in enumerate(scores)]
    write_json(path, {"evalId": "synthetic", "results": {"version": 3, "results": rows}})


def make_holm_fixtures() -> None:
    rng = random.Random(11)
    base = [1 if rng.random() < 0.7 else 0 for _ in range(200)]
    ones = [i for i, s in enumerate(base) if s == 1]
    zeros = [i for i, s in enumerate(base) if s == 0]

    def variant(lost: int, gained: int, seed: int) -> list[int]:
        r = random.Random(seed)
        out = list(base)
        for i in r.sample(ones, lost):
            out[i] = 0
        for i in r.sample(zeros, gained):
            out[i] = 1
        return out

    folder = EVALS / "task-holm-variants"
    promptfoo_file(folder / "baseline.json", base)
    promptfoo_file(folder / "variant_a.json", variant(8, 30, 21))   # clearly better
    promptfoo_file(folder / "variant_b.json", variant(5, 15, 22))   # raw p ~0.04, not after Holm
    promptfoo_file(folder / "variant_c.json", variant(12, 10, 23))  # nothing


# ---------------------------------------------------------------- lm-eval folders
def lm_eval_rows(task: str, n: int, seed: int, better: bool) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for doc_id in range(n):
        right = rng.random() < 0.6
        if better:
            right = right or rng.random() < 0.3
        question = f"{task} question {doc_id}"
        rows.append({
            "doc_id": doc_id,
            "doc": {"question": question},
            "target": "a",
            "arguments": {"gen_args_0": {"arg_0": question, "arg_1": {}}},
            "resps": [[["a" if right else "b"]]],
            "filtered_resps": ["a" if right else "b"],
            "filter": "none",
            "metrics": ["acc"],
            "doc_hash": f"hash-{task}-{doc_id}",
            "prompt_hash": f"prompt-{task}-{doc_id}",
            "target_hash": "target-a",
            "acc": 1.0 if right else 0.0,
        })
    return rows


def make_lm_eval_single_task(base_dir: Path) -> None:
    """One task (quiz_mc), 80 docs: the evaluation-set case. The fine-tuned run lacks doc 79,
    and doc 7 has a different doc_hash (the question was edited between runs).

    On the 78 valid pairs exactly 6 items are right only in base and 13 only in ft
    (exact McNemar p = 0.167, not significant). Doc 7 is wrong in base and right in ft, so
    pairing it anyway gives 6 vs 14 and a different p (0.115): the exact p shows the exclusion."""
    stamp = "2026-01-01T00-00-00.000000"
    task = "quiz_mc"

    def set_acc(row: dict, right: bool) -> None:
        row["acc"] = 1.0 if right else 0.0
        row["resps"] = [[["a" if right else "b"]]]
        row["filtered_resps"] = ["a" if right else "b"]

    base = lm_eval_rows(task, 80, seed=51, better=False)
    set_acc(base[7], False)
    ft = [dict(row) for row in base]
    usable = [i for i in range(79) if i != 7]   # doc 79 is missing in ft, doc 7 is excluded
    rng = random.Random(52)
    for i in rng.sample([i for i in usable if base[i]["acc"] == 1.0], 6):
        set_acc(ft[i], False)                    # right only in base
    for i in rng.sample([i for i in usable if base[i]["acc"] == 0.0], 13):
        set_acc(ft[i], True)                     # right only in ft
    set_acc(ft[7], True)
    ft[7]["doc_hash"] = f"hash-{task}-7-edited"
    write_jsonl(base_dir / "base" / f"samples_{task}_{stamp}.jsonl", base)
    write_jsonl(base_dir / "ft" / f"samples_{task}_{stamp}.jsonl", ft[:79])


def make_lm_eval_fixtures(base_dir: Path) -> None:
    """Two tasks whose doc_id both start at 0. The candidate lacks taskA doc 59 and
    taskB doc 7 has a different doc_hash (the question text changed between runs).

    Used only by the unit tests (tests/fixtures/lm-eval-two-tasks/): the pooled verdict and
    the secondary per-task lines are checked deterministically there."""
    stamp = "2026-01-01T00-00-00.000000"
    for side, better in (("base", False), ("ft", True)):
        for task, n in (("taskA", 60), ("taskB", 40)):
            rows = lm_eval_rows(task, n, seed=31 if task == "taskA" else 32, better=False)
            if better:
                rng = random.Random(41 if task == "taskA" else 42)
                for row in rows:
                    if row["acc"] == 0.0 and rng.random() < 0.4:
                        row["acc"] = 1.0
                        row["resps"] = [[["a"]]]
                        row["filtered_resps"] = ["a"]
                    elif row["acc"] == 1.0 and rng.random() < 0.05:
                        row["acc"] = 0.0
                        row["resps"] = [[["b"]]]
                        row["filtered_resps"] = ["b"]
                if task == "taskA":
                    rows = rows[:59]
                else:
                    rows[7]["doc_hash"] = "hash-taskB-7-edited"
            write_jsonl(base_dir / side / f"samples_{task}_{stamp}.jsonl", rows)


# ---------------------------------------------------------------- inspect log with epochs (minimal, synthetic)
def make_inspect_epochs(folder: Path) -> None:
    """30 items x 3 epochs, rubric scores in [0, 1]; the candidate adds a small gain."""
    rng = random.Random(5)
    levels = {"base": 0.0, "cand": 0.04}
    ability = [rng.gauss(0.55, 0.15) for _ in range(30)]
    for side, gain in levels.items():
        samples = []
        for epoch in (1, 2, 3):
            for i in range(30):
                noise = random.Random(f"{side}-{i}-{epoch}").gauss(0, 0.15)
                other = random.Random(f"shared-{i}-{epoch}").gauss(0, 0.08)
                value = min(1.0, max(0.0, round(ability[i] + gain + noise + 0.2 * other, 2)))
                samples.append({"id": f"q{i:02d}", "epoch": epoch, "input": f"question {i}", "target": "a",
                                "scores": {"rubric": {"value": value, "answer": "a"}}, "metadata": {}})
        write_json(folder / f"{side}.json", {"version": 2, "status": "success",
                                              "eval": {"task": "rubric", "model": "mockllm/model"},
                                              "samples": samples})


# ---------------------------------------------------------------- continuous rubric scores with clusters (jsonl)
def make_rubric(folder: Path) -> None:
    rng = random.Random(9)
    a_rows, b_rows = [], []
    for p in range(30):
        shift = rng.gauss(0, 0.12)
        for q in range(4):
            base = min(1.0, max(0.0, round(0.6 + shift + rng.gauss(0, 0.1), 2)))
            gain = min(1.0, max(0.0, round(base + 0.04 + 0.5 * shift + rng.gauss(0, 0.05), 2)))
            a_rows.append({"id": f"p{p:02d}-q{q}", "passage": f"p{p:02d}", "score": base})
            b_rows.append({"id": f"p{p:02d}-q{q}", "passage": f"p{p:02d}", "score": gain})
    write_jsonl(folder / "run_a.jsonl", a_rows)
    write_jsonl(folder / "run_b.jsonl", b_rows)


# ---------------------------------------------------------------- error path: ids that never overlap
def make_no_overlap(folder: Path) -> None:
    write_jsonl(folder / "run_a.jsonl", [{"id": f"case-{i}", "score": i % 2} for i in range(20)])
    write_jsonl(folder / "run_b.jsonl", [{"id": f"CASE_{i:03d}", "score": (i + 1) % 2} for i in range(20)])


def main() -> None:
    make_reading(EVALS / "task-reading-improved")
    make_reading(TESTS / "reading")
    make_verdict_fixtures()
    make_holm_fixtures()
    make_lm_eval_single_task(EVALS / "task-lm-eval-folders")
    make_lm_eval_fixtures(TESTS / "lm-eval-two-tasks")
    make_inspect_epochs(EVALS / "task-inspect-epochs")
    make_rubric(TESTS / "rubric")
    make_no_overlap(EVALS / "task-error-no-overlap")


if __name__ == "__main__":
    main()
