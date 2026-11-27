"""Message tables (English / Korean) and language selection.

Every user-visible string lives in MESSAGES. JSON report keys and verdict tokens
are language independent and never pass through this module.

Language precedence: ``--lang`` > ``EVAL_LIFT_CHECK_LANG`` > ``LC_ALL`` >
``LC_MESSAGES`` > ``LANG``; anything that does not start with ``ko`` is English.
"""
from __future__ import annotations

import argparse
from typing import Mapping, Optional, Sequence

LANGS = ("en", "ko")
ENV_VAR = "EVAL_LIFT_CHECK_LANG"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # --- compare.py --help
        "help.compare.desc": "Pair two or more eval runs item by item and decide whether the candidate really beats the baseline.",
        "help.compare.epilog": "Exit codes: 0 analysis done (whatever the verdict), 2 input or usage error, 3 join failure.",
        "help.runs": "BASELINE then one or more CANDIDATE files or folders",
        "help.format": "input format (default: auto-detect)",
        "help.id_key": "field holding the item id (default: id)",
        "help.score_key": "field holding the score (default: score; promptfoo: success)",
        "help.metric": "lm-eval metric name or Inspect scorer name",
        "help.cluster_key": "field that groups items (for example the passage id) for cluster-robust errors",
        "help.dup": "what to do with duplicate item ids: error, first, or mean (default: error)",
        "help.epochs": "repeated epochs per item: mean (average inside the item) or cluster (each epoch is a row, the item is the cluster)",
        "help.alpha": "significance level (default 0.05)",
        "help.power": "target power for the required sample size (default 0.8)",
        "help.margin": "equivalence margin on the difference (binary default 0.02; continuous: none)",
        "help.seed": "bootstrap seed (default 0)",
        "help.reps": "bootstrap replicates (default 10000)",
        "help.json": "write the full JSON report to PATH ('-' = stdout, summary suppressed)",
        "help.lang": "output language: en or ko",
        "help.h": "show this help message and exit",
        "help.positionals": "positional arguments",
        "help.options": "options",
        "help.usage": "usage: ",
        "help.prompt_idx": "promptfoo only: keep results of this promptIdx",
        # --- plan_n.py --help
        "help.plan.desc": "Plan an eval before running it: required number of items for a paired comparison, or the smallest detectable difference.",
        "help.plan.rate": "fraction of items on which the two runs disagree (0-1), binary scores",
        "help.plan.delta": "difference to detect (accuracy points as a fraction, e.g. 0.02)",
        "help.plan.n": "number of items you can afford (computes the smallest detectable difference)",
        "help.plan.sd_diff": "continuous scores: standard deviation of the per-item difference",
        "help.plan.deff": "continuous scores: design effect for clustered items (default 1)",
        "help.plan.from_runs": "estimate the disagreement rate from two existing run files (binary scores)",
        # --- errors (first stderr line is 'error: <code>: <text>')
        "err.file-not-found": "file or folder not found: {path}. Check the path; folders are accepted for lm-eval samples.",
        "err.bad-encoding": "{path} is not valid UTF-8 (first bad byte at offset {offset}). Re-save the file as UTF-8 and run again.",
        "err.unknown-format": "cannot tell the format of {path}. Pass --format jsonl|csv|lm-eval|inspect|promptfoo.",
        "err.id-missing": "{path}: row {row} has no id field '{key}'. Seen fields: {seen}. Pass --id-key with one of them.",
        "err.score-missing": "{path}: row {row} has no score field '{key}'. Seen fields: {seen}. Pass --score-key (or --metric) with one of them.",
        "err.score-not-numeric": "{path}: row {row} has score {value!r}, which is not 0/1, true/false, C/I or a number. Fix the file or pick another --score-key.",
        "err.cluster-missing": "{path}: row {row} has no cluster field '{key}'. Seen fields: {seen}.",
        "err.cluster-task": "{path}: lm-eval rows have no '{key}' field. Items are keyed by task/doc_id and the report already gives results per task. A few tasks are separate test sets, not clusters: run without --cluster-key, or name a field inside doc that groups items (for example a passage id).",
        "err.inspect-zstd": "{path} uses zstd compression that this Python cannot open. Run: inspect log dump {path} > {path}.json and pass the .json file.",
        "err.duplicate-id": "{path}: {count} duplicate item ids: {ids}. Pick a policy with --dup first (keep the first row) or --dup mean (average them), or fix the file.",
        "err.too-few-pairs": "only {n} item id(s) are common to all inputs (baseline has {n_base}, candidate has {n_cand}). The id schemes probably differ; compare the ids, or pass --id-key.",
        "err.bad-argument": "{text}",
        "err.bad-json": "{path}: not valid JSON ({reason}). Check that the file is complete.",
        "err.no-rows": "{path}: no result rows found. Check that the file is the per-item output, not a summary.",
        "bad.rate": "--discordant-rate must be greater than 0 and at most 1 (got {value}).",
        "bad.delta": "--delta must be greater than 0 and smaller than the disagreement rate (delta {delta}, rate {rate}); a difference cannot exceed the share of items that differ.",
        "bad.n": "--n must be an integer of at least 2 (got {value}).",
        "bad.mode": "give either --delta (required N) or --n (smallest detectable difference), not both and not neither.",
        "bad.need-rate": "binary planning needs --discordant-rate (or --from-runs A B); continuous planning needs --sd-diff.",
        "bad.sd": "--sd-diff must be greater than 0 (got {value}).",
        "bad.alpha": "--alpha and --power must be strictly between 0 and 1.",
        "bad.margin": "--margin must be greater than 0.",
        "bad.reps": "--reps must be at least 200.",
        "bad.runs": "give a BASELINE and at least one CANDIDATE.",
        "bad.from-runs": "--from-runs needs binary (0/1) scores in both files.",
        # --- summary
        "sum.title": "Paired eval comparison",
        "sum.inputs": "Inputs",
        "sum.input_line": "  {role}: {path} ({fmt}, {rows} rows)",
        "role.baseline": "baseline",
        "role.candidate": "candidate",
        "sum.join": "Join diagnostics",
        "sum.paired": "  paired items: {n}",
        "sum.paired_rows": "  paired items: {items} ({n} item-epoch rows, one row per epoch)",
        "sum.only_base": "  only in baseline ({n}): {ids}",
        "sum.only_cand": "  only in a candidate ({n}): {ids}",
        "sum.dups": "  duplicate ids ({n}): {ids}; policy --dup {policy}",
        "sum.hash": "  doc_hash mismatches excluded ({n}): {ids}",
        "sum.epochs": "  epochs per item: {value}; policy --epochs {policy}",
        "sum.no_issues": "  no missing, duplicate or mismatched items",
        "sum.cmp": "Candidate: {name}",
        "sum.means": "  mean: baseline {a}, candidate {b}, difference {d}",
        "sum.ci": "  95% CI of the difference: [{lo}, {hi}] ({method})",
        "sum.p": "  p = {p} ({method})",
        "sum.p_holm": "  Holm-adjusted p = {p} (adjusted over {m} candidates)",
        "sum.discordant": "  disagreements: baseline-only correct {a}, candidate-only correct {b}",
        "sum.se": "  standard error: paired {paired}, cluster-robust {cluster} ({g} clusters)",
        "sum.se_nocluster": "  standard error (paired): {paired}",
        "sum.reqn": "  required items for {target} at {power} power: N* = {n} ({method}); you have {have}, N/N* = {ratio}",
        "sum.reqn_none": "  required items: not computable ({reason})",
        "sum.mde": "  smallest detectable difference at this size: {mde}",
        "sum.verdict": "  verdict: {verdict}",
        "sum.why": "  why: {text}",
        "sum.warn": "  warning: {text}",
        "sum.seed": "Bootstrap: {reps} replicates, seed {seed}.",
        "sum.per_task": "  per task (secondary, Holm-adjusted over {m} tasks; the verdict above is for all items pooled, do not pick the best task):",
        "sum.per_task_line": "    {task}: {n} items, difference {d}, p = {p}, Holm p = {ph}",
        "sum.saved": "Full report written to {path}",
        "target.margin": "a {margin} difference",
        "target.observed": "the observed difference",
        "why.improved": "p ({p}) is below alpha ({alpha}) and the difference is positive.",
        "why.regressed": "p ({p}) is below alpha ({alpha}) and the difference is negative.",
        "why.bounded-null": "not significant, and the whole 95% CI lies inside +/-{margin}: any real difference is smaller than the margin.",
        "why.underpowered": "not significant and the 95% CI is wider than +/-{margin}: this does not show that there is no difference. More items are needed.",
        "why.underpowered-nomargin": "not significant, and no --margin was given so a bounded null cannot be declared. This does not show that there is no difference.",
        "why.underpowered-check": "not significant. The bootstrap CI fits inside +/-{margin}, but the {check_method} [{check_lo}, {check_hi}] does not: too few items or disagreements to rule out a difference of that size. This does not show that there is no difference. More items are needed.",
        "why.underpowered-zero-variance": "not significant, and every item has the same difference, so these items cannot show how large a real difference could be. This does not show that there is no difference. More items are needed.",
        "warn.few-clusters": "only {g} clusters: cluster-robust errors are unreliable below 10; prefer the cluster bootstrap CI.",
        "warn.one-cluster": "a single cluster: cluster-robust errors are undefined, falling back to item-level errors.",
        "warn.zero-variance": "every per-item difference is identical (zero variance): the t statistic is degenerate.",
        "warn.no-discordant": "no item differs between the runs: the exact test cannot reject anything.",
        "warn.no-reqn": "the observed disagreement rate is not above the margin, so the Connor formula gives no required N. That rate is only an estimate: with few items the real rate can be much higher.",
        "warn.holm-ci": "the CI is not adjusted for multiple candidates; the verdict uses the Holm-adjusted p.",
        "warn.format-guess": "{path}: format guessed as {fmt}; pass --format to be explicit.",
        "warn.lm-eval-latest": "{task}: several sample files found, using the latest ({name}).",
        "warn.prompt-idx": "{path}: results of {n} prompts found; pass --prompt-idx to choose one.",
        "warn.promptfoo-field": "{path}: score taken from '{field}'.",
        "verdict.improved": "improved",
        "verdict.regressed": "regressed",
        "verdict.bounded-null": "bounded-null",
        "verdict.underpowered": "underpowered",
        # --- method and assumption phrases (the English text also goes into the JSON report)
        "m.connor": "Connor 1987 (normal approximation for McNemar)",
        "m.paired_normal": "paired normal approximation: n = ((z_alpha/2 + z_beta) * sd_diff / delta)^2 * design effect",
        "m.ci_cluster": "cluster bootstrap percentile ({reps} replicates, seed {seed})",
        "m.ci_item": "item bootstrap percentile ({reps} replicates, seed {seed})",
        "m.p_cluster": "cluster-robust t test (CRV1 standard error, df = G - 1)",
        "m.p_mcnemar": "exact McNemar test (two-sided binomial on the disagreements)",
        "m.p_t": "paired t test (df = n - 1)",
        "m.ci_tango": "Tango score interval for paired proportions",
        "m.ci_tango_deff": "Tango score interval for paired proportions, widened by the design effect {deff}",
        "m.ci_t": "paired t interval (df = n - 1)",
        "m.ci_t_cluster": "cluster-robust t interval ({g} clusters, df = G - 1)",
        "a.rate_observed": "observed disagreement rate {rate} (items where the runs differ) is held fixed",
        "a.alpha_power": "two-sided alpha {alpha}, power {power}",
        "a.mcnemar_approx": "McNemar normal approximation; exact test power is slightly different for small N",
        "a.deff_applied": "design effect {deff} applied",
        "a.independent": "items are treated as independent (no clustering)",
        "a.sd_fixed": "standard deviation of the per-item difference {sd} is held fixed",
        "a.target_margin": "target difference {target} (the margin)",
        "a.target_observed": "target difference {target} (the observed difference)",
        "a.plan_rate": "disagreement rate {rate} (fraction of items where the runs differ) is held fixed",
        "a.plan_mcnemar": "McNemar normal approximation; items are treated as independent",
        "a.plan_deff": "design effect {deff}",
        "reason.rate_le_margin": "disagreement rate <= margin",
        "reason.zero_variance": "zero variance",
        # --- plan_n.py output
        "plan.title": "Evaluation planning",
        "plan.required": "  required items: N* = {n}",
        "plan.mde": "  smallest detectable difference with N = {n}: {mde}",
        "plan.method": "  method: {method}",
        "plan.assumption": "  assumption: {text}",
        "plan.from_runs": "  disagreement rate estimated from the runs: {rate} ({n} paired items)",
    },
    "ko": {
        "help.compare.desc": "둘 이상의 평가 실행을 문항 단위로 짝지어, 후보가 기준선보다 정말 나아졌는지 판정합니다.",
        "help.compare.epilog": "종료 코드: 0 분석 완료(판정과 무관), 2 입력·사용 오류, 3 조인 실패.",
        "help.runs": "BASELINE 다음에 CANDIDATE 파일 또는 폴더 하나 이상",
        "help.format": "입력 형식 (기본: 자동 감지)",
        "help.id_key": "문항 ID 필드 (기본: id)",
        "help.score_key": "점수 필드 (기본: score, promptfoo 는 success)",
        "help.metric": "lm-eval 지표 이름 또는 Inspect scorer 이름",
        "help.cluster_key": "군집 표준오차를 위해 문항을 묶는 필드(예: 지문 ID)",
        "help.dup": "중복 문항 ID 처리: error, first, mean (기본: error)",
        "help.epochs": "문항당 반복(에포크) 처리: mean(문항 안 평균) 또는 cluster(에포크를 각각 행으로, 문항을 군집으로)",
        "help.alpha": "유의수준 (기본 0.05)",
        "help.power": "필요 표본 수 계산의 목표 검정력 (기본 0.8)",
        "help.margin": "차이의 동등성 한계 (이진 기본 0.02, 연속 점수는 없음)",
        "help.seed": "부트스트랩 시드 (기본 0)",
        "help.reps": "부트스트랩 반복 수 (기본 10000)",
        "help.json": "전체 JSON 보고서를 PATH 에 저장 ('-' 면 stdout, 요약은 출력 안 함)",
        "help.lang": "출력 언어: en 또는 ko",
        "help.h": "이 도움말을 보여 주고 종료합니다",
        "help.positionals": "위치 인자",
        "help.options": "옵션",
        "help.usage": "사용법: ",
        "help.prompt_idx": "promptfoo 전용: 이 promptIdx 의 결과만 사용",
        "help.plan.desc": "평가를 돌리기 전에 계획합니다: 쌍대 비교에 필요한 문항 수, 또는 검출 가능한 최소 차이.",
        "help.plan.rate": "두 실행의 결과가 서로 다른 문항의 비율(0~1), 이진 점수용",
        "help.plan.delta": "검출하려는 차이(정확도 차이를 비율로, 예: 0.02)",
        "help.plan.n": "쓸 수 있는 문항 수(검출 가능한 최소 차이를 계산)",
        "help.plan.sd_diff": "연속 점수: 문항별 차이의 표준편차",
        "help.plan.deff": "연속 점수: 군집 문항의 설계 효과 (기본 1)",
        "help.plan.from_runs": "기존 실행 파일 두 개에서 불일치율을 추정(이진 점수)",
        "err.file-not-found": "파일 또는 폴더를 찾을 수 없습니다: {path}. 경로를 확인하세요. lm-eval 샘플은 폴더도 받습니다.",
        "err.bad-encoding": "{path} 는 올바른 UTF-8 이 아닙니다(잘못된 첫 바이트 위치 {offset}). 파일을 UTF-8 로 다시 저장한 뒤 실행하세요.",
        "err.unknown-format": "{path} 의 형식을 알 수 없습니다. --format jsonl|csv|lm-eval|inspect|promptfoo 를 지정하세요.",
        "err.id-missing": "{path}: {row}번째 행에 ID 필드 '{key}' 가 없습니다. 보이는 필드: {seen}. --id-key 로 그중 하나를 지정하세요.",
        "err.score-missing": "{path}: {row}번째 행에 점수 필드 '{key}' 가 없습니다. 보이는 필드: {seen}. --score-key(또는 --metric)로 그중 하나를 지정하세요.",
        "err.score-not-numeric": "{path}: {row}번째 행의 점수 {value!r} 는 0/1, true/false, C/I, 숫자가 아닙니다. 파일을 고치거나 다른 --score-key 를 고르세요.",
        "err.cluster-missing": "{path}: {row}번째 행에 군집 필드 '{key}' 가 없습니다. 보이는 필드: {seen}.",
        "err.cluster-task": "{path}: lm-eval 행에는 '{key}' 필드가 없습니다. 문항 키는 task/doc_id 이고 보고서에 태스크별 결과가 이미 있습니다. 몇 개의 태스크는 군집이 아니라 서로 다른 시험지입니다: --cluster-key 없이 실행하거나, 문항을 묶는 doc 안의 필드(예: 지문 ID)를 지정하세요.",
        "err.inspect-zstd": "{path} 는 이 Python 이 열 수 없는 zstd 압축입니다. inspect log dump {path} > {path}.json 을 실행하고 .json 파일을 넘기세요.",
        "err.duplicate-id": "{path}: 중복 문항 ID {count}개: {ids}. --dup first(첫 행 유지) 또는 --dup mean(평균)으로 정책을 고르거나 파일을 고치세요.",
        "err.too-few-pairs": "모든 입력에 공통인 문항 ID 가 {n}개뿐입니다(기준선 {n_base}개, 후보 {n_cand}개). ID 체계가 다른 것 같습니다. ID 를 비교하거나 --id-key 를 지정하세요.",
        "err.bad-argument": "{text}",
        "err.bad-json": "{path}: 올바른 JSON 이 아닙니다({reason}). 파일이 끝까지 저장됐는지 확인하세요.",
        "err.no-rows": "{path}: 결과 행이 없습니다. 요약이 아니라 문항별 출력 파일인지 확인하세요.",
        "bad.rate": "--discordant-rate 는 0 보다 크고 1 이하여야 합니다(받은 값 {value}).",
        "bad.delta": "--delta 는 0 보다 크고 불일치율보다 작아야 합니다(delta {delta}, 불일치율 {rate}). 차이는 서로 다른 문항의 비율을 넘을 수 없습니다.",
        "bad.n": "--n 은 2 이상의 정수여야 합니다(받은 값 {value}).",
        "bad.mode": "--delta(필요 N) 와 --n(검출 가능한 최소 차이) 중 하나만 지정하세요.",
        "bad.need-rate": "이진 점수 계획에는 --discordant-rate(또는 --from-runs A B), 연속 점수 계획에는 --sd-diff 가 필요합니다.",
        "bad.sd": "--sd-diff 는 0 보다 커야 합니다(받은 값 {value}).",
        "bad.alpha": "--alpha 와 --power 는 0 과 1 사이(양 끝 제외)여야 합니다.",
        "bad.margin": "--margin 은 0 보다 커야 합니다.",
        "bad.reps": "--reps 는 200 이상이어야 합니다.",
        "bad.runs": "BASELINE 과 CANDIDATE 를 하나 이상 지정하세요.",
        "bad.from-runs": "--from-runs 는 두 파일 모두 이진(0/1) 점수여야 합니다.",
        "sum.title": "쌍대 평가 비교",
        "sum.inputs": "입력",
        "sum.input_line": "  {role}: {path} ({fmt}, {rows}행)",
        "role.baseline": "기준선",
        "role.candidate": "후보",
        "sum.join": "조인 진단",
        "sum.paired": "  짝지은 문항: {n}개",
        "sum.paired_rows": "  짝지은 문항: {items}개 (문항×에포크 {n}행, 에포크마다 한 행)",
        "sum.only_base": "  기준선에만 있음 ({n}): {ids}",
        "sum.only_cand": "  후보에만 있음 ({n}): {ids}",
        "sum.dups": "  중복 ID ({n}): {ids}; 정책 --dup {policy}",
        "sum.hash": "  doc_hash 불일치로 제외 ({n}): {ids}",
        "sum.epochs": "  문항당 에포크: {value}; 정책 --epochs {policy}",
        "sum.no_issues": "  누락·중복·불일치 문항 없음",
        "sum.cmp": "후보: {name}",
        "sum.means": "  평균: 기준선 {a}, 후보 {b}, 차이 {d}",
        "sum.ci": "  차이의 95% 신뢰구간: [{lo}, {hi}] ({method})",
        "sum.p": "  p = {p} ({method})",
        "sum.p_holm": "  Holm 보정 p = {p} (후보 {m}개에 대해 보정)",
        "sum.discordant": "  불일치: 기준선만 정답 {a}, 후보만 정답 {b}",
        "sum.se": "  표준오차: 쌍대 {paired}, 군집 {cluster} (군집 {g}개)",
        "sum.se_nocluster": "  표준오차(쌍대): {paired}",
        "sum.reqn": "  검정력 {power}로 {target}를 가리는 데 필요한 문항: N* = {n} ({method}); 현재 {have}개, N/N* = {ratio}",
        "sum.reqn_none": "  필요 문항 수: 계산 불가 ({reason})",
        "sum.mde": "  이 표본 크기에서 검출 가능한 최소 차이: {mde}",
        "sum.verdict": "  판정: {verdict}",
        "sum.why": "  이유: {text}",
        "sum.warn": "  경고: {text}",
        "sum.seed": "부트스트랩: {reps}회, 시드 {seed}.",
        "sum.per_task": "  태스크별(보조, 태스크 {m}개에 대해 Holm 보정; 판정은 위의 전체 문항 합동 결과이며 가장 좋은 태스크만 골라 쓰지 마세요):",
        "sum.per_task_line": "    {task}: {n}개 문항, 차이 {d}, p = {p}, Holm p = {ph}",
        "sum.saved": "전체 보고서 저장 위치: {path}",
        "target.margin": "{margin} 차이",
        "target.observed": "관측된 차이",
        "why.improved": "p({p})가 alpha({alpha})보다 작고 차이가 양수입니다.",
        "why.regressed": "p({p})가 alpha({alpha})보다 작고 차이가 음수입니다.",
        "why.bounded-null": "유의하지 않고 95% 신뢰구간 전체가 +/-{margin} 안에 있습니다. 실제 차이가 있어도 한계보다 작습니다.",
        "why.underpowered": "유의하지 않고 95% 신뢰구간이 +/-{margin} 보다 넓습니다. 차이가 없다는 뜻이 아닙니다. 문항이 더 필요합니다.",
        "why.underpowered-nomargin": "유의하지 않고 --margin 을 주지 않아 '차이 없음 범위'를 선언할 수 없습니다. 차이가 없다는 뜻이 아닙니다.",
        "why.underpowered-check": "유의하지 않습니다. 부트스트랩 신뢰구간은 +/-{margin} 안에 있지만 {check_method} [{check_lo}, {check_hi}] 는 그 밖으로 나갑니다. 문항이나 불일치가 너무 적어 그만한 차이를 배제할 수 없습니다. 차이가 없다는 뜻이 아닙니다. 문항이 더 필요합니다.",
        "why.underpowered-zero-variance": "유의하지 않고 모든 문항의 차이가 똑같아, 이 문항들로는 실제 차이가 얼마나 클 수 있는지 알 수 없습니다. 차이가 없다는 뜻이 아닙니다. 문항이 더 필요합니다.",
        "warn.few-clusters": "군집이 {g}개뿐입니다. 10개 미만이면 군집 표준오차가 불안정하니 군집 부트스트랩 신뢰구간을 우선 보세요.",
        "warn.one-cluster": "군집이 하나뿐이라 군집 표준오차를 정의할 수 없어 문항 단위 오차로 대신합니다.",
        "warn.zero-variance": "모든 문항별 차이가 같아(분산 0) t 통계량이 퇴화합니다.",
        "warn.no-discordant": "두 실행 사이에 결과가 다른 문항이 없어 정확 검정으로 아무것도 기각할 수 없습니다.",
        "warn.no-reqn": "관측된 불일치율이 한계(margin)보다 크지 않아 Connor 공식으로 필요 문항 수를 구할 수 없습니다. 이 불일치율도 추정값이라 문항이 적으면 실제 비율은 훨씬 높을 수 있습니다.",
        "warn.holm-ci": "신뢰구간은 다중 후보 보정을 하지 않았고, 판정은 Holm 보정 p 를 씁니다.",
        "warn.format-guess": "{path}: 형식을 {fmt} 로 추정했습니다. 확실히 하려면 --format 을 지정하세요.",
        "warn.lm-eval-latest": "{task}: 샘플 파일이 여러 개라 가장 최근 것({name})을 씁니다.",
        "warn.prompt-idx": "{path}: 프롬프트 {n}개의 결과가 있습니다. --prompt-idx 로 하나를 고르세요.",
        "warn.promptfoo-field": "{path}: 점수를 '{field}' 에서 읽었습니다.",
        "verdict.improved": "improved",
        "verdict.regressed": "regressed",
        "verdict.bounded-null": "bounded-null",
        "verdict.underpowered": "underpowered",
        "m.connor": "Connor 1987 (McNemar 정규 근사)",
        "m.paired_normal": "쌍대 정규 근사: n = ((z_alpha/2 + z_beta) * sd_diff / delta)^2 * 설계 효과",
        "m.ci_cluster": "군집 부트스트랩 백분위수 ({reps}회, 시드 {seed})",
        "m.ci_item": "문항 부트스트랩 백분위수 ({reps}회, 시드 {seed})",
        "m.p_cluster": "군집 강건 t 검정 (CRV1 표준오차, 자유도 = G - 1)",
        "m.p_mcnemar": "정확 McNemar 검정 (불일치 문항에 대한 양측 이항 검정)",
        "m.p_t": "쌍대 t 검정 (자유도 = n - 1)",
        "m.ci_tango": "쌍대 비율 Tango 점수 구간",
        "m.ci_tango_deff": "쌍대 비율 Tango 점수 구간(설계 효과 {deff} 만큼 넓힘)",
        "m.ci_t": "쌍대 t 구간 (자유도 = n - 1)",
        "m.ci_t_cluster": "군집 강건 t 구간 (군집 {g}개, 자유도 = G - 1)",
        "a.rate_observed": "관측된 불일치율 {rate}(두 실행의 결과가 다른 문항 비율)을 고정값으로 둡니다",
        "a.alpha_power": "양측 alpha {alpha}, 검정력 {power}",
        "a.mcnemar_approx": "McNemar 정규 근사. 표본이 작으면 정확 검정의 검정력은 조금 다릅니다",
        "a.deff_applied": "설계 효과 {deff}를 적용했습니다",
        "a.independent": "문항을 서로 독립으로 봅니다(군집 없음)",
        "a.sd_fixed": "문항별 차이의 표준편차 {sd}를 고정값으로 둡니다",
        "a.target_margin": "목표 차이 {target}(한계값)",
        "a.target_observed": "목표 차이 {target}(관측된 차이)",
        "a.plan_rate": "불일치율 {rate}(두 실행의 결과가 다른 문항 비율)을 고정값으로 둡니다",
        "a.plan_mcnemar": "McNemar 정규 근사. 문항을 서로 독립으로 봅니다",
        "a.plan_deff": "설계 효과 {deff}",
        "reason.rate_le_margin": "불일치율이 한계값 이하",
        "reason.zero_variance": "분산 0",
        "plan.title": "평가 계획",
        "plan.required": "  필요 문항 수: N* = {n}",
        "plan.mde": "  N = {n} 에서 검출 가능한 최소 차이: {mde}",
        "plan.method": "  방법: {method}",
        "plan.assumption": "  가정: {text}",
        "plan.from_runs": "  실행 결과로 추정한 불일치율: {rate} (짝지은 문항 {n}개)",
    },
}


