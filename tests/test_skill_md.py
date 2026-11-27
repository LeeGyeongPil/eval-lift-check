"""AC-7: SKILL.md points to every bundled script and reference by its plain relative path.

A static skill checker counts a bundled file as used only when the SKILL.md body names it as a
relative path such as `scripts/compare.py`. Writing `<this skill's folder>/scripts/compare.py`
made it report both scripts as unused, so this test uses a conservative rule: the character
right before the path must be the line start, a space, a backtick, `(` or `[`.
"""
import re

from helpers import ROOT

SKILL = ROOT / "skills" / "eval-lift-check"
ALLOWED_BEFORE = " `(["


def body_of_skill_md():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, _, body = text[4:].partition("\n---\n")
    return body


def named_plainly(body, rel_path):
    """True when rel_path appears at least once with an allowed character (or line start) before it."""
    for match in re.finditer(re.escape(rel_path), body):
        start = match.start()
        if start == 0 or body[start - 1] == "\n" or body[start - 1] in ALLOWED_BEFORE:
            return True
    return False


def bundled_files():
    scripts = sorted(f"scripts/{p.name}" for p in (SKILL / "scripts").glob("*.py") if not p.name.startswith("_"))
    references = sorted(f"references/{p.name}" for p in (SKILL / "references").glob("*.md"))
    return scripts, references


def test_the_rule_itself_rejects_placeholder_prefixes():
    # 규칙이 회차 3의 실패 표기(자리표시자 접두)를 실제로 잡는지 먼저 확인한다
    assert not named_plainly("run `python3 <this skill's folder>/scripts/compare.py A B`", "scripts/compare.py")
    assert not named_plainly("run python3 /path/to/scripts/compare.py", "scripts/compare.py")
    assert not named_plainly("see myscripts/compare.py", "scripts/compare.py")
    for ok in ("run `scripts/compare.py`", "run python3 scripts/compare.py", "(scripts/compare.py)",
               "[scripts/compare.py]", "scripts/compare.py is the entry point"):
        assert named_plainly(ok, "scripts/compare.py"), ok


def test_expected_bundle_is_what_the_plan_names():
    scripts, references = bundled_files()
    assert scripts == ["scripts/compare.py", "scripts/plan_n.py"]
    assert references == ["references/formats.md", "references/statistics.md"]


def test_every_bundled_script_and_reference_is_named_by_relative_path():
    body = body_of_skill_md()
    scripts, references = bundled_files()
    missing = [path for path in [*scripts, *references] if not named_plainly(body, path)]
    assert not missing, f"SKILL.md does not name these by plain relative path: {missing}"


def test_no_placeholder_or_absolute_prefix_before_bundled_paths():
    body = body_of_skill_md()
    assert not re.search(r"[>}\w.-]/(scripts|references)/", body), "path prefix in front of scripts/ or references/"
    assert "/path/to/" not in body and "this skill's folder>" not in body


def test_how_to_run_sentence_is_there():
    body = body_of_skill_md()
    # 실행 위치 규칙은 경로 표기와 별도 문장으로: 사용자 작업 폴더에서 전체 경로로 실행, 스킬 폴더로 cd 금지
    assert re.search(r"full path from the user's working folder", body)
    assert re.search(r"do not `cd` into the skill folder", body, re.I)
    # 명령 예시는 채점 패턴(scripts/compare\.py)과 같은 모양
    assert "python3 scripts/compare.py BASELINE CANDIDATE" in body
    assert "python3 scripts/plan_n.py --discordant-rate" in body


def test_always_run_the_script_rule_is_explicit():
    # skill-eval: 답은 맞았지만 스크립트 경로가 명령에 없이(직접 계산·변수·cd·import) 실행돼 script_ran 미달.
    # 규칙이 본문 앞쪽(작업 절차보다 먼저)에 눈에 띄게 있고, 질문 → 스크립트 대응과 명령 모양 금지 사항을 담는지 확인한다.
    body = body_of_skill_md()
    rule = "**Always run the bundled script for the numbers. Do not compute them yourself**"
    assert rule in body and body.index(rule) < body.index("## Workflow")
    assert re.search(r"How many items do I need\?.*\| `scripts/plan_n\.py` \|", body)
    assert re.search(r"Did B beat A\?.*\| `scripts/compare\.py` \|", body)
    for banned in ("do not `cd` into `scripts/`", "shell variable", "copy the scripts", "`python3 -c`"):
        assert banned in body, banned
    assert "python3 scripts/plan_n.py --from-runs PILOT_A PILOT_B" in body
    assert "Do not count disagreements or apply a formula by hand" in body


def test_multi_task_guidance_is_one_line():
    lines = [line for line in body_of_skill_md().splitlines() if "several tasks" in line]
    assert len(lines) == 1 and "pooled" in lines[0] and "Holm" in lines[0]


def test_skill_md_is_at_most_500_lines():
    assert len((SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()) <= 500
