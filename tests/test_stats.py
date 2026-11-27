"""AC-1: statistics agree with scipy/statsmodels oracle values and handle edges."""
import math

import pytest

import _stats as st
from _join import join_runs
from _loaders import load_run
from helpers import EXPECTED, FX, READING

R = EXPECTED["reading"]


def reading_pair():
    runs = [load_run(str(READING / "run_a.jsonl"), cluster_key="passage"),
            load_run(str(READING / "run_b.jsonl"), cluster_key="passage")]
    return join_runs(runs, "first", "mean")


def test_mcnemar_matches_oracle_on_reading_fixture():
    paired = reading_pair()
    a, b = paired.scores
    only_a = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)
    only_b = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)
    assert (only_a, only_b) == (R["n10"], R["n01"])
    assert st.mcnemar_exact(only_a, only_b) == pytest.approx(R["mcnemar_exact_p_statsmodels"], abs=1e-12)
    assert st.mcnemar_exact(only_a, only_b) == pytest.approx(R["binomtest_p_scipy"], abs=1e-12)


@pytest.mark.parametrize("b,c,expected", [
    (0, 0, 1.0),                 # nothing differs: cannot reject
    (0, 10, 2 / 2 ** 10),        # one-sided discordance is the exact tail, doubled
    (10, 0, 2 / 2 ** 10),
    (5, 5, 1.0),                 # doubled tail is capped at 1
    (1, 0, 1.0),
])
def test_mcnemar_edges(b, c, expected):
    assert st.mcnemar_exact(b, c) == pytest.approx(expected, abs=1e-15)


def test_mcnemar_large_counts_do_not_overflow():
    assert 0.0 <= st.mcnemar_exact(900, 1100) <= 1.0


@pytest.mark.parametrize("row", EXPECTED["t_cdf"], ids=lambda r: f"t={r['t']},df={r['df']}")
def test_t_cdf_matches_scipy(row):
    assert st.t_cdf(row["t"], row["df"]) == pytest.approx(row["cdf"], abs=1e-9)


@pytest.mark.parametrize("row", EXPECTED["t_ppf"], ids=lambda r: f"p={r['p']},df={r['df']}")
def test_t_quantile_matches_scipy(row):
    assert st.t_quantile(row["p"], row["df"]) == pytest.approx(row["q"], abs=1e-8)


def test_t_cdf_edges():
    assert st.t_cdf(math.inf, 5) == 1.0
    assert st.t_cdf(-math.inf, 5) == 0.0
    assert st.t_cdf(0.0, 3) == pytest.approx(0.5, abs=1e-15)
    with pytest.raises(ValueError):
        st.t_cdf(1.0, 0)
    with pytest.raises(ValueError):
        st.t_quantile(1.0, 5)


def test_cluster_se_matches_statsmodels():
    paired = reading_pair()
    a, b = paired.scores
    diffs = [y - x for x, y in zip(a, b)]
    res = st.cluster_se(diffs, paired.clusters)
    assert res["se"] == pytest.approx(R["cluster_se"], abs=1e-9)
    assert res["clusters"] == R["clusters"]
    out = st.cluster_t(diffs, paired.clusters)
    assert out["p"] == pytest.approx(R["cluster_t_p"], abs=1e-9)


def test_cluster_se_degenerate_inputs_return_values_not_exceptions():
    one = st.cluster_se([1.0, 0.0, 1.0], ["g", "g", "g"])
    assert one["se"] is None and one["warnings"] == ["one-cluster"]
    few = st.cluster_se([1.0, 0.0, 1.0, 0.0], ["a", "a", "b", "b"])
    assert few["se"] is not None and "few-clusters" in few["warnings"]
    flat = st.cluster_t([0.0, 0.0, 0.0, 0.0], ["a", "a", "b", "b"])
    assert flat["p"] == 1.0 and "zero-variance" in flat["warnings"]
    assert st.cluster_t([1.0, 1.0], ["a", "a"])["p"] is None


