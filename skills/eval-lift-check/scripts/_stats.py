"""Statistics for paired eval comparisons, standard library only.

Written from the textbook formulas (see references/statistics.md):
exact McNemar, Student t via the regularized incomplete beta function,
percentile bootstrap (item and cluster), CRV1 cluster-robust standard error,
Connor (1987) sample size, minimum detectable effect and Holm adjustment.
Degenerate inputs return explicit values plus warning codes, never exceptions.
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist
from typing import Optional, Sequence

_NORMAL = NormalDist()
# Up to this many discordant pairs the exact test uses big-integer arithmetic.
EXACT_INTEGER_MAX_N = 2000


def z_quantile(prob: float) -> float:
    """Standard normal quantile."""
    return _NORMAL.inv_cdf(prob)


# --------------------------------------------------------------------------
# exact McNemar
# --------------------------------------------------------------------------
def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p value.

    ``b`` and ``c`` are the two discordant counts. Under H0 the smaller count is
    Binomial(b + c, 1/2); the two-sided p is twice the lower tail, capped at 1.
    With no discordant pair the test cannot reject anything and p is 1.0.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    if n <= EXACT_INTEGER_MAX_N:
        tail = sum(math.comb(n, i) for i in range(k + 1))
        # Integer arithmetic until the final division keeps the value exact.
        return min(1.0, 2 * tail / 2 ** n)
    return min(1.0, 2 * _binom_lower_tail_half(n, k))


def _binom_lower_tail_half(n: int, k: int) -> float:
    """P(X <= k) for X ~ Binomial(n, 1/2) with k <= n / 2, summed in log space.

    The terms shrink geometrically away from k, so the sum stops as soon as a
    term is negligible; the cost stays near sqrt(n) steps for large n.
    """
    log_top = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) - n * math.log(2.0)
    total, ratio = 1.0, 1.0
    for i in range(k, 0, -1):
        ratio *= i / (n - i + 1)  # pmf(i - 1) / pmf(k), built one term at a time
        total += ratio
        if ratio < 1e-18 * total:
            break
    return math.exp(log_top) * total


# --------------------------------------------------------------------------
# Student t
# --------------------------------------------------------------------------
def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """Student t cumulative distribution function."""
    if df <= 0:
        raise ValueError("df must be positive")
    if math.isinf(t):
        return 1.0 if t > 0 else 0.0
    x = df / (df + t * t)
    tail = 0.5 * betainc(df / 2.0, 0.5, x)  # P(T > |t|)
    return 1.0 - tail if t > 0 else tail


def t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p value of a t statistic."""
    if math.isinf(t):
        return 0.0
    x = df / (df + t * t)
    return min(1.0, betainc(df / 2.0, 0.5, x))


def t_quantile(prob: float, df: float) -> float:
    """Student t quantile by bisection on t_cdf (accurate to about 1e-12)."""
    if not 0.0 < prob < 1.0:
        raise ValueError("prob must be in (0, 1)")
    if prob == 0.5:
        return 0.0
    lo, hi = -1.0, 1.0
    while t_cdf(lo, df) > prob:
        lo *= 2.0
    while t_cdf(hi, df) < prob:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < prob:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --------------------------------------------------------------------------
# means, paired t, cluster-robust SE
# --------------------------------------------------------------------------
def mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def sample_sd(values: Sequence[float]) -> float:
    """Sample standard deviation (n - 1); 0.0 for fewer than two values."""
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(math.fsum((v - m) ** 2 for v in values) / (n - 1))


def paired_se(diffs: Sequence[float]) -> float:
    """Standard error of the mean of per-item differences (item level)."""
    n = len(diffs)
    return sample_sd(diffs) / math.sqrt(n) if n else 0.0


def paired_t(diffs: Sequence[float]) -> dict:
    """Paired t test on per-item differences.

    Returns mean, se, t, df, p and a ``warnings`` list. Zero variance gives
    p = 1.0 when the mean is zero and p = 0.0 otherwise, with a warning.
    """
    n = len(diffs)
    m = mean(diffs)
    se = paired_se(diffs)
    warnings: list[str] = []
    df = n - 1
    if se == 0.0:
        warnings.append("zero-variance")
        p = 1.0 if m == 0.0 else 0.0
        t = 0.0 if m == 0.0 else math.copysign(math.inf, m)
        return {"mean": m, "se": se, "t": t, "df": df, "p": p, "warnings": warnings}
    t = m / se
    return {"mean": m, "se": se, "t": t, "df": df, "p": t_two_sided_p(t, df), "warnings": warnings}


def group_by_cluster(diffs: Sequence[float], clusters: Sequence[str]) -> dict[str, list[float]]:
    groups: dict[str, list[float]] = {}
    for value, key in zip(diffs, clusters):
        groups.setdefault(key, []).append(value)
    return groups


