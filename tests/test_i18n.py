"""AC-6: English and Korean output, language precedence, message tables."""
import json
import re
import string

import pytest

import _i18n
import compare
import plan_n
from helpers import READING, SCRIPTS, run_cli

HANGUL = re.compile(r"[가-힣]")
ARGS = [READING / "run_a.jsonl", READING / "run_b.jsonl", "--dup", "first"]


def fields(template):
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_message_tables_have_identical_keys_and_placeholders():
    en, ko = _i18n.MESSAGES["en"], _i18n.MESSAGES["ko"]
    assert set(en) == set(ko)
    for key in en:
        assert fields(en[key]) == fields(ko[key]), key


def test_every_literal_message_key_used_in_code_exists():
    table = set(_i18n.MESSAGES["en"])
    used = set()
    for path in SCRIPTS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'tr\(lang, "([a-z_.\-]+)"', text))
        used |= set(re.findall(r'_bad\("([a-z_.\-]+)"', text))
    assert used and used <= table, used - table
    # keys built from a variable part
    for code in ("file-not-found", "unknown-format", "id-missing", "score-missing", "score-not-numeric",
                 "cluster-missing", "inspect-zstd", "duplicate-id", "too-few-pairs", "bad-json", "no-rows"):
        assert f"err.{code}" in table, code
    for code in ("few-clusters", "one-cluster", "zero-variance", "no-discordant", "no-reqn", "holm-ci",
                 "lm-eval-latest", "prompt-idx", "promptfoo-field"):
        assert f"warn.{code}" in table, code
    for verdict in ("improved", "regressed", "bounded-null", "underpowered"):
        assert f"verdict.{verdict}" in table
    for reason in ("improved", "regressed", "bounded-null", "underpowered", "underpowered-nomargin",
                   "underpowered-check", "underpowered-zero-variance"):
        assert f"why.{reason}" in table


@pytest.mark.parametrize("cli,env,expected", [
    ("ko", {"EVAL_LIFT_CHECK_LANG": "en", "LANG": "en_US.UTF-8"}, "ko"),       # --lang wins
    ("en", {"EVAL_LIFT_CHECK_LANG": "ko", "LANG": "ko_KR.UTF-8"}, "en"),
    (None, {"EVAL_LIFT_CHECK_LANG": "ko", "LC_ALL": "en_US.UTF-8"}, "ko"),     # tool variable beats locale
    (None, {"EVAL_LIFT_CHECK_LANG": "en", "LC_ALL": "ko_KR.UTF-8"}, "en"),
    (None, {"LC_ALL": "ko_KR.UTF-8", "LC_MESSAGES": "en_US", "LANG": "en_US"}, "ko"),
    (None, {"LC_ALL": "en_US.UTF-8", "LANG": "ko_KR.UTF-8"}, "en"),            # LC_ALL beats LANG
    (None, {"LC_MESSAGES": "ko_KR.UTF-8", "LANG": "en_US"}, "ko"),
    (None, {"LANG": "ko_KR.UTF-8"}, "ko"),
    (None, {"LANG": "fr_FR.UTF-8"}, "en"),                                      # not Korean -> English
    (None, {"LANG": "C"}, "en"),
    (None, {}, "en"),
    ("xx", {"LANG": "ko_KR"}, "ko"),                                            # unknown --lang value is ignored
])
def test_language_precedence(cli, env, expected):
    assert _i18n.detect_lang(cli, env) == expected


def test_peek_lang_reads_both_spellings():
    assert _i18n.peek_lang(["--lang", "ko"], {}) == "ko"
    assert _i18n.peek_lang(["--lang=ko"], {"LANG": "en"}) == "ko"
    assert _i18n.peek_lang(["a", "b"], {"LANG": "ko_KR"}) == "ko"


@pytest.mark.parametrize("module", [compare, plan_n])
def test_help_follows_the_selected_language(module):
    code, out_en, _ = run_cli(module, ["--help", "--lang", "en"], env={"LANG": "ko_KR.UTF-8"})
    code_ko, out_ko, _ = run_cli(module, ["--help", "--lang", "ko"], env={"LANG": "en_US.UTF-8"})
    assert code == code_ko == 0
    assert not HANGUL.search(out_en) and HANGUL.search(out_ko)
    code, from_env, _ = run_cli(module, ["--help"], env={"EVAL_LIFT_CHECK_LANG": "ko"})
    assert HANGUL.search(from_env)


