"""AC-2 (part 2): the join reports what does not pair and applies the policies."""
import pytest

from _join import join_runs
from _loaders import Row, RunData, ToolError, load_run
from helpers import EVALS_FX, FX, READING

LM_EVAL = FX / "lm-eval-two-tasks"           # two tasks: unit tests only (moved out of evals/ in v2)
LM_ONE = EVALS_FX / "task-lm-eval-folders"     # one task: the evaluation-set case


def run(path, rows):
    return RunData(path, "jsonl", [Row(*r) if isinstance(r, tuple) else r for r in rows])


def test_reading_fixture_diagnostics():
    runs = [load_run(str(READING / "run_a.jsonl")), load_run(str(READING / "run_b.jsonl"))]
    joined = join_runs(runs, "first", "mean")
    diag = joined.diagnostics
    assert diag["n_paired"] == 299
    assert diag["only_in_baseline"] == ["p03-q2"]
    assert diag["only_in_candidate"] == []
    assert diag["duplicates"] == {"p00-q3": 2}
    assert diag["dup_policy"] == "first"
    assert joined.binary is True and joined.clusters is None


def test_duplicate_error_lists_every_duplicate_and_the_options():
    runs = [load_run(str(READING / "run_a.jsonl")), load_run(str(READING / "run_b.jsonl"))]
    with pytest.raises(ToolError) as err:
        join_runs(runs, "error", "mean")
    assert err.value.code == "duplicate-id" and err.value.exit_code == 3
    assert "p00-q3 (x2)" in err.value.fields["ids"]


def test_duplicate_policies_first_versus_mean():
    base = run("a", [("x", 1.0), ("x", 0.0), ("y", 1.0), ("z", 0.0)])
    cand = run("b", [("x", 1.0), ("y", 1.0), ("z", 1.0)])
    first = join_runs([base, cand], "first")
    assert first.scores[0] == [1.0, 1.0, 0.0]
    mean = join_runs([base, cand], "mean")
    assert mean.scores[0] == [0.5, 1.0, 0.0] and mean.binary is False
    assert mean.diagnostics["duplicates"] == {"x": 2}


def test_all_duplicates_across_runs_are_reported_together():
    base = run("a", [("x", 1.0), ("x", 1.0), ("y", 0.0), ("y", 0.0), ("z", 1.0)])
    cand = run("b", [("z", 1.0), ("z", 1.0), ("x", 0.0), ("y", 0.0)])
    with pytest.raises(ToolError) as err:
        join_runs([base, cand], "error")
    assert err.value.fields["count"] == 3
    for ident in ("x (x2)", "y (x2)", "z (x2)"):
        assert ident in err.value.fields["ids"]


def test_lm_eval_folders_pair_on_task_and_doc_id_and_drop_hash_mismatch():
    runs = [load_run(str(LM_EVAL / "base"), metric="acc"), load_run(str(LM_EVAL / "ft"), metric="acc")]
    diag = join_runs(runs, "error", "mean").diagnostics
    assert diag["n_paired"] == 98
    assert diag["only_in_baseline"] == ["taskA/59"]
    assert diag["hash_mismatch"] == ["taskB/7"]


def test_lm_eval_single_task_drops_the_hash_mismatch_and_the_missing_doc():
    runs = [load_run(str(LM_ONE / "base"), metric="acc"), load_run(str(LM_ONE / "ft"), metric="acc")]
    joined = join_runs(runs, "error", "mean")
    diag = joined.diagnostics
    assert diag["n_paired"] == 78
    assert diag["only_in_baseline"] == ["quiz_mc/79"] and diag["only_in_candidate"] == []
    assert diag["hash_mismatch"] == ["quiz_mc/7"]
    # 짝지은 78개에서 불일치는 6 대 13(doc 7 을 그대로 짝지으면 6 대 14 가 된다)
    a, b = joined.scores
    assert sum(x > y for x, y in zip(a, b)) == 6 and sum(y > x for x, y in zip(a, b)) == 13


def test_inspect_epochs_mean_and_cluster():
    base = FX / "real" / "inspect_log.json"
    runs = [load_run(str(base)), load_run(str(base))]
    mean = join_runs(runs, "error", "mean")
    assert mean.diagnostics["n_paired"] == 4
    assert mean.diagnostics["epochs"]["per_input"][0] == {"path": str(base), "min": 2, "max": 2}
    assert all(v in (0.0, 0.5, 1.0) for v in mean.scores[0])
    cluster = join_runs(runs, "error", "cluster")
    assert cluster.diagnostics["n_paired"] == 8
    assert cluster.ids[0].endswith("#e1") or "#e" in cluster.ids[0]
    assert cluster.binary is True


def test_epochs_cluster_uses_item_as_cluster_by_default_path_in_cli():
    # the CLI turns '--epochs cluster' into clusters keyed by the item id
    from helpers import compare_json
    report = compare_json([FX / "real" / "inspect_log.json", FX / "real" / "inspect_log.json", "--epochs", "cluster"])
    assert report["join"]["n_paired"] == 8
    assert report["comparisons"][0]["se"]["clusters"] == 4


def test_too_few_pairs_and_message_fields():
    base = run("a", [("a1", 1.0), ("a2", 0.0)])
    cand = run("b", [("b1", 1.0), ("b2", 0.0), ("b3", 1.0)])
    with pytest.raises(ToolError) as err:
        join_runs([base, cand])
    assert err.value.code == "too-few-pairs" and err.value.exit_code == 3
    assert err.value.fields == {"n": 0, "n_base": 2, "n_cand": 3}
    one = run("c", [("a1", 1.0), ("zzz", 1.0)])
    with pytest.raises(ToolError):
        join_runs([base, one])


def test_cluster_comes_from_the_baseline_and_must_be_complete():
    base = run("a", [("x", 1.0, "g1"), ("y", 0.0, "g1"), ("z", 1.0, "g2")])
    cand = run("b", [("x", 1.0, "gX"), ("y", 1.0, "gX"), ("z", 1.0, "gX")])
    assert join_runs([base, cand]).clusters == ["g1", "g1", "g2"]
    no_cluster = run("c", [("x", 1.0), ("y", 0.0), ("z", 1.0)])
    assert join_runs([no_cluster, cand]).clusters is None


def test_several_candidates_use_the_intersection():
    base = run("a", [("x", 1.0), ("y", 0.0), ("z", 1.0), ("w", 0.0)])
    v1 = run("v1", [("x", 1.0), ("y", 1.0), ("z", 1.0), ("w", 1.0)])
    v2 = run("v2", [("x", 0.0), ("y", 1.0), ("w", 0.0), ("q", 1.0)])
    joined = join_runs([base, v1, v2])
    assert joined.ids == ["w", "x", "y"]
    assert joined.diagnostics["only_in_baseline"] == ["z"]
    assert joined.diagnostics["only_in_candidate"] == ["q", "z"]
    assert len(joined.scores) == 3
