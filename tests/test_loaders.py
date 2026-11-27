"""AC-2 (part 1): adapters read every supported format."""
import json
import zipfile

import pytest

from _loaders import ToolError, detect_format, load_run, normalize_score
from helpers import EVALS_FX, FX, READING

REAL = FX / "real"
LM_EVAL = FX / "lm-eval-two-tasks"           # two tasks: unit tests only (moved out of evals/ in v2)
LM_ONE = EVALS_FX / "task-lm-eval-folders"     # one task: the evaluation-set case


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_normalize_score_accepts_the_documented_spellings():
    assert normalize_score(True) == 1.0
    assert normalize_score("C") == 1.0 and normalize_score("I") == 0.0
    assert normalize_score("true") == 1.0 and normalize_score(" False ") == 0.0
    assert normalize_score("0.75") == 0.75
    assert normalize_score(3) == 3.0
    for bad in ("maybe", None, {"a": 1}, float("nan"), float("inf"), [1]):
        with pytest.raises(ValueError):
            normalize_score(bad)


def test_generic_jsonl_and_csv_with_custom_keys(tmp_path):
    jl = write(tmp_path / "a.jsonl", '{"qid": "x", "ok": true, "grp": "g1"}\n\n{"qid": "y", "ok": false, "grp": "g1"}\n')
    run = load_run(jl, id_key="qid", score_key="ok", cluster_key="grp")
    assert run.format_detected == "jsonl"
    assert [(r.key, r.score, r.cluster) for r in run.rows] == [("x", 1.0, "g1"), ("y", 0.0, "g1")]
    cs = write(tmp_path / "b.csv", "id,score\na,1\nb,0\n")
    run = load_run(cs)
    assert run.format_detected == "csv" and [r.score for r in run.rows] == [1.0, 0.0]


def test_generic_json_list(tmp_path):
    path = write(tmp_path / "rows.json", json.dumps([{"id": 1, "score": 1}, {"id": 2, "score": 0}]))
    assert detect_format(tmp_path / "rows.json") == "jsonl"
    assert [r.key for r in load_run(path).rows] == ["1", "2"]


def test_lm_eval_folder_keys_are_task_and_doc_id_and_hashes_kept():
    run = load_run(str(LM_EVAL / "base"))
    assert run.format_detected == "lm-eval"
    keys = {r.key for r in run.rows}
    assert "taskA/0" in keys and "taskB/0" in keys           # same doc_id, different task
    assert len(keys) == len(run.rows) == 100
    assert run.score_field == "acc"
    assert all(r.doc_hash for r in run.rows)


def test_lm_eval_single_task_folder_keys_and_hashes():
    # 평가 세트 케이스(태스크 1개): 폴더 안 samples 파일 하나, 키는 여전히 <task>/<doc_id>
    base, ft = load_run(str(LM_ONE / "base")), load_run(str(LM_ONE / "ft"))
    assert base.format_detected == ft.format_detected == "lm-eval"
    assert len(list((LM_ONE / "base").glob("samples_*.jsonl"))) == len(list((LM_ONE / "ft").glob("samples_*.jsonl"))) == 1
    assert {r.key.split("/")[0] for r in base.rows} == {"quiz_mc"}
    assert len(base.rows) == 80 and len(ft.rows) == 79
    hashes = {r.key: r.doc_hash for r in base.rows}
    assert [r.key for r in ft.rows if r.doc_hash != hashes[r.key]] == ["quiz_mc/7"]


def test_lm_eval_single_file_and_metric_selection(tmp_path):
    row = {"doc_id": 3, "acc": 1.0, "acc_norm": 0.0, "metrics": ["acc", "acc_norm"], "doc_hash": "h"}
    path = write(tmp_path / "samples_foo_2026-01-01T00-00-00.000000.jsonl", json.dumps(row) + "\n")
    assert load_run(path).rows[0].key == "foo/3"
    assert load_run(path, metric="acc_norm").rows[0].score == 0.0
    plain = write(tmp_path / "renamed.jsonl", json.dumps(row) + "\n")
    assert load_run(plain, fmt="lm-eval").rows[0].key == "3"
    with pytest.raises(ToolError) as err:
        load_run(path, metric="nope")
    assert err.value.code == "score-missing" and "acc_norm" in err.value.fields["seen"]