def cluster_se(diffs: Sequence[float], clusters: Sequence[str]) -> dict:
    """CRV1 cluster-robust standard error of the mean difference.

    var = G/(G-1) * sum_g (sum_{i in g}(d_i - mean))^2 / n^2 with G clusters.
    One cluster: se is None and the warning ``one-cluster`` is returned.
    """
    n = len(diffs)
    m = mean(diffs)
    groups = group_by_cluster(diffs, clusters)
    g = len(groups)
    warnings: list[str] = []
    if g < 2:
        return {"se": None, "clusters": g, "df": 0, "warnings": ["one-cluster"]}
    if g < 10:
        warnings.append("few-clusters")
    total = math.fsum(math.fsum(v - m for v in vals) ** 2 for vals in groups.values())
    var = total / n ** 2 * (g / (g - 1))
    return {"se": math.sqrt(var), "clusters": g, "df": g - 1, "warnings": warnings}


def cluster_t(diffs: Sequence[float], clusters: Sequence[str]) -> dict:
    """t test of the mean difference using the cluster-robust SE and G-1 df."""
    res = cluster_se(diffs, clusters)
    m = mean(diffs)
    warnings = list(res["warnings"])
    se = res["se"]
    if se is None:
        return {"mean": m, "se": None, "t": None, "df": 0, "p": None, "clusters": res["clusters"], "warnings": warnings}
    if se == 0.0:
        warnings.append("zero-variance")
        p = 1.0 if m == 0.0 else 0.0
        t = 0.0 if m == 0.0 else math.copysign(math.inf, m)
    else:
        t = m / se
        p = t_two_sided_p(t, res["df"])
    return {"mean": m, "se": se, "t": t, "df": res["df"], "p": p, "clusters": res["clusters"], "warnings": warnings}


