# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "statsmodels"]
# ///
"""Development only: regenerate tests/oracle/expected.json with scipy and statsmodels.

    uv run tests/oracle/crosscheck.py

The skill itself never imports these packages; the tests read expected.json.
"""
import json
import math
from pathlib import Path

import numpy as np
import scipy
import statsmodels
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[2]


def load(path, dedupe=True):
    out = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        out.setdefault(row["id"], row)
    return out


def paired_vectors(folder):
    a, b = load(folder / "run_a.jsonl"), load(folder / "run_b.jsonl")
    ids = sorted(set(a) & set(b))
    return ids, a, b


ids, a, b = paired_vectors(ROOT / "tests" / "fixtures" / "reading")
sa = np.array([a[i]["score"] for i in ids])
sb = np.array([b[i]["score"] for i in ids])
n11, n10 = int(((sa == 1) & (sb == 1)).sum()), int(((sa == 1) & (sb == 0)).sum())
n01, n00 = int(((sa == 0) & (sb == 1)).sum()), int(((sa == 0) & (sb == 0)).sum())
mc = mcnemar([[n11, n10], [n01, n00]], exact=True)
d = sb - sa
groups = np.array([{g: k for k, g in enumerate(sorted({a[i]["passage"] for i in ids}))}[a[i]["passage"]] for i in ids])
cluster_fit = sm.OLS(d, np.ones(len(d))).fit(cov_type="cluster", cov_kwds={"groups": groups})

# Connor (1987) with scipy's normal quantiles, written independently of the skill code
za, zb = stats.norm.ppf(0.975), stats.norm.ppf(0.8)
psi, delta = (n10 + n01) / len(ids), abs(n01 - n10) / len(ids)
connor_n = math.ceil((za * math.sqrt(psi) + zb * math.sqrt(psi - delta ** 2)) ** 2 / delta ** 2)
rate, target = 0.16, 0.02
connor_rate = math.ceil((za * math.sqrt(rate) + zb * math.sqrt(rate - target ** 2)) ** 2 / target ** 2)

grid = [(0.0, 1), (0.5, 1), (2.0, 1), (-1.3, 2), (2.5, 3), (1.1, 5), (-2.2, 7), (2.228, 10), (3.1, 29), (0.4, 59), (-4.0, 4), (1.96, 1000)]
rubric = paired_vectors(ROOT / "tests" / "fixtures" / "rubric")
ra = np.array([rubric[1][i]["score"] for i in rubric[0]])
rb = np.array([rubric[2][i]["score"] for i in rubric[0]])
rt = stats.ttest_rel(rb, ra)
out = {
    "versions": {"scipy": scipy.__version__, "statsmodels": statsmodels.__version__, "numpy": np.__version__},
    "reading": {"n_paired": len(ids), "n10": n10, "n01": n01,
                "mcnemar_exact_p_statsmodels": float(mc.pvalue),
                "binomtest_p_scipy": float(stats.binomtest(n01, n10 + n01, 0.5).pvalue),
                "cluster_se": float(cluster_fit.bse[0]), "clusters": int(len(set(groups))),
                "cluster_t_p": float(2 * stats.t.sf(abs(d.mean() / cluster_fit.bse[0]), len(set(groups)) - 1)),
                "connor_n_observed": connor_n},
    "connor_rate_0.16_delta_0.02": connor_rate,
    "t_cdf": [{"t": t, "df": df, "cdf": float(stats.t.cdf(t, df))} for t, df in grid],
    "t_ppf": [{"p": p, "df": df, "q": float(stats.t.ppf(p, df))} for p, df in ((0.975, 1), (0.975, 10), (0.975, 59), (0.9, 4))],
    "holm": {"in": [0.01, 0.04, 0.03, 0.2], "out": [float(x) for x in multipletests([0.01, 0.04, 0.03, 0.2], method="holm")[1]]},
    "rubric": {"n": len(ra), "paired_t_p": float(rt.pvalue), "paired_t_stat": float(rt.statistic),
               "mean_diff": float((rb - ra).mean())},
    "continuous_required_n": {"sd": 0.2, "delta": 0.03, "n": math.ceil(((za + zb) * 0.2 / 0.03) ** 2)},
}
dest = Path(__file__).with_name("expected.json")
dest.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