def test_lm_eval_latest_file_per_task_is_used_and_reported(tmp_path):
    old = {"doc_id": 0, "acc": 0.0}
    new = {"doc_id": 0, "acc": 1.0}
    write(tmp_path / "samples_t_2026-01-01T00-00-00.000000.jsonl", json.dumps(old) + "\n")
    write(tmp_path / "samples_t_2026-02-01T00-00-00.000000.jsonl", json.dumps(new) + "\n")
    run = load_run(str(tmp_path))
    assert [r.score for r in run.rows] == [1.0]
    assert run.warnings[0]["code"] == "lm-eval-latest"
    assert "2026-02-01" in run.warnings[0]["name"]


def test_inspect_json_log_real_output():
    run = load_run(str(REAL / "inspect_log.json"))
    assert run.format_detected == "inspect" and run.score_field == "parity"
    assert len(run.rows) == 8
    assert sorted({r.epoch for r in run.rows}) == [1, 2]
    assert {r.score for r in run.rows} <= {0.0, 1.0}


def test_inspect_eval_archive_real_output_or_zstd_message():
    try:
        run = load_run(str(REAL / "inspect_log.eval"))
    except ToolError as err:
        # Python before 3.14 cannot open the zstd members the real archive uses.
        assert err.code == "inspect-zstd"
        pytest.skip("this Python cannot read zstd zip members")
    json_run = load_run(str(REAL / "inspect_log.json"))
    key = lambda r: (r.key, r.epoch)  # noqa: E731
    assert sorted((key(r), r.score) for r in run.rows) == sorted((key(r), r.score) for r in json_run.rows)


def test_inspect_eval_archive_deflated_and_zstd_marker(tmp_path):
    samples = [{"id": "q0", "epoch": 1, "scores": {"s": {"value": "C"}}},
               {"id": "q0", "epoch": 2, "scores": {"s": {"value": "I"}}}]
    archive = tmp_path / "ok.eval"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for sample in samples:
            zf.writestr(f"samples/{sample['id']}_epoch_{sample['epoch']}.json", json.dumps(sample))
        zf.writestr("header.json", "{}")
    run = load_run(str(archive))
    assert run.format_detected == "inspect" and [r.score for r in run.rows] == [1.0, 0.0]
    # Flag every member as zstd without real zstd data: reading must fail with the helpful code.
    raw = bytearray(archive.read_bytes())
    for sig, offset in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
        start = 0
        while (start := raw.find(sig, start)) != -1:
            raw[start + offset:start + offset + 2] = (93).to_bytes(2, "little")
            start += 4
    fake = tmp_path / "zstd.eval"
    fake.write_bytes(bytes(raw))
    with pytest.raises(ToolError) as err:
        load_run(str(fake))
    assert err.value.code == "inspect-zstd"


def test_inspect_scorer_choice_and_value_types(tmp_path):
    log = {"samples": [{"id": 1, "epoch": 1, "scores": {"a": {"value": 1.0}, "b": {"value": "I"}}}]}
    path = write(tmp_path / "log.json", json.dumps(log))
    assert load_run(path).rows[0].score == 1.0
    assert load_run(path, metric="b").rows[0].score == 0.0
    with pytest.raises(ToolError) as err:
        load_run(path, metric="c")
    assert err.value.code == "score-missing"
    nested = write(tmp_path / "n.json", json.dumps({"samples": [{"id": 1, "scores": {"a": {"value": {"x": 1}}}}]}))
    with pytest.raises(ToolError) as err:
        load_run(nested)
    assert err.value.code == "score-not-numeric"


def test_promptfoo_json_real_output_and_jsonl_agree():
    as_json = load_run(str(REAL / "promptfoo_results.json"))
    as_jsonl = load_run(str(REAL / "promptfoo_results.jsonl"))
    assert as_json.format_detected == as_jsonl.format_detected == "promptfoo"
    assert [(r.key, r.score) for r in as_json.rows] == [("0", 1.0), ("1", 0.0), ("2", 1.0)]
    assert [(r.key, r.score) for r in as_jsonl.rows] == [(r.key, r.score) for r in as_json.rows]
    assert as_json.score_field == "success"