def test_paired_t_matches_scipy():
    from _loaders import load_run as lr
    runs = [lr(str(FX / "rubric" / "run_a.jsonl")), lr(str(FX / "rubric" / "run_b.jsonl"))]
    paired = join_runs(runs, "error", "mean")
    diffs = [y - x for x, y in zip(*paired.scores)]
    res = st.paired_t(diffs)
    assert res["t"] == pytest.approx(EXPECTED["rubric"]["paired_t_stat"], abs=1e-9)
    assert res["p"] == pytest.approx(EXPECTED["rubric"]["paired_t_p"], abs=1e-9)


def test_paired_t_zero_variance():
    same = st.paired_t([0.0, 0.0, 0.0])
    assert same["p"] == 1.0 and "zero-variance" in same["warnings"]
    shifted = st.paired_t([0.5, 0.5, 0.5])
    assert shifted["p"] == 0.0 and math.isinf(shifted["t"])


def test_holm_matches_oracle_and_known_values():
    assert st.holm(EXPECTED["holm"]["in"]) == pytest.approx(EXPECTED["holm"]["out"], abs=1e-12)
    assert st.holm([0.01, 0.04, 0.03, 0.2]) == pytest.approx([0.04, 0.09, 0.09, 0.2])
    assert st.holm([0.5]) == [0.5]
    assert st.holm([0.6, 0.7]) == [1.0, 1.0]
    assert st.holm([]) == []


def test_connor_required_n():
    n = 299
    assert st.mcnemar_required_n(R["n10"] / n, R["n01"] / n) == R["connor_n_observed"] == 304
    assert st.required_n_for_delta(0.16, 0.02) == EXPECTED["connor_rate_0.16_delta_0.02"]
    assert st.mcnemar_required_n(0.1, 0.1) is None          # no difference to detect
    assert st.required_n_for_delta(0.01, 0.02) is None       # delta larger than the disagreement rate


def test_mde_is_inverse_of_required_n():
    mde = st.mde_binary(3138, 0.16)
    assert mde == pytest.approx(0.02, abs=2e-4)
    assert st.mde_binary(1, 0.16) is None
    assert st.mde_binary(5, 0.01) is None                    # not even a full-rate difference is detectable
    assert st.mde_binary(100, 0.0) is None


def test_continuous_required_n_and_mde():
    spec = EXPECTED["continuous_required_n"]
    assert st.required_n_continuous(spec["sd"], spec["delta"]) == spec["n"]
    assert st.required_n_continuous(0.0, 0.1) is None
    assert st.required_n_continuous(0.2, 0.03, design_effect=2.0) > spec["n"]
    mde = st.mde_continuous(spec["n"], spec["sd"])
    assert mde == pytest.approx(spec["delta"], rel=0.01)
    assert st.mde_continuous(1, 0.2) is None


def test_bootstrap_is_deterministic_per_seed_and_changes_with_seed():
    diffs = [0.1 * (i % 7) - 0.2 for i in range(47)]
    first = st.bootstrap_ci(diffs, reps=2000, seed=3)
    assert first == st.bootstrap_ci(diffs, reps=2000, seed=3)
    assert first != st.bootstrap_ci(diffs, reps=2000, seed=4)
    assert first[0] < st.mean(diffs) < first[1]


def test_cluster_bootstrap_resamples_whole_clusters():
    diffs = [1.0, 1.0, 0.0, 0.0, -1.0, -1.0]
    clusters = ["a", "a", "b", "b", "c", "c"]
    lo, hi = st.bootstrap_ci(diffs, clusters, reps=500, seed=1)
    assert lo <= 0.0 <= hi
    assert (lo, hi) == st.bootstrap_ci(diffs, clusters, reps=500, seed=1)


def test_mean_sd_helpers():
    assert st.mean([1, 2, 3]) == 2
    assert st.sample_sd([1.0]) == 0.0
    assert st.paired_se([]) == 0.0


def test_mcnemar_large_n_is_fast_and_matches_incomplete_beta():
    import time
    start = time.perf_counter()
    p = st.mcnemar_exact(42000, 42500)
    assert time.perf_counter() - start < 1.0
    # P(X <= k) = I_{0.5}(n - k, k + 1) for X ~ Binomial(n, 1/2)
    assert p == pytest.approx(2 * st.betainc(84500 - 42000, 42000 + 1, 0.5), rel=1e-8)


