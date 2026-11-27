"""Verdict rules and report assembly.

Verdicts (decided in this order, using the Holm-adjusted p when there are
several candidates):
  improved      p < alpha and the difference is positive
  regressed     p < alpha and the difference is negative
  bounded-null  not significant and both the 95% bootstrap CI and the analytic
                check interval (Tango score / t) lie inside (-margin, +margin)
  underpowered  everything else; the report carries the required N
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import _stats as st
from _i18n import phrase
from _join import Paired

TOOL_VERSION = "0.1.0"
VERDICTS = ("improved", "regressed", "bounded-null", "underpowered")
BINARY_DEFAULT_MARGIN = 0.02

CONNOR, CONNOR_CODE = phrase("m.connor")
PAIRED_NORMAL, PAIRED_NORMAL_CODE = phrase("m.paired_normal")


def _deff_phrase(design_effect: float) -> tuple[str, dict]:
    if design_effect != 1.0:
        return phrase("a.deff_applied", deff=f"{design_effect:.6f}")
    return phrase("a.independent")


@dataclass
class Settings:
    alpha: float = 0.05
    power: float = 0.8
    margin: Optional[float] = None
    seed: int = 0
    reps: int = 10000


def _inside(interval: tuple[float, float], margin: float) -> bool:
    return interval[0] > -margin and interval[1] < margin


def decide(p_adj: Optional[float], diff: float, ci: tuple[float, float], alpha: float,
           margin: Optional[float], check: Optional[tuple[float, float]] = None) -> tuple[str, str]:
    """Return (verdict, reason_key). The reason key indexes the ``why.*`` messages.

    bounded-null needs two intervals inside the margin: the bootstrap CI and an
    analytic check interval (Tango score for 0/1 scores, t for continuous). The
    percentile bootstrap collapses to [0, 0] when no item disagrees, so on its own
    it would call 10 identical items a tight null."""
    if p_adj is not None and p_adj < alpha:
        return ("improved", "improved") if diff > 0 else ("regressed", "regressed")
    if margin is None:
        return "underpowered", "underpowered-nomargin"
    if not _inside(ci, margin):
        return "underpowered", "underpowered"
    # 부트스트랩 구간만 좁은 경우: 분석적 구간으로 한 번 더 확인한다
    if check is None:
        return "underpowered", "underpowered-zero-variance"
    if not _inside(check, margin):
        return "underpowered", "underpowered-check"
    return "bounded-null", "bounded-null"


def _check_interval(binary: bool, n: int, diff: float, b: int, c: int, paired_se: float,
                    cl: Optional[dict], design_effect: float) -> tuple[Optional[tuple[float, float]], tuple[str, dict]]:
    """Analytic 95% interval used as a second opinion before bounded-null.

    0/1 scores: Tango score interval on the disagreement counts, widened by the
    square root of the design effect when clustered. Continuous scores: t interval
    with the paired SE (df n-1) or the cluster-robust SE (df G-1); None when the SE
    is 0, because then nothing says how large a difference could be."""
    if binary:
        lo, hi = st.tango_ci(c, b, n)
        if design_effect > 1.0:
            # 군집이면 문항이 독립이 아니다 → 구간 폭을 sqrt(설계 효과) 배로 넓힌다
            k = math.sqrt(design_effect)
            lo, hi = max(-1.0, diff - (diff - lo) * k), min(1.0, diff + (hi - diff) * k)
            return (lo, hi), phrase("m.ci_tango_deff", deff=f"{design_effect:.6f}")
        return (lo, hi), phrase("m.ci_tango")
    if cl is not None:
        return st.t_interval(diff, cl["se"], cl["df"]), phrase("m.ci_t_cluster", g=cl["clusters"])
    return st.t_interval(diff, paired_se, n - 1), phrase("m.ci_t")


def _required_n(binary: bool, n: int, diffs: list[float], b: int, c: int, margin: Optional[float],
                design_effect: float, s: Settings) -> tuple[dict, list[dict], Optional[float]]:
    """Required N block, warnings and MDE for one comparison."""
    warnings: list[dict] = []
    n_eff = max(2, int(n / design_effect)) if design_effect > 0 else n
    if binary:
        rate = (b + c) / n
        target_delta = margin
        raw = st.required_n_for_delta(rate, margin, s.alpha, s.power) if margin else None
        observed = st.mcnemar_required_n(b / n, c / n, s.alpha, s.power)
        needed = None if raw is None else math.ceil(raw * design_effect - 1e-9)
        if needed is None:
            warnings.append({"code": "no-reqn"})
        parts = [phrase("a.rate_observed", rate=f"{rate:.6f}"), phrase("a.alpha_power", alpha=s.alpha, power=s.power),
                 phrase("a.mcnemar_approx"), _deff_phrase(design_effect)]
        assumptions = [text for text, _code in parts]
        n_observed = None if observed is None else math.ceil(observed * design_effect - 1e-9)
        mde = st.mde_binary(n_eff, rate, s.alpha, s.power) if rate > 0 else None
        block = {
            "n": needed, "n_observed_effect": n_observed, "target_delta": target_delta,
            "method": CONNOR, "assumptions": assumptions,
            "method_code": CONNOR_CODE, "assumption_codes": [code for _text, code in parts],
            "ratio": None if not needed else n / needed, "design_effect": design_effect,
        }
        return block, warnings, mde
    sd = st.sample_sd(diffs)
    mean_diff = st.mean(diffs)
    target = margin if margin else abs(mean_diff)
    needed = st.required_n_continuous(sd, target, s.alpha, s.power, design_effect) if target else None
    parts = [phrase("a.sd_fixed", sd=f"{sd:.6f}"),
             phrase("a.target_margin" if margin else "a.target_observed", target=f"{target:.6f}"),
             phrase("a.alpha_power", alpha=s.alpha, power=s.power), _deff_phrase(design_effect)]
    assumptions = [text for text, _code in parts]
    block = {
        "n": needed, "n_observed_effect": st.required_n_continuous(sd, abs(mean_diff), s.alpha, s.power, design_effect),
        "target_delta": target or None, "method": PAIRED_NORMAL, "assumptions": assumptions,
        "method_code": PAIRED_NORMAL_CODE, "assumption_codes": [code for _text, code in parts],
        "ratio": None if not needed else n / needed, "design_effect": design_effect,
    }
    mde = st.mde_continuous(n, sd, s.alpha, s.power, design_effect)
    return block, warnings, mde


def _compare_one(name: str, base: list[float], cand: list[float], clusters: Optional[list[str]],
                 binary: bool, margin: Optional[float], s: Settings) -> dict:
    n = len(base)
    diffs = [y - x for x, y in zip(base, cand)]
    diff = st.mean(diffs)
    warnings: list[dict] = []
    b = sum(1 for x, y in zip(base, cand) if x == 1.0 and y == 0.0) if binary else 0
    c = sum(1 for x, y in zip(base, cand) if x == 0.0 and y == 1.0) if binary else 0
    paired_se = st.paired_se(diffs)
    use_clusters = clusters is not None
    cl = None
    if use_clusters:
        cl = st.cluster_t(diffs, clusters)  # type: ignore[arg-type]
        if cl["se"] is None:
            warnings.append({"code": "one-cluster"})
            use_clusters = False
        else:
            for code in cl["warnings"]:
                if code == "few-clusters":
                    warnings.append({"code": "few-clusters", "g": cl["clusters"]})
                elif code == "zero-variance":
                    warnings.append({"code": "zero-variance"})
    if use_clusters:
        p = cl["p"]
        p_method, p_code = phrase("m.p_cluster")
        ci = st.bootstrap_ci(diffs, clusters, s.reps, s.seed)
        ci_method, ci_code = phrase("m.ci_cluster", reps=s.reps, seed=s.seed)
    elif binary:
        p = st.mcnemar_exact(b, c)
        p_method, p_code = phrase("m.p_mcnemar")
        ci = st.bootstrap_ci(diffs, None, s.reps, s.seed)
        ci_method, ci_code = phrase("m.ci_item", reps=s.reps, seed=s.seed)
        if b + c == 0:
            warnings.append({"code": "no-discordant"})
    else:
        tt = st.paired_t(diffs)
        p = tt["p"]
        p_method, p_code = phrase("m.p_t")
        ci = st.bootstrap_ci(diffs, None, s.reps, s.seed)
        ci_method, ci_code = phrase("m.ci_item", reps=s.reps, seed=s.seed)
        if "zero-variance" in tt["warnings"]:
            warnings.append({"code": "zero-variance"})
    design_effect = 1.0
    if use_clusters and paired_se > 0:
        design_effect = (cl["se"] / paired_se) ** 2
    req, req_warnings, mde = _required_n(binary, n, diffs, b, c, margin, design_effect, s)
    warnings.extend(req_warnings)
    check, (check_method, check_code) = _check_interval(binary, n, diff, b, c, paired_se,
                                                        cl if use_clusters else None, design_effect)
    comparison = {
        "candidate": name,
        "mean_baseline": st.mean(base),
        "mean_candidate": st.mean(cand),
        "diff": diff,
        "ci95": [ci[0], ci[1]],
        "ci_method": ci_method,
        "ci_method_code": ci_code,
        # bounded-null 은 이 분석적 구간도 margin 안에 있어야 한다(None = 표준오차 0)
        "ci95_check": None if check is None else [check[0], check[1]],
        "ci_check_method": check_method,
        "ci_check_method_code": check_code,
        "p": p,
        "p_method": p_method,
        "p_method_code": p_code,
        "p_holm": p,
        "discordant": {"baseline_only": b, "candidate_only": c} if binary else None,
        "se": {"paired": paired_se, "cluster": cl["se"] if use_clusters else None,
               "clusters": cl["clusters"] if use_clusters else None},
        "required_n": req,
        "mde": mde,
        "verdict": "",
        "warnings": warnings,
    }
    if binary:
        # Reference only: what an unpaired two-proportion z test would say. Never cite it.
        comparison["p_unpaired_z_reference"] = _unpaired_z_p(base, cand)
        if use_clusters:
            comparison["p_mcnemar_unclustered"] = st.mcnemar_exact(b, c)
    return comparison


def _unpaired_z_p(base: list[float], cand: list[float]) -> Optional[float]:
    n = len(base)
    pa, pb = sum(base) / n, sum(cand) / n
    pool = (sum(base) + sum(cand)) / (2 * n)
    if pool in (0.0, 1.0):
        return None
    z = (pb - pa) / math.sqrt(pool * (1 - pool) * 2 / n)
    return 2 * (1 - st._NORMAL.cdf(abs(z)))


def per_task(base: list[float], cand: list[float], tasks: list[str], binary: bool) -> list[dict]:
    """Secondary breakdown by lm-eval task, Holm-adjusted over the tasks.

    The verdict stays the pooled one: picking the best task after looking at the
    data is the forking-paths error, so each task p is also given Holm-adjusted."""
    rows = []
    for task in sorted(set(tasks)):
        a = [x for x, t in zip(base, tasks) if t == task]
        b = [y for y, t in zip(cand, tasks) if t == task]
        diffs = [y - x for x, y in zip(a, b)]
        entry: dict = {"task": task, "n_paired": len(a), "mean_baseline": st.mean(a), "mean_candidate": st.mean(b),
                       "diff": st.mean(diffs)}
        if binary:
            only_base = sum(1 for x, y in zip(a, b) if x == 1.0 and y == 0.0)
            only_cand = sum(1 for x, y in zip(a, b) if x == 0.0 and y == 1.0)
            entry["discordant"] = {"baseline_only": only_base, "candidate_only": only_cand}
            entry["p"] = st.mcnemar_exact(only_base, only_cand)
            entry["p_method_code"] = {"code": "m.p_mcnemar"}
        else:
            # 태스크 문항이 1개면 t 검정을 할 수 없다 → p 없음
            entry["p"] = st.paired_t(diffs)["p"] if len(diffs) > 1 else None
            entry["p_method_code"] = {"code": "m.p_t"}
        rows.append(entry)
    adjusted = st.holm([r["p"] if r["p"] is not None else 1.0 for r in rows])
    for entry, p_adj in zip(rows, adjusted):
        entry["p_holm_tasks"] = p_adj if entry["p"] is not None else None
    return rows


def analyze(paired: Paired, names: list[str], s: Settings) -> tuple[list[dict], float | None]:
    """Compare every candidate with the baseline. Returns (comparisons, margin used)."""
    margin = s.margin if s.margin is not None else (BINARY_DEFAULT_MARGIN if paired.binary else None)
    comparisons = []
    for j, name in enumerate(names, start=1):
        comparisons.append(_compare_one(name, paired.scores[0], paired.scores[j], paired.clusters,
                                        paired.binary, margin, s))
    adjusted = st.holm([c["p"] if c["p"] is not None else 1.0 for c in comparisons])
    for comp, p_adj in zip(comparisons, adjusted):
        comp["p_holm"] = p_adj if len(comparisons) > 1 else comp["p"]
        if len(comparisons) > 1:
            comp["warnings"].append({"code": "holm-ci"})
        comp["verdict"], comp["verdict_reason"] = decide(
            comp["p_holm"], comp["diff"], (comp["ci95"][0], comp["ci95"][1]), s.alpha, margin,
            None if comp["ci95_check"] is None else (comp["ci95_check"][0], comp["ci95_check"][1]))
    if paired.tasks is not None:
        for j, comp in enumerate(comparisons, start=1):
            comp["per_task"] = per_task(paired.scores[0], paired.scores[j], paired.tasks, paired.binary)
    return comparisons, margin


def build_report(inputs: list[dict], paired: Paired, comparisons: list[dict], s: Settings,
                 margin: Optional[float], loader_warnings: list[dict]) -> dict:
    """Assemble the language-neutral JSON report."""
    return {
        "tool_version": TOOL_VERSION,
        "inputs": inputs,
        "join": paired.diagnostics,
        "score_type": "binary" if paired.binary else "continuous",
        "settings": {"alpha": s.alpha, "power": s.power, "margin": margin, "seed": s.seed, "reps": s.reps,
                     "clustered": paired.clusters is not None},
        "comparisons": comparisons,
        "warnings": loader_warnings,
    }