def test_promptfoo_id_key_from_vars_and_score_key_and_fallbacks(tmp_path):
    rows = [{"promptIdx": 0, "vars": {"q": "alpha"}, "gradingResult": {"pass": True}, "score": 0.5},
            {"promptIdx": 1, "vars": {"q": "beta"}, "pass": False, "score": 0.25}]
    path = write(tmp_path / "r.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
    run = load_run(path, fmt="promptfoo", id_key="q")
    assert [r.key for r in run.rows] == ["alpha", "beta"]
    assert [r.score for r in run.rows] == [1.0, 0.0]
    assert {w["code"] for w in run.warnings} == {"prompt-idx", "promptfoo-field"}
    only_first = load_run(path, fmt="promptfoo", id_key="q", prompt_idx=0)
    assert [r.key for r in only_first.rows] == ["alpha"]
    by_score = load_run(path, fmt="promptfoo", id_key="q", score_key="score")
    assert [r.score for r in by_score.rows] == [0.5, 0.25]
    with pytest.raises(ToolError) as err:
        load_run(path, fmt="promptfoo", id_key="nope")
    assert err.value.code == "id-missing"


def test_auto_detection_and_unknown_format(tmp_path):
    assert detect_format(REAL / "inspect_log.json") == "inspect"
    assert detect_format(REAL / "promptfoo_results.json") == "promptfoo"
    assert detect_format(REAL / "promptfoo_results.jsonl") == "promptfoo"
    assert detect_format(LM_EVAL / "base") == "lm-eval"
    assert detect_format(READING / "run_a.jsonl") == "jsonl"
    for name, text in (("x.txt", "hello"), ("y.json", '"just a string"')):
        with pytest.raises(ToolError) as err:
            detect_format(tmp_path / name) if (tmp_path / name).exists() else load_run(write(tmp_path / name, text))
        assert err.value.code == "unknown-format"
    with pytest.raises(ToolError) as err:
        load_run(str(tmp_path))  # an empty folder
    assert err.value.code == "unknown-format"
    with pytest.raises(ToolError) as err:
        load_run(str(tmp_path / "missing.jsonl"))
    assert err.value.code == "file-not-found"


def test_error_codes_carry_row_and_seen_fields(tmp_path):
    path = write(tmp_path / "a.jsonl", '{"id": "x", "grade": 1}\n')
    with pytest.raises(ToolError) as err:
        load_run(path)
    assert err.value.code == "score-missing"
    assert err.value.fields["seen"] == "grade, id" and err.value.fields["row"] == 1
    with pytest.raises(ToolError) as err:
        load_run(path, id_key="qid", score_key="grade")
    assert err.value.code == "id-missing"
    bad = write(tmp_path / "b.jsonl", '{"id": "x", "score": "high"}\n')
    with pytest.raises(ToolError) as err:
        load_run(bad)
    assert err.value.code == "score-not-numeric" and err.value.fields["value"] == "high"
    broken = write(tmp_path / "c.jsonl", '{"id": "x", "score": 1}\n{oops\n')
    with pytest.raises(ToolError) as err:
        load_run(broken)
    assert err.value.code == "bad-json" and "line 2" in err.value.fields["reason"]
    empty = write(tmp_path / "d.jsonl", "")
    with pytest.raises(ToolError) as err:
        load_run(empty, fmt="jsonl")
    assert err.value.code == "no-rows"
    with pytest.raises(ToolError) as err:
        load_run(path, id_key="id", score_key="grade", cluster_key="grp")
    assert err.value.code == "cluster-missing"


@pytest.mark.parametrize("name,fmt", [("lat.jsonl", "jsonl"), ("lat.csv", "csv"), ("lat.json", "jsonl")])
def test_non_utf8_file_reports_bad_encoding_with_offset(tmp_path, name, fmt):
    path = tmp_path / name
    path.write_bytes(b'id,score\ncaf\xe9,1\n' if fmt == "csv" else b'{"id":"caf\xe9","score":1}\n')
    with pytest.raises(ToolError) as err:
        load_run(str(path), fmt)
    assert err.value.code == "bad-encoding"
    assert err.value.fields["offset"] > 0