def test_mcnemar_log_space_path_agrees_with_integer_path(monkeypatch):
    exact = [st.mcnemar_exact(b, c) for b, c in [(900, 1100), (700, 1300), (1000, 1001), (0, 1999)]]
    monkeypatch.setattr(st, "EXACT_INTEGER_MAX_N", 0)
    approx = [st.mcnemar_exact(b, c) for b, c in [(900, 1100), (700, 1300), (1000, 1001), (0, 1999)]]
    assert approx == pytest.approx(exact, rel=1e-9)


# ---------------------------------------------------------------- check intervals (bounded-null guard)
Z95 = 1.959963984540054


@pytest.mark.parametrize("n", [3, 10, 40, 183, 300])
def test_tango_with_no_disagreement_has_closed_form_width(n):
    # 불일치 0개: 구간은 +/- z^2 / (n + z^2) — 부트스트랩처럼 [0, 0] 으로 무너지지 않는다
    lo, hi = st.tango_ci(0, 0, n)
    half = Z95 ** 2 / (n + Z95 ** 2)
    assert lo == pytest.approx(-half, abs=1e-9) and hi == pytest.approx(half, abs=1e-9)


def test_tango_no_disagreement_needs_about_190_items_to_fit_a_2_point_margin():
    assert st.tango_ci(0, 0, 10)[1] == pytest.approx(0.2775, abs=1e-4)
    assert st.tango_ci(0, 0, 188)[1] > 0.02
    assert st.tango_ci(0, 0, 189)[1] < 0.02


@pytest.mark.parametrize("cand_only,base_only,n", [(7, 1, 21), (33, 14, 299), (62, 60, 2000), (3, 0, 12), (5, 5, 10)])
def test_tango_endpoints_solve_the_score_equation(cand_only, base_only, n):
    lo, hi = st.tango_ci(cand_only, base_only, n)
    estimate = (cand_only - base_only) / n
    assert lo < estimate < hi
    assert st._tango_score(cand_only, base_only, n, lo) == pytest.approx(Z95, abs=1e-6)
    assert st._tango_score(cand_only, base_only, n, hi) == pytest.approx(-Z95, abs=1e-6)
    # 후보/기준선을 바꾸면 구간이 0 을 중심으로 뒤집힌다
    flipped = st.tango_ci(base_only, cand_only, n)
    assert flipped[0] == pytest.approx(-hi, abs=1e-9) and flipped[1] == pytest.approx(-lo, abs=1e-9)


@pytest.mark.parametrize("cand_only,base_only,n,delta", [(7, 1, 21, 0.1), (7, 1, 21, 0.45), (2, 9, 40, -0.05),
                                                         (0, 0, 10, 0.2), (12, 40, 300, 0.01)])
def test_tango_restricted_mle_maximizes_the_constrained_likelihood(cand_only, base_only, n, delta):
    # 독립 확인: 폐형식 제약 MLE 가 수치 탐색으로 찾은 최댓값과 같은지 본다
    def loglik(p):
        cells = [(cand_only, p + delta), (base_only, p), (n - cand_only - base_only, 1.0 - 2.0 * p - delta)]
        return sum(k * math.log(q) for k, q in cells if k > 0)

    lo = max(0.0, -delta) + 1e-12
    hi = (1.0 - delta) / 2.0 - 1e-12
    for _ in range(300):  # 오목 함수의 황금분할 탐색
        m1, m2 = lo + (hi - lo) * 0.382, lo + (hi - lo) * 0.618
        if loglik(m1) < loglik(m2):
            lo = m1
        else:
            hi = m2
    assert st._tango_restricted_p(cand_only, base_only, n, delta) == pytest.approx((lo + hi) / 2.0, abs=1e-6)


def test_tango_extreme_counts_reach_the_bounds():
    assert st.tango_ci(10, 0, 10)[1] == 1.0
    assert st.tango_ci(0, 10, 10)[0] == -1.0
    assert st.tango_ci(0, 0, 0) == (-1.0, 1.0)


def test_t_interval():
    lo, hi = st.t_interval(0.1, 0.05, 9)
    half = st.t_quantile(0.975, 9) * 0.05
    assert (lo, hi) == pytest.approx((0.1 - half, 0.1 + half), abs=1e-12)
    assert st.t_interval(0.0, 0.0, 9) is None
    assert st.t_interval(0.0, 0.1, 0) is None