# --------------------------------------------------------------------------
# bootstrap
# --------------------------------------------------------------------------
def bootstrap_ci(
    diffs: Sequence[float],
    clusters: Optional[Sequence[str]] = None,
    reps: int = 10000,
    seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean difference.

    Without ``clusters`` items are resampled; with ``clusters`` whole clusters
    are resampled and the statistic is total / count so unequal sizes stay
    consistent. The same seed always gives the same interval.
    """
    rng = random.Random(seed)
    stats: list[float] = []
    if clusters is None:
        data = list(diffs)
        n = len(data)
        for _ in range(reps):
            stats.append(math.fsum(rng.choices(data, k=n)) / n)
    else:
        groups = group_by_cluster(diffs, clusters)
        keys = sorted(groups)
        sums = [math.fsum(groups[k]) for k in keys]
        counts = [len(groups[k]) for k in keys]
        g = len(keys)
        for _ in range(reps):
            picks = rng.choices(range(g), k=g)
            total = math.fsum(sums[j] for j in picks)
            count = sum(counts[j] for j in picks)
            stats.append(total / count)
    stats.sort()
    lo_idx = int(((1.0 - level) / 2.0) * reps)
    hi_idx = int(((1.0 + level) / 2.0) * reps) - 1
    return stats[lo_idx], stats[max(hi_idx, lo_idx)]


# --------------------------------------------------------------------------
# analytic check intervals (used before declaring bounded-null)
# --------------------------------------------------------------------------
def _tango_restricted_p(cand_only: int, base_only: int, n: int, delta: float) -> float:
    """Restricted MLE of P(baseline-only) when the true difference is ``delta``.

    Root of 2n p^2 + B p + C = 0 with B = -(x + y) + (2n - x + y) delta and
    C = -y delta (1 - delta), where x = candidate-only and y = baseline-only counts.
    """
    a = 2.0 * n
    b = -(cand_only + base_only) + (2.0 * n - cand_only + base_only) * delta
    c = -base_only * delta * (1.0 - delta)
    disc = max(0.0, b * b - 4.0 * a * c)
    return (math.sqrt(disc) - b) / (2.0 * a)


def _tango_score(cand_only: int, base_only: int, n: int, delta: float) -> float:
    """Tango (1998) score statistic for H0: P(candidate-only) - P(baseline-only) = delta."""
    p_base_only = _tango_restricted_p(cand_only, base_only, n, delta)
    numerator = cand_only - base_only - n * delta
    variance = n * (2.0 * p_base_only + delta * (1.0 - delta))
    if variance <= 0.0:
        return 0.0 if numerator == 0 else math.copysign(math.inf, numerator)
    return numerator / math.sqrt(variance)


def tango_ci(cand_only: int, base_only: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Tango (1998) asymptotic score interval for a paired difference of proportions.

    Unlike the percentile bootstrap it does not collapse when few items disagree:
    with no disagreement in n items it is +/- z^2 / (n + z^2) (0.2775 for n = 10),
    so a small sample can never look like a tight null. Solved by bisection.
    """
    if n <= 0:
        return -1.0, 1.0
    z = z_quantile(0.5 + level / 2.0)
    estimate = (cand_only - base_only) / n
    edge = 1.0 - 1e-12

    # 점수 통계량은 delta 가 커질수록 줄어든다 → 하한은 T = +z, 상한은 T = -z 인 점
    def solve(target: float, lo: float, hi: float) -> float:
        for _ in range(200):
            mid = (lo + hi) / 2.0
            if _tango_score(cand_only, base_only, n, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    lower = -1.0 if _tango_score(cand_only, base_only, n, -edge) <= z else solve(z, -edge, estimate)
    upper = 1.0 if _tango_score(cand_only, base_only, n, edge) >= -z else solve(-z, estimate, edge)
    return lower, upper


def t_interval(mean_diff: float, se: float, df: float, level: float = 0.95) -> Optional[tuple[float, float]]:
    """mean +/- t_(df) * se; None when se is 0 (every item has the same difference)."""
    if se <= 0.0 or df < 1:
        return None
    half = t_quantile(0.5 + level / 2.0, df) * se
    return mean_diff - half, mean_diff + half


# --------------------------------------------------------------------------
# sample size and minimum detectable effect
# --------------------------------------------------------------------------
def mcnemar_required_n(p10: float, p01: float, alpha: float = 0.05, power: float = 0.8) -> Optional[int]:
    """Connor (1987) normal-approximation sample size for a McNemar test.

    ``p10`` and ``p01`` are the expected fractions of items that only the
    baseline / only the candidate gets right. n = (z_a*sqrt(psi) + z_b*sqrt(psi - delta^2))^2 / delta^2
    with psi = p10 + p01 and delta = |p01 - p10|. Returns None when delta is 0.
    """
    psi = p10 + p01
    delta = abs(p01 - p10)
    if delta == 0.0 or psi <= 0.0:
        return None
    za = z_quantile(1.0 - alpha / 2.0)
    zb = z_quantile(power)
    n = (za * math.sqrt(psi) + zb * math.sqrt(max(psi - delta ** 2, 0.0))) ** 2 / delta ** 2
    return math.ceil(n - 1e-9)


def required_n_for_delta(rate: float, delta: float, alpha: float = 0.05, power: float = 0.8) -> Optional[int]:
    """Items needed to detect an accuracy difference ``delta`` when a fraction
    ``rate`` of items disagree between the runs (Connor 1987)."""
    if delta <= 0.0 or delta > rate:
        return None
    return mcnemar_required_n((rate - delta) / 2.0, (rate + delta) / 2.0, alpha, power)


def mde_binary(n: int, rate: float, alpha: float = 0.05, power: float = 0.8) -> Optional[float]:
    """Smallest accuracy difference detectable with ``n`` items at disagreement
    ``rate``: the delta whose Connor sample size equals ``n`` (bisection)."""
    if n < 2 or rate <= 0.0:
        return None
    lo, hi = 1e-9, rate
    best = required_n_for_delta(rate, hi, alpha, power)
    if best is None or best > n:
        return None  # even a difference equal to the whole disagreement rate is not detectable
    for _ in range(100):
        mid = (lo + hi) / 2.0
        need = required_n_for_delta(rate, mid, alpha, power)
        if need is not None and need <= n:
            hi = mid
        else:
            lo = mid
    return hi


def required_n_continuous(sd_diff: float, delta: float, alpha: float = 0.05, power: float = 0.8,
                          design_effect: float = 1.0) -> Optional[int]:
    """Items needed for a paired comparison of continuous scores (normal approx.):
    n = ((z_a + z_b) * sd / delta)^2 * design_effect."""
    if sd_diff <= 0.0 or delta <= 0.0:
        return None
    za = z_quantile(1.0 - alpha / 2.0)
    zb = z_quantile(power)
    return math.ceil(((za + zb) * sd_diff / delta) ** 2 * design_effect - 1e-9)


def mde_continuous(n: int, sd_diff: float, alpha: float = 0.05, power: float = 0.8,
                   design_effect: float = 1.0) -> Optional[float]:
    """Smallest mean difference detectable with ``n`` items (normal approx.)."""
    if n < 2 or sd_diff <= 0.0:
        return None
    za = z_quantile(1.0 - alpha / 2.0)
    zb = z_quantile(power)
    return (za + zb) * sd_diff * math.sqrt(design_effect / n)


# --------------------------------------------------------------------------
# Holm
# --------------------------------------------------------------------------
def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p values, in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[idx]))
        adjusted[idx] = running
    return adjusted
