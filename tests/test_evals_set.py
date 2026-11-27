"""AC-8: the evaluation set is complete and its regex graders match real script output."""
import json
import re
import shutil
import subprocess
import sys

import pytest

from helpers import EVALS_FX, ROOT, SCRIPTS

EVALS = ROOT / "evals"
COMPARE = str(SCRIPTS / "compare.py")
PLAN = str(SCRIPTS / "plan_n.py")


def front(path):
    """Read the frontmatter of a case file into a dict (just enough YAML for these files)."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    head, _, body = text[4:].partition("\n---\n")
    data = {}
    for line in head.splitlines():
        key, _, value = line.partition(": ")
        value = value.strip()
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        data[key.strip()] = value
    data["_body"] = body
    return data


def cases(prefix):
    return sorted(p for p in EVALS.iterdir() if p.is_dir() and p.name.startswith(prefix))


def test_composition_meets_the_minimums():
    triggers, near, far = cases("trigger-"), cases("notrigger-near-"), [
        p for p in cases("notrigger-") if not p.name.startswith("notrigger-near-")]
    tasks = cases("task-")
    assert len(triggers) >= 10 and len(near) >= 5 and len(near) + len(far) >= 10 and len(tasks) >= 5
    korean = [p for p in triggers if re.search(r"[가-힣]", front(p / "prompt.md")["_body"])]
    assert len(korean) >= 2
    assert any(p.name.startswith("task-error-") for p in tasks)
    for case in triggers:
        body = front(case / "prompt.md")["_body"]
        assert not re.search(r"eval-lift-check|\bskill\b|스킬", body, re.I), case.name
        grader = front(case / "graders" / "skill-fired.md")
        assert grader["tool"] == "Skill" and grader["arm"] == "both"
        assert re.search(grader["input_match"], json.dumps({"skill": "eval-lift-check"}))
        assert re.search(grader["input_match"], json.dumps({"skill": "eval-lift-check:eval-lift-check"}))
        assert not re.search(grader["input_match"], json.dumps({"skill": "eval-lift-check-other"}))
    for case in [*near, *far]:
        grader = front(case / "graders" / "skill-not-fired.md")
        assert grader["max"] == "0" and grader["arm"] == "both"


def test_every_task_has_fixture_script_grader_and_exact_value_regex():
    for case in cases("task-"):
        assert (EVALS_FX / case.name).is_dir(), f"no fixture folder for {case.name}"
        assert any((EVALS_FX / case.name).rglob("*.json*")), case.name
        ran = front(case / "graders" / "script-ran.md")
        assert ran["arm"] == "with-only" and ran["tool"] == "Bash"
        value_graders = [g for g in (case / "graders").glob("*.md") if front(g)["type"] == "regex"]
        assert value_graders, case.name
        for grader in value_graders:
            assert len(front(grader)["pattern"]) >= 6, (case.name, grader.name)


# the command a correct agent would run for each task (cwd = a copy of the fixture folder)
COMMANDS = {
    "task-reading-improved": [[COMPARE, "run_a.jsonl", "run_b.jsonl", "--dup", "first", "--json", "report.json"]],
    "task-lm-eval-folders": [[COMPARE, "base", "ft", "--metric", "acc", "--json", "report.json"]],
    "task-holm-variants": [[COMPARE, "baseline.json", "variant_a.json", "variant_b.json", "variant_c.json",
                            "--json", "report.json"]],
    "task-small-sample": [[COMPARE, "run_a.jsonl", "run_b.jsonl", "--json", "report.json"]],
    "task-inspect-epochs": [[COMPARE, "base.json", "cand.json", "--epochs", "cluster", "--json", "report.json"]],
    "task-plan-n": [[PLAN, "--from-runs", "pilot_a.jsonl", "pilot_b.jsonl", "--delta", "0.02", "--json", "plan.json"]],
    "task-error-no-overlap": [[COMPARE, "run_a.jsonl", "run_b.jsonl"]],
}


# tasks whose prompt asks to keep the raw stdout+stderr in a file (the agent runs `... > output.txt 2>&1`)
RAW_OUTPUT = {"task-error-no-overlap": "output.txt"}


def grade(name, work, answer_text):
    """Run every regex grader of a task case; return {grader file name: passed}."""
    results = {}
    for grader_path in sorted((EVALS / name / "graders").glob("*.md")):
        grader = front(grader_path)
        if grader["type"] != "regex":
            continue
        match = re.fullmatch(r"\{source: file, path: (.+)\}", grader.get("target", ""))
        if match:
            target = work / match[1]
            text = target.read_text(encoding="utf-8") if target.exists() else None
        else:
            text = answer_text
        if text is None:
            results[grader_path.name] = False  # 파일이 없으면 채점 실패
            continue
        hits = re.findall(grader["pattern"], text, re.M)
        results[grader_path.name] = not hits if grader.get("match") == "not_contains" else bool(hits)
    return results


@pytest.mark.parametrize("lang", ["en", "ko"])
@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_task_regexes_match_real_script_output(name, lang, tmp_path):
    # 하네스 세션은 한국어 로케일에서도 돈다: 두 언어 출력 모두에서 채점이 통과해야 한다
    work = tmp_path / name
    shutil.copytree(EVALS_FX / name, work)
    pooled = ""
    for argv in COMMANDS[name]:
        done = subprocess.run([sys.executable, *argv, "--lang", lang], cwd=work, capture_output=True, text=True,
                              timeout=60)
        pooled += done.stdout + done.stderr
        expected_exit = 3 if name == "task-error-no-overlap" else 0
        assert done.returncode == expected_exit, done.stderr
    if name in RAW_OUTPUT:
        (work / RAW_OUTPUT[name]).write_text(pooled, encoding="utf-8")
    ran = front(EVALS / name / "graders" / "script-ran.md")
    assert re.search(ran["input_match"], f"python3 /abs/skills/eval-lift-check/{argv[0].split('/skills/eval-lift-check/')[1]}")
    results = grade(name, work, pooled)
    assert results and all(results.values()), (name, lang, results)


def skill_docs_text():
    root = ROOT / "skills" / "eval-lift-check"
    return "\n".join(p.read_text(encoding="utf-8") for p in [root / "SKILL.md", *sorted((root / "references").glob("*.md"))])


def test_error_code_of_the_error_task_is_not_given_away_by_the_docs():
    # 문서에 오류 코드가 있으면 스크립트 없이도 답에 코드를 쓸 수 있다(돌연변이 생존 원인)
    assert "too-few-pairs" not in skill_docs_text()
    docs = skill_docs_text()
    for name in ("task-error-no-overlap", "task-small-sample", "task-holm-variants", "task-lm-eval-folders"):
        for grader_path in sorted((EVALS / name / "graders").glob("*.md")):
            grader = front(grader_path)
            if grader["type"] == "regex" and "target" in grader:
                assert not re.search(grader["pattern"], docs, re.M), (name, grader_path.name)


# What an agent can still write when the script is replaced by a fake: everything it can read in
# SKILL.md / references or count or compute by hand from the fixture. The graders must fail it.
HAND_MADE = {
    "task-error-no-overlap": {
        "answer": "I cannot tell. The two files share 0 ids: run_a has 20 rows with ids like case-0 and run_b has "
                  "20 rows with ids like CASE_000. error: too-few-pairs: the id schemes differ, so no pairs exist. "
                  "Map the ids to one scheme and re-run.",
        "files": {"output.txt": "error: too-few-pairs: 0 common ids (run_a 20, run_b 20); id schemes differ.\n"},
    },
    "task-small-sample": {
        "answer": "Verdict: underpowered. Paired on 40 items, disagreements 3 vs 5, exact McNemar p = 0.7265625. "
                  "Required N for a 2-point difference is 3923 (Connor 1987); you have 40.",
        "files": {"report.json": json.dumps({
            "comparisons": [{
                "mean_baseline": 0.7, "mean_candidate": 0.75, "diff": 0.05, "ci95": [-0.075, 0.175],
                "p": 0.7265625, "p_method": "exact McNemar test (two-sided binomial on the disagreements)",
                "discordant": {"baseline_only": 3, "candidate_only": 5},
                "se": {"paired": 0.0711625}, "required_n": {
                    "n": 3923, "method": "Connor 1987 (normal approximation for McNemar)",
                    "assumptions": ["disagreement rate 0.2 held fixed", "alpha 0.05, power 0.8"]},
                "mde": 0.19, "verdict": "underpowered"}]}, indent=2)},
    },
    # 최악의 경우: 정확 McNemar·Holm 은 손으로도 정확히 나온다(돌연변이 생존 원인이던 값),
    # 비쌍대 z(합동 분산)도 교과서 공식으로 정확히 재현했다고 가정한다
    "task-holm-variants": {
        "answer": "Only variant_a beats the baseline: exact McNemar p = 0.00047, Holm-adjusted p = 0.0014 "
                  "(improved). variant_b p = 0.0414, Holm 0.0828 (underpowered); variant_c p = 0.83.",
        "files": {"report.json": json.dumps({
            "comparisons": [
                {"candidate": "variant_a.json", "diff": 0.11, "ci95": [0.05, 0.17],
                 "ci_method": "percentile bootstrap, 10000 resamples", "p": 0.0004719867429230362,
                 "p_holm": 0.0014159602287691087, "discordant": {"baseline_only": 8, "candidate_only": 30},
                 "required_n": {"n": 3726, "method": "Connor 1987",
                                "assumptions": ["disagreement rate 0.19 held fixed", "alpha 0.05, power 0.8"]},
                 "mde": 0.0858, "p_unpaired_z_reference": 0.01268659625483659, "verdict": "improved"},
                {"candidate": "variant_b.json", "p": 0.04138946533203125, "p_holm": 0.0827789306640625,
                 "verdict": "underpowered"},
                {"candidate": "variant_c.json", "p": 0.8318119049072266, "p_holm": 0.8318119049072266,
                 "verdict": "underpowered"}]}, indent=2)},
    },
    # 최악의 경우: doc_hash 불일치를 알아채 제외하고, 정확 McNemar(6 대 13)를 손으로 정확히 계산했다고 가정한다
    "task-lm-eval-folders": {
        "answer": "Verdict: underpowered. 78 paired items (quiz_mc/79 missing in ft, quiz_mc/7 "
                  "excluded because its doc_hash changed). Disagreements 6 vs 13, exact McNemar p = 0.167.",
        "files": {"report.json": json.dumps({
            "join": {"n_paired": 78, "only_in_baseline": ["quiz_mc/79"], "hash_mismatch": ["quiz_mc/7"]},
            "comparisons": [{
                "candidate": "ft", "mean_baseline": 0.5256, "mean_candidate": 0.6154, "diff": 0.0897,
                "ci95": [-0.0187, 0.1981], "ci_method": "Wald normal approximation",
                "p": 0.1670684814453125, "discordant": {"baseline_only": 6, "candidate_only": 13},
                "required_n": {"n": 4778, "method": "Connor 1987",
                               "assumptions": ["disagreement rate 0.2436 held fixed", "alpha 0.05, power 0.8"]},
                "mde": 0.154, "p_unpaired_z_reference": 0.2575, "verdict": "underpowered"}]}, indent=2)},
    },
}

# 케이스 통과선(skill-eval thresholds.task_case_score_min)
CASE_PASS_LINE = 0.67


@pytest.mark.parametrize("name", sorted(HAND_MADE))
def test_hand_made_answers_without_the_script_fail_the_graders(name, tmp_path):
    # 돌연변이 검사 흉내: 스크립트 없이 손으로 만든 답은 케이스 통과선(0.67) 아래여야 한다
    work = tmp_path / name
    shutil.copytree(EVALS_FX / name, work)
    for file_name, text in HAND_MADE[name]["files"].items():
        (work / file_name).write_text(text, encoding="utf-8")
    results = grade(name, work, HAND_MADE[name]["answer"])
    # script-ran 은 가짜 스크립트도 실행되므로 통과한 것으로 센다
    score = (sum(results.values()) + 1) / (len(results) + 1)
    worst_case = ("task-holm-variants", "task-lm-eval-folders")
    assert score < 0.6 if name not in worst_case else score < CASE_PASS_LINE, (name, score, results)
    if name == "task-holm-variants":
        # 손으로 재현되는 값(Holm p 두 개, 승자 이름)은 맞았지만 스크립트 고유 값은 모두 빠져야 한다
        assert results["report-holm-a.md"] and results["report-holm-b.md"] and results["answer-winner.md"]
        for grader in ("json-assumption-a.md", "json-mde-a.md", "json-ci-method.md"):
            assert not results[grader], grader
    if name == "task-lm-eval-folders":
        # 문항 수·해시·정확 p·판정은 손으로도 맞힐 수 있다고 보고, 스크립트 고유 값 3개가 막아야 한다
        assert results["report-join.md"] and results["report-hash.md"] and results["report-p.md"]
        for grader in ("json-mde.md", "json-assumption.md", "json-ci.md"):
            assert not results[grader], grader


def test_lm_eval_case_is_one_task_with_a_hash_mismatch_and_no_per_task_grader():
    # v2: 실측 케이스는 태스크 1개. 여러 태스크(per_task)는 tests/fixtures/lm-eval-two-tasks 의 단위 테스트로만 검증
    case = EVALS / "task-lm-eval-folders"
    fixture = EVALS_FX / "task-lm-eval-folders"
    for side in ("base", "ft"):
        files = sorted((fixture / side).glob("samples_*.jsonl"))
        assert len(files) == 1 and files[0].name.startswith("samples_quiz_mc_"), files
    assert not (case / "graders" / "json-per-task.md").exists()
    assert not any("p_holm_tasks" in front(g)["pattern"] for g in (case / "graders").glob("*.md")
                   if front(g)["type"] == "regex")
    body = front(case / "prompt.md")["_body"]
    assert "one task" in body and "quiz_mc" in body and "two tasks" not in body
    # 픽스처 base/ft 사이에 doc_hash 가 다른 문항이 하나 이상 있다
    base = {json.loads(line)["doc_id"]: json.loads(line)["doc_hash"]
            for line in next((fixture / "base").glob("*.jsonl")).read_text().splitlines()}
    ft = [json.loads(line) for line in next((fixture / "ft").glob("*.jsonl")).read_text().splitlines()]
    assert sum(row["doc_hash"] != base[row["doc_id"]] for row in ft) >= 1


def test_lm_eval_case_rejects_a_report_that_pairs_the_edited_question(tmp_path):
    # doc_hash 를 무시하고 doc 7 까지 짝지은 결과(6 대 14)는 정확 p·문항 수 채점에서 빠져야 한다
    work = tmp_path / "w"
    shutil.copytree(EVALS_FX / "task-lm-eval-folders", work)
    for side in ("base", "ft"):
        path = next((work / side).glob("*.jsonl"))
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            row.pop("doc_hash")
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    done = subprocess.run([sys.executable, COMPARE, "base", "ft", "--json", "report.json", "--lang", "en"], cwd=work,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    results = grade("task-lm-eval-folders", work, done.stdout)
    assert not results["report-join.md"] and not results["report-p.md"] and not results["report-hash.md"]


def test_reading_task_fails_without_dup_policy_like_the_prompt_expects(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(EVALS_FX / "task-reading-improved", work)
    done = subprocess.run([sys.executable, COMPARE, "run_a.jsonl", "run_b.jsonl", "--lang", "en"], cwd=work,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 3 and "duplicate-id" in done.stderr
    assert not (work / "report.json").exists()
