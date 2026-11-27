"""AC-3, AC-4, AC-5: end-to-end behaviour of compare.py and plan_n.py."""
import json
import subprocess
import sys
import time
import zipfile

import pytest

import compare
import plan_n
from helpers import EVALS_FX, EXPECTED, FX, READING, ROOT, SCRIPTS, compare_json, run_cli

HOLM = EVALS_FX / "task-holm-variants"
EN = {"EVAL_LIFT_CHECK_LANG": "en"}


def verdict_of(folder):
    report = compare_json([folder / "run_a.jsonl", folder / "run_b.jsonl"])
    return report["comparisons"][0]["verdict"]


def test_four_verdicts_on_four_fixtures():
    assert verdict_of(FX / "improved") == "improved"
    assert verdict_of(FX / "regressed") == "regressed"
    assert verdict_of(FX / "bounded_null") == "bounded-null"
    assert verdict_of(EVALS_FX / "task-small-sample") == "underpowered"


def test_reading_fixture_report_fields():
    report = compare_json([READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first"])
    comp = report["comparisons"][0]
    assert report["join"]["n_paired"] == 299
    assert comp["p"] == pytest.approx(0.007942726509483574, abs=1e-12)
    assert comp["p_method"].startswith("exact McNemar")
    assert comp["ci_method"].startswith("item bootstrap")
    assert comp["required_n"]["method"].startswith("Connor 1987")
    assert comp["required_n"]["assumptions"] and comp["required_n"]["n_observed_effect"] == 304
    assert comp["discordant"] == {"baseline_only": 14, "candidate_only": 33}
    assert report["score_type"] == "binary" and report["settings"]["margin"] == 0.02
    assert comp["p_unpaired_z_reference"] == pytest.approx(0.0822, abs=1e-3)   # the number a hand calculation gives
    assert report["tool_version"] == "0.1.0"


def test_cluster_key_switches_to_cluster_robust_inference():
    report = compare_json([READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first",
                           "--cluster-key", "passage"])
    comp = report["comparisons"][0]
    assert comp["se"]["cluster"] == pytest.approx(0.02362679536910196, abs=1e-9)
    assert comp["se"]["clusters"] == 60
    assert comp["p_method"].startswith("cluster-robust t")
    assert comp["ci_method"].startswith("cluster bootstrap")
    assert comp["p"] == pytest.approx(0.009289182826065742, abs=1e-9)
    assert comp["p_mcnemar_unclustered"] == pytest.approx(0.007942726509483574, abs=1e-12)
    assert comp["required_n"]["design_effect"] > 1.0


def test_holm_decides_the_verdict_with_several_candidates():
    files = [HOLM / "baseline.json", HOLM / "variant_a.json", HOLM / "variant_b.json", HOLM / "variant_c.json"]
    report = compare_json(files)
    a, b, c = report["comparisons"]
    assert b["p"] < 0.05 < b["p_holm"]                 # raw p would call it significant
    assert (a["verdict"], b["verdict"], c["verdict"]) == ("improved", "underpowered", "underpowered")
    assert a["p_holm"] == pytest.approx(min(1.0, 3 * a["p"]))
    ordered = sorted([a["p"], b["p"], c["p"]])
    assert max(x["p_holm"] for x in (a, b, c)) >= ordered[-1]
    assert any(w["code"] == "holm-ci" for w in a["warnings"])
    code, out, _ = run_cli(compare, [*map(str, files), "--lang", "en"])
    assert code == 0 and "Holm-adjusted p" in out


def test_single_candidate_has_no_holm_adjustment():
    comp = compare_json([FX / "improved" / "run_a.jsonl", FX / "improved" / "run_b.jsonl"])["comparisons"][0]
    assert comp["p_holm"] == comp["p"]


def test_continuous_scores_use_paired_t_and_need_margin_for_bounded_null():
    comp = compare_json([FX / "rubric" / "run_a.jsonl", FX / "rubric" / "run_b.jsonl"])["comparisons"][0]
    assert comp["p_method"].startswith("paired t")
    assert comp["discordant"] is None
    assert comp["required_n"]["method"].startswith("paired normal")
    with_margin = compare_json([FX / "rubric" / "run_a.jsonl", FX / "rubric" / "run_b.jsonl",
                                "--margin", "0.5"])["comparisons"][0]
    assert with_margin["verdict"] in ("improved", "bounded-null")
    flat = compare_json([FX / "rubric" / "run_a.jsonl", FX / "rubric" / "run_a.jsonl"])
    assert flat["comparisons"][0]["verdict"] == "underpowered"
    assert {"code": "zero-variance"} in flat["comparisons"][0]["warnings"]
    code, out, _ = run_cli(compare, [FX / "rubric" / "run_a.jsonl", FX / "rubric" / "run_a.jsonl", "--lang", "en"])
    assert code == 0 and "no --margin was given" in out


def _write_runs(tmp_path, base_scores, cand_scores):
    a, b = tmp_path / "run_a.jsonl", tmp_path / "run_b.jsonl"
    a.write_text("".join(json.dumps({"id": f"q{i}", "score": s}) + "\n" for i, s in enumerate(base_scores)))
    b.write_text("".join(json.dumps({"id": f"q{i}", "score": s}) + "\n" for i, s in enumerate(cand_scores)))
    return a, b


def test_identical_small_binary_runs_are_underpowered_not_bounded_null(tmp_path):
    # QA F-1 회귀: 10문항이 모두 같으면 부트스트랩 CI 는 [0, 0] 이지만 bounded-null 이 아니다
    scores = [1, 0, 1, 1, 0, 1, 1, 1, 0, 1]
    a, b = _write_runs(tmp_path, scores, scores)
    comp = compare_json([a, b])["comparisons"][0]
    assert comp["ci95"] == [0.0, 0.0]
    assert comp["verdict"] == "underpowered" and comp["verdict_reason"] == "underpowered-check"
    assert comp["ci_check_method_code"] == {"code": "m.ci_tango"}
    assert comp["ci95_check"] == pytest.approx([-0.2775, 0.2775], abs=1e-4)
    code, out, _ = run_cli(compare, [a, b, "--lang", "en"])
    assert code == 0 and "verdict: underpowered" in out
    assert "Tango score interval for paired proportions [-0.2775, +0.2775]" in out
    assert "smaller than the margin" not in out
    code, out_ko, _ = run_cli(compare, [a, b, "--lang", "ko"])
    assert code == 0 and "쌍대 비율 Tango 점수 구간 [-0.2775, +0.2775]" in out_ko


def test_real_promptfoo_three_items_against_itself_is_underpowered():
    path = FX / "real" / "promptfoo_results.json"
    comp = compare_json([path, path])["comparisons"][0]
    assert comp["verdict"] == "underpowered" and comp["verdict_reason"] == "underpowered-check"


def test_identical_binary_runs_become_bounded_null_only_with_enough_items(tmp_path):
    # 불일치 0개라도 문항이 충분하면(189개 이상) 2점 차이를 배제할 수 있다
    small = [i % 3 == 0 for i in range(150)]
    a, b = _write_runs(tmp_path, [int(x) for x in small], [int(x) for x in small])
    assert compare_json([a, b])["comparisons"][0]["verdict"] == "underpowered"
    large = [int(i % 3 == 0) for i in range(300)]
    a, b = _write_runs(tmp_path, large, large)
    comp = compare_json([a, b])["comparisons"][0]
    assert comp["verdict"] == "bounded-null"
    assert -0.02 < comp["ci95_check"][0] and comp["ci95_check"][1] < 0.02


def test_bounded_null_fixture_passes_both_intervals():
    comp = compare_json([FX / "bounded_null" / "run_a.jsonl", FX / "bounded_null" / "run_b.jsonl"])["comparisons"][0]
    assert comp["verdict"] == "bounded-null"
    assert -0.02 < comp["ci95"][0] and comp["ci95"][1] < 0.02
    assert -0.02 < comp["ci95_check"][0] and comp["ci95_check"][1] < 0.02


def test_continuous_identical_runs_with_margin_are_underpowered(tmp_path):
    # 연속 점수에서 모든 차이가 같으면 표준오차가 0 이라 구간 폭을 알 수 없다
    scores = [0.5, 0.7, 0.2, 0.9, 0.4, 0.6, 0.3, 0.8, 0.1, 0.55]
    a, b = _write_runs(tmp_path, scores, scores)
    comp = compare_json([a, b, "--margin", "0.05"])["comparisons"][0]
    assert comp["verdict"] == "underpowered" and comp["verdict_reason"] == "underpowered-zero-variance"
    assert comp["ci95_check"] is None
    code, out, _ = run_cli(compare, [a, b, "--margin", "0.05", "--lang", "en"])
    assert code == 0 and "every item has the same difference" in out


def test_continuous_small_sample_needs_the_t_interval_inside_the_margin(tmp_path):
    # 5문항: 백분위 부트스트랩은 t 구간보다 좁다 → t 구간이 margin 밖이면 bounded-null 이 아니다
    base = [0.5, 0.5, 0.5, 0.5, 0.5]
    cand = [0.6, 0.4, 0.6, 0.4, 0.5]
    a, b = _write_runs(tmp_path, base, cand)
    comp = compare_json([a, b, "--margin", "0.1"])["comparisons"][0]
    assert -0.1 < comp["ci95"][0] and comp["ci95"][1] < 0.1
    assert comp["ci95_check"][1] > 0.1 and comp["ci_check_method_code"] == {"code": "m.ci_t"}
    assert comp["verdict"] == "underpowered" and comp["verdict_reason"] == "underpowered-check"
    assert compare_json([a, b, "--margin", "0.2"])["comparisons"][0]["verdict"] == "bounded-null"


def test_clustered_binary_check_interval_is_widened_by_the_design_effect():
    comp = compare_json([READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first",
                         "--cluster-key", "passage"])["comparisons"][0]
    assert comp["ci_check_method_code"]["code"] == "m.ci_tango_deff"
    plain = compare_json([READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first"])["comparisons"][0]
    width = comp["ci95_check"][1] - comp["ci95_check"][0]
    assert width > plain["ci95_check"][1] - plain["ci95_check"][0]


def test_epochs_cluster_summary_separates_items_from_rows():
    # QA F-4: 30문항 x 3에포크 → 문항 30개, 행 90개
    base, cand = EVALS_FX / "task-inspect-epochs" / "base.json", EVALS_FX / "task-inspect-epochs" / "cand.json"
    report = compare_json([base, cand, "--epochs", "cluster"])
    assert report["join"]["n_paired"] == 90 and report["join"]["n_items"] == 30
    code, out, _ = run_cli(compare, [base, cand, "--epochs", "cluster", "--lang", "en"])
    assert code == 0 and "paired items: 30 (90 item-epoch rows, one row per epoch)" in out
    code, out_ko, _ = run_cli(compare, [base, cand, "--epochs", "cluster", "--lang", "ko"])
    assert "짝지은 문항: 30개 (문항×에포크 90행" in out_ko
    mean = compare_json([base, cand])
    assert mean["join"]["n_paired"] == mean["join"]["n_items"] == 30
    code, out, _ = run_cli(compare, [base, cand, "--lang", "en"])
    assert "  paired items: 30\n" in out


def test_continuous_with_clusters_and_epochs():
    base, cand = EVALS_FX / "task-inspect-epochs" / "base.json", EVALS_FX / "task-inspect-epochs" / "cand.json"
    report = compare_json([base, cand, "--epochs", "cluster"])
    comp = report["comparisons"][0]
    assert report["join"]["n_paired"] == 90 and comp["se"]["clusters"] == 30
    assert comp["p_method"].startswith("cluster-robust t")
    assert report["join"]["epochs"]["policy"] == "cluster"
    mean = compare_json([base, cand])
    assert mean["join"]["n_paired"] == 30 and mean["comparisons"][0]["p_method"].startswith("paired t")


def test_same_input_and_seed_give_byte_identical_output(tmp_path):
    outputs = []
    for name in ("one.json", "two.json"):
        target = tmp_path / name
        code, out, _ = run_cli(compare, [READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first",
                                         "--lang", "en", "--json", target, "--seed", "5", "--reps", "2000"])
        assert code == 0
        # 마지막 줄은 저장 위치(절대 경로)를 알려 준다: 파일 이름만 다르므로 그 줄을 맞춰 비교한다
        assert out.endswith(f"Full report written to {target}\n")
        outputs.append((target.read_bytes(), out.replace(str(target), "REPORT")))
    assert outputs[0] == outputs[1]
    # a continuous score gives a fine-grained interval, so the seed visibly matters
    cis = []
    for seed in ("1", "2"):
        code, out, _ = run_cli(compare, [FX / "rubric" / "run_a.jsonl", FX / "rubric" / "run_b.jsonl",
                                         "--seed", seed, "--reps", "2000", "--json", "-"])
        cis.append(json.loads(out)["comparisons"][0]["ci95"])
    assert cis[0] != cis[1]


def test_json_dash_suppresses_the_summary():
    code, out, _ = run_cli(compare, [READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first", "--json", "-"])
    assert code == 0 and out.lstrip().startswith("{")


def test_error_paths(tmp_path):
    good = str(READING / "run_a.jsonl")

    def fail(args, code, name):
        status, out, err = run_cli(compare, [*map(str, args), "--lang", "en"])
        assert status == code, (args, out, err)
        first = err.splitlines()[0]
        assert first.startswith(f"error: {name}: "), first
        assert out == ""
        return err

    fail([tmp_path / "nope.jsonl", good], 2, "file-not-found")
    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    fail([junk, good], 2, "unknown-format")
    fail([good, good, "--format", "excel"], 2, "unknown-format")
    nokey = tmp_path / "nokey.jsonl"
    nokey.write_text('{"id": "a", "grade": 1}\n{"id": "b", "grade": 0}\n')
    err = fail([nokey, nokey], 2, "score-missing")
    assert "grade" in err
    text = tmp_path / "text.jsonl"
    text.write_text('{"id": "a", "score": "high"}\n')
    fail([text, text], 2, "score-not-numeric")
    # zstd-marked .eval archive
    archive = tmp_path / "z.eval"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("samples/q_epoch_1.json", json.dumps({"id": "q", "epoch": 1, "scores": {"s": {"value": "C"}}}))
    raw = bytearray(archive.read_bytes())
    for sig, offset in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
        raw[raw.find(sig) + offset:raw.find(sig) + offset + 2] = (93).to_bytes(2, "little")
    archive.write_bytes(bytes(raw))
    err = fail([archive, archive], 2, "inspect-zstd")
    assert "inspect log dump" in err
    # exit 3: duplicates under the default policy, and nothing in common
    err = fail([READING / "run_a.jsonl", READING / "run_b.jsonl"], 3, "duplicate-id")
    assert "p00-q3" in err and "--dup first" in err and "--dup mean" in err
    one = tmp_path / "one.jsonl"
    one.write_text('{"id": "a", "score": 1}\n{"id": "b", "score": 0}\n')
    other = tmp_path / "other.jsonl"
    other.write_text('{"id": "A", "score": 1}\n{"id": "B", "score": 0}\n')
    fail([one, other], 3, "too-few-pairs")


def test_usage_errors():
    for args in (["only-one.jsonl"], [str(READING / "run_a.jsonl"), str(READING / "run_b.jsonl"), "--alpha", "2"],
                 [str(READING / "run_a.jsonl"), str(READING / "run_b.jsonl"), "--reps", "5"],
                 [str(READING / "run_a.jsonl"), str(READING / "run_b.jsonl"), "--margin", "0"]):
        code, _, err = run_cli(compare, [*args, "--lang", "en"])
        assert code == 2 and err.startswith("error: bad-argument: ")


def test_unwritable_json_path_is_a_clean_error(tmp_path):
    code, _, err = run_cli(compare, [READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first",
                                     "--json", tmp_path / "missing-dir" / "out.json"])
    assert code == 2 and err.startswith("error: bad-argument: ")
    code, _, err = run_cli(plan_n, ["--discordant-rate", "0.16", "--delta", "0.02",
                                    "--json", tmp_path / "missing-dir" / "plan.json"])
    assert code == 2 and err.startswith("error: bad-argument: ")


def test_saved_report_path_is_printed_in_both_languages(tmp_path):
    # 에이전트가 다른 폴더에서 실행해도 보고서가 어디 저장됐는지 보이게 절대 경로를 찍는다
    target = tmp_path / "report.json"
    code, out, _ = run_cli(compare, [READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first",
                                     "--json", target, "--lang", "en"])
    assert code == 0 and target.exists() and out.endswith(f"Full report written to {target}\n")
    code, out, _ = run_cli(plan_n, ["--discordant-rate", "0.16", "--delta", "0.02", "--json", target,
                                    "--lang", "ko"])
    assert code == 0 and out.endswith(f"전체 보고서 저장 위치: {target}\n")
    assert json.loads(target.read_text())["n"] == 3138


LM_EVAL = FX / "lm-eval-two-tasks"  # two tasks: unit tests only (moved out of evals/ in v2)


def test_lm_eval_tasks_get_a_secondary_holm_adjusted_breakdown():
    report = compare_json([LM_EVAL / "base", LM_EVAL / "ft"])
    comp = report["comparisons"][0]
    # 주 판정은 합동(98문항) 결과 그대로
    assert comp["p"] == 0.11846923828125 and comp["verdict"] == "underpowered"
    rows = {r["task"]: r for r in comp["per_task"]}
    assert set(rows) == {"taskA", "taskB"}
    assert rows["taskA"]["n_paired"] + rows["taskB"]["n_paired"] == report["join"]["n_paired"] == 98
    # taskA: 1 대 8 불일치 → 정확 McNemar p = 2 * (1 + 9) / 2^9, Holm(태스크 2개)로 두 배
    assert rows["taskA"]["discordant"] == {"baseline_only": 1, "candidate_only": 8}
    assert rows["taskA"]["p"] == pytest.approx(20 / 512, abs=1e-15)
    assert rows["taskA"]["p_holm_tasks"] == pytest.approx(40 / 512, abs=1e-15)
    assert rows["taskB"]["p"] == 1.0 and rows["taskB"]["p_holm_tasks"] == 1.0
    # 일반 입력에는 태스크가 없으므로 per_task 도 없다
    assert "per_task" not in compare_json([READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first"])[
        "comparisons"][0]


def test_lm_eval_per_task_lines_in_both_languages_and_cluster_by_task_hint():
    code, out, _ = run_cli(compare, [LM_EVAL / "base", LM_EVAL / "ft", "--lang", "en"])
    assert code == 0 and "per task (secondary, Holm-adjusted over 2 tasks" in out
    assert "taskA: 59 items, difference +0.1186, p = 0.0391, Holm p = 0.0781" in out
    assert out.index("verdict: underpowered") < out.index("per task")
    code, out, _ = run_cli(compare, [LM_EVAL / "base", LM_EVAL / "ft", "--lang", "ko"])
    assert code == 0 and "태스크별(보조, 태스크 2개에 대해 Holm 보정" in out
    assert "taskB: 39개 문항, 차이 +0.0000, p = 1.0000, Holm p = 1.0000" in out
    for lang, words in (("en", "not clusters"), ("ko", "군집이 아니라")):
        code, _, err = run_cli(compare, [LM_EVAL / "base", LM_EVAL / "ft", "--cluster-key", "task", "--lang", lang])
        assert code == 2 and err.startswith("error: cluster-missing: ") and words in err


def test_plan_n_required_n_mde_and_errors(tmp_path):
    code, out, _ = run_cli(plan_n, ["--discordant-rate", "0.16", "--delta", "0.02", "--lang", "en"])
    assert code == 0 and "N* = 3138" in out and "Connor 1987" in out and "assumption" in out
    code, out, _ = run_cli(plan_n, ["--discordant-rate", "0.16", "--n", "3138", "--json", "-"])
    assert code == 0 and json.loads(out)["mde"] == pytest.approx(0.02, abs=2e-4)
    code, out, _ = run_cli(plan_n, ["--sd-diff", "0.2", "--delta", "0.03", "--json", "-"])
    assert json.loads(out)["n"] == EXPECTED["continuous_required_n"]["n"] and json.loads(out)["score_type"] == "continuous"
    code, out, _ = run_cli(plan_n, ["--sd-diff", "0.2", "--n", "100", "--design-effect", "2", "--json", "-"])
    assert code == 0 and json.loads(out)["mde"] > 0
    code, out, _ = run_cli(plan_n, ["--from-runs", EVALS_FX / "task-plan-n" / "pilot_a.jsonl",
                                    EVALS_FX / "task-plan-n" / "pilot_b.jsonl", "--delta", "0.02", "--lang", "en"])
    assert code == 0 and "0.2000" in out and "N* = 3923" in out
    for args in (["--discordant-rate", "1.5", "--delta", "0.02"], ["--discordant-rate", "0", "--n", "100"],
                 ["--discordant-rate", "0.16", "--delta", "0.2"], ["--discordant-rate", "0.16", "--delta", "0"],
                 ["--discordant-rate", "0.16"], ["--discordant-rate", "0.16", "--delta", "0.02", "--n", "50"],
                 ["--delta", "0.02"], ["--discordant-rate", "0.16", "--n", "1"], ["--sd-diff", "0", "--delta", "0.1"],
                 ["--discordant-rate", "0.16", "--delta", "0.02", "--alpha", "1"],
                 ["--from-runs", str(FX / "rubric" / "run_a.jsonl"), str(FX / "rubric" / "run_b.jsonl"),
                  "--delta", "0.02"]):
        code, _, err = run_cli(plan_n, [*args, "--lang", "en"])
        assert code == 2 and err.startswith("error: bad-argument: "), (args, err)
    code, _, err = run_cli(plan_n, ["--from-runs", "nope.jsonl", "nope2.jsonl", "--delta", "0.02"])
    assert code == 2 and err.startswith("error: file-not-found: ")


def test_first_run_needs_no_install_and_is_fast():
    """AC-5: plain python3, standard library only, quickstart command."""
    start = time.time()
    done = subprocess.run(
        [sys.executable, str(SCRIPTS / "compare.py"),
         str(READING / "run_a.jsonl"), str(READING / "run_b.jsonl"), "--dup", "first", "--lang", "en"],
        capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert time.time() - start < 5
    assert done.returncode == 0, done.stderr
    assert "improved" in done.stdout and "p = 0.0079" in done.stdout and "299" in done.stdout


def test_every_script_answers_help():
    for script in ("compare.py", "plan_n.py"):
        done = subprocess.run([sys.executable, str(SCRIPTS / script), "--help", "--lang", "en"], capture_output=True, text=True,
                              timeout=60)
        assert done.returncode == 0 and "usage:" in done.stdout


def test_bad_encoding_message_names_the_fix_in_both_languages(tmp_path):
    latin = tmp_path / "lat.jsonl"
    latin.write_bytes(b'{"id":"caf\xe9","score":1}\n')
    for lang, hint in (("en", "UTF-8"), ("ko", "UTF-8")):
        status, out, err = run_cli(compare, [latin, latin, "--format", "jsonl", "--lang", lang])
        assert status == 2 and out == ""
        assert err.startswith("error: bad-encoding: ")
        assert hint in err
        assert "--format" not in err