def test_summary_follows_the_selected_language():
    _, en, _ = run_cli(compare, [*ARGS, "--lang", "en"], env={"LANG": "ko_KR.UTF-8"})
    _, ko, _ = run_cli(compare, [*ARGS, "--lang", "ko"], env={"LANG": "en_US.UTF-8"})
    assert "Join diagnostics" in en and not HANGUL.search(en.replace("p03-q2", ""))
    assert "조인 진단" in ko and "판정: improved" in ko
    _, from_env, _ = run_cli(compare, ARGS, env={"EVAL_LIFT_CHECK_LANG": "ko"})
    assert "조인 진단" in from_env
    _, default, _ = run_cli(compare, ARGS, env={})
    assert "Join diagnostics" in default


def test_errors_are_localized_but_keep_the_code():
    for lang, probe in (("en", "not found"), ("ko", "찾을 수 없습니다")):
        code, _, err = run_cli(compare, ["missing-a.jsonl", "missing-b.jsonl", "--lang", lang])
        assert code == 2
        first = err.splitlines()[0]
        assert first.startswith("error: file-not-found: ") and probe in first


def test_json_report_is_language_independent():
    _, en, _ = run_cli(compare, [*ARGS, "--lang", "en", "--json", "-"])
    _, ko, _ = run_cli(compare, [*ARGS, "--lang", "ko", "--json", "-"])
    assert en == ko
    report = json.loads(en)
    assert report["comparisons"][0]["verdict"] == "improved"
    assert not HANGUL.search(en)


def test_plan_output_is_localized():
    _, en, _ = run_cli(plan_n, ["--discordant-rate", "0.16", "--delta", "0.02", "--lang", "en"])
    _, ko, _ = run_cli(plan_n, ["--discordant-rate", "0.16", "--delta", "0.02", "--lang", "ko"])
    assert "Evaluation planning" in en and "평가 계획" in ko and "N* = 3138" in ko


ENGLISH_RUN = re.compile(r"(?:\b[A-Za-z]{3,}\b[ ,;:()]+){3,}")
ALLOWED = ("McNemar", "Connor", "CRV1", "Holm", "bootstrap", "alpha", "N*", "doc_hash", "improved",
           "regressed", "bounded-null", "underpowered", "baseline", "candidate", "Inputs", "stderr")


def english_fragments(text):
    """Lines with a run of 3+ English words once allowed tokens and paths are removed."""
    bad = []
    for line in text.splitlines():
        cleaned = re.sub(r"\S*[/\\.]\S*", " ", line)  # paths and file names
        for token in ALLOWED:
            cleaned = cleaned.replace(token, " ")
        cleaned = re.sub(r"--[a-z-]+", " ", cleaned)
        if ENGLISH_RUN.search(cleaned):
            bad.append(line)
    return bad


@pytest.mark.parametrize("extra", [[], ["--cluster-key", "passage"]])
def test_ko_summary_has_no_english_sentences(extra):
    code, out, err = run_cli(compare, [*ARGS, *extra, "--lang", "ko"])
    assert code == 0, err
    assert english_fragments(out) == []


@pytest.mark.parametrize("argv", [
    ["--discordant-rate", "0.16", "--delta", "0.02"],
    ["--discordant-rate", "0.16", "--n", "300"],
    ["--sd-diff", "0.2", "--delta", "0.03", "--design-effect", "1.5"],
    ["--sd-diff", "0.2", "--n", "300"],
])
def test_ko_plan_output_has_no_english_sentences(argv):
    code, out, err = run_cli(plan_n, [*argv, "--lang", "ko"])
    assert code == 0, err
    assert HANGUL.search(out)
    assert english_fragments(out) == []


def test_json_report_keeps_english_text_and_adds_codes():
    code, out, _err = run_cli(compare, [*ARGS, "--json", "-"])
    comp = json.loads(out)["comparisons"][0]
    assert comp["p_method"].startswith("exact McNemar test")
    assert comp["p_method_code"]["code"] == "m.p_mcnemar"
    assert comp["required_n"]["assumption_codes"][0]["code"] == "a.rate_observed"


@pytest.mark.parametrize("module", [compare, plan_n])
def test_ko_help_has_no_argparse_english(module):
    code, out, _err = run_cli(module, ["--help", "--lang", "ko"])
    assert code == 0
    for word in ("usage:", "positional arguments:", "options:", "show this help message and exit"):
        assert word not in out
    assert "사용법:" in out
    assert "옵션:" in out