def detect_lang(cli_value: Optional[str], env: Mapping[str, str]) -> str:
    """Pick the output language. ``cli_value`` is the ``--lang`` argument or None."""
    if cli_value in LANGS:
        return str(cli_value)
    candidates: Sequence[Optional[str]] = (
        env.get(ENV_VAR),
        env.get("LC_ALL"),
        env.get("LC_MESSAGES"),
        env.get("LANG"),
    )
    for value in candidates:
        if value:
            # The first non-empty source decides, as with POSIX locale lookup.
            return "ko" if value.lower().startswith("ko") else "en"
    return "en"


def peek_lang(argv: Sequence[str], env: Mapping[str, str]) -> str:
    """Find ``--lang`` in raw argv so ``--help`` can already speak the right language."""
    value: Optional[str] = None
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--lang="):
            value = arg.split("=", 1)[1]
    return detect_lang(value, env)


def phrase(key: str, /, **fields: object) -> tuple[str, dict]:
    """English text for the JSON report plus a language-neutral code record.

    The human summary re-renders the record in the chosen language with ``tr``.
    """
    return tr("en", key, **fields), {"code": key, **fields}


def localize_parser(parser: argparse.ArgumentParser, lang: str) -> argparse.ArgumentParser:
    """Replace argparse's built-in English section titles, usage prefix and -h text."""
    parser._positionals.title = tr(lang, "help.positionals")
    parser._optionals.title = tr(lang, "help.options")
    for action in parser._actions:
        if action.dest == "help":
            action.help = tr(lang, "help.h")

    class Formatter(argparse.HelpFormatter):
        def add_usage(self, usage, actions, groups, prefix=None):  # type: ignore[no-untyped-def]
            super().add_usage(usage, actions, groups, tr(lang, "help.usage") if prefix is None else prefix)

    parser.formatter_class = Formatter
    return parser


def tr(lang: str, key: str, /, **fields: object) -> str:
    """Look up ``key`` in ``lang`` and fill in ``fields``."""
    return MESSAGES[lang][key].format(**fields)
