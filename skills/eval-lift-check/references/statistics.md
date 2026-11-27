# Statistics used by eval-lift-check

All formulas are implemented in `scripts/_stats.py` from textbook definitions (standard library only). Sources were checked on 2026-11-27.

## Contents

1. Paired data and the disagreement table
2. Exact McNemar test
3. Paired t test
4. Intervals: bootstrap
5. Clustered items: CRV1 standard error
6. Required sample size and minimum detectable difference
7. Holm correction
8. Verdict rules
9. Why not compare two averages

## 1. Paired data and the disagreement table

Both runs answer the same items. For 0/1 scores, `b` counts items only the baseline gets right, `c` counts items only the candidate gets right. Items both get right or both get wrong say nothing about which run is better. The difference of accuracies equals `(c - b) / n`.

## 2. Exact McNemar test

Under no difference, each disagreement is equally likely to favour either run, so `min(b, c)` is Binomial(`b + c`, 1/2). The two-sided p is twice the lower tail, capped at 1. With `b + c = 0` the test cannot reject and p is 1. No normal approximation and no continuity correction are used.

Reference: McNemar (1947); the exact form is the sign test on the disagreements. Practical advice for eval comparisons: Miller (2024), "Adding Error Bars to Evals", https://arxiv.org/abs/2411.00640 (checked 2026-11-27).

## 3. Paired t test

For continuous scores the per-item differences `d_i` are tested with `t = mean(d) / (sd(d) / sqrt(n))`, df `n - 1`. The Student t CDF is computed through the regularized incomplete beta function (continued fraction, modified Lentz). Zero variance gives p = 1 when the mean is 0 and p = 0 otherwise, with a `zero-variance` warning.

## 4. Intervals: bootstrap

The 95% interval of the mean difference is a percentile bootstrap: `reps` resamples (default 10000) with a seeded generator. Without clusters items are resampled; with clusters whole clusters are resampled and the statistic is total over count. The percentile indexes are `int(0.025 * reps)` and `int(0.975 * reps) - 1` of the sorted statistics. The same seed gives the same interval. For 0/1 scores the interval lives on a grid of size `1/n`, so different seeds often give the same endpoints.

The percentile bootstrap collapses when few items disagree: with `b = c = 0` every resample has difference 0 and the interval is `[0, 0]`, even for 10 items. So before `bounded-null` the script also computes an analytic check interval (`ci95_check` in the JSON):

- 0/1 scores: the Tango (1998) asymptotic score interval for the difference of paired proportions (Statistics in Medicine 17(8):891-908, https://doi.org/10.1002/(SICI)1097-0258(19980430)17:8%3C891::AID-SIM780%3E3.0.CO;2-B, checked 2026-11-27; recommended in Fagerland, Lydersen and Laake (2014), Statistics in Medicine 33:2850-2875, https://doi.org/10.1002/sim.6148, checked 2026-11-27). It inverts the score test with the restricted maximum-likelihood estimate, solved by bisection. With no disagreement in `n` items it is `+/- z^2 / (n + z^2)`, so 0/1 scores with no disagreement need at least 189 items before a 2-point margin can be bounded. With clusters the interval is widened around the estimate by `sqrt(design effect)`.
- Continuous scores: the t interval `mean(d) +/- t_{0.975, df} * se` with the paired SE (df `n - 1`) or the cluster-robust SE (df `G - 1`). When every item has the same difference the SE is 0 and there is no interval, so `bounded-null` is not declared.

## 5. Clustered items: CRV1 standard error

When items share a source (questions on one passage, epochs of one item) they are not independent. The cluster-robust standard error of the mean difference is

`var = G / (G - 1) * sum_g (sum_{i in g} (d_i - mean))^2 / n^2`

with `G` clusters, and the t test uses `G - 1` degrees of freedom. Below 10 clusters the estimate is unstable and the script warns; one cluster makes it undefined (the script falls back to item-level errors and says so). With `--cluster-key` or `--epochs cluster` the cluster-robust t test is the primary p; the unclustered McNemar p is kept as `p_mcnemar_unclustered`. Reference: Cameron and Miller (2015), "A Practitioner's Guide to Cluster-Robust Inference", Journal of Human Resources.

## 6. Required sample size and minimum detectable difference

0/1 scores: Connor (1987), "Sample size for testing differences in proportions for the paired-sample design", Biometrics 43(1). With `psi = p10 + p01` (fraction of disagreeing items) and `delta = |p01 - p10|`:

`n = (z_{alpha/2} * sqrt(psi) + z_{beta} * sqrt(psi - delta^2))^2 / delta^2`

`compare.py` fixes `psi` at the observed disagreement rate and reports `n` for a difference equal to the margin (default 0.02) plus `n_observed_effect` for the observed difference. Clustered data multiply by the design effect `(se_cluster / se_paired)^2`. `plan_n.py --discordant-rate R --delta D` solves the same formula; `--n N` finds the smallest `D` whose required N is at most N (bisection).

Continuous scores: `n = ((z_{alpha/2} + z_beta) * sd_diff / delta)^2 * design_effect` (normal approximation).

Different formulas give very different numbers for the same situation. In one probe (2026-11-27) tools returned 304, 432 and 4120 for what looked like the same question, because they assume different things (observed effect versus fixed margin, which disagreement rate, one-sided versus two-sided, independent versus paired). That is why every report states the method and the assumptions next to N.

## 7. Holm correction

For `m` candidates compared with one baseline, p values are sorted ascending and the k-th smallest is multiplied by `m - k + 1`, made monotone and capped at 1 (Holm 1979, "A simple sequentially rejective multiple test procedure"). Example: `[0.01, 0.04, 0.03, 0.2]` becomes `[0.04, 0.09, 0.09, 0.2]`. The confidence intervals are not adjusted.

## 8. Verdict rules

| Verdict | Condition |
|---|---|
| improved | adjusted p < alpha and difference > 0 |
| regressed | adjusted p < alpha and difference < 0 |
| bounded-null | not significant, and both the 95% bootstrap CI and the 95% check interval (section 4) lie strictly inside (-margin, +margin) |
| underpowered | anything else |

Defaults: alpha 0.05, power 0.8, margin 0.02 for 0/1 scores. Continuous scores have no default margin, so `bounded-null` is not evaluated without `--margin`. This is not an equivalence test (TOST); it is a CI-inside-margin rule. The JSON field `verdict_reason` says which rule decided: `underpowered` (bootstrap CI wider than the margin), `underpowered-check` (bootstrap CI inside, check interval not), `underpowered-zero-variance` (continuous scores with identical differences) or `underpowered-nomargin`.

## 9. Why not compare two averages

Comparing 69.2% with 75.6% on 299 items with an unpaired two-proportion z test gives p about 0.082, "not significant". The same data tested as pairs (14 items only the baseline gets right, 33 only the candidate) gives an exact McNemar p of 0.0079. Ignoring the pairing throws away the information that the same items were asked, which makes the test too weak. The lm-evaluation-harness issue https://github.com/EleutherAI/lm-evaluation-harness/issues/3831 (checked 2026-11-27) reports the same problem in its comparison script.
