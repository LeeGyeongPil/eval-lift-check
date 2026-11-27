"""Join runs by item id and report what does not pair.

Order of work per run: duplicates (policy), epochs (policy). Then the key sets
are intersected, rows whose lm-eval ``doc_hash`` disagrees are excluded, and the
leftovers are reported before any statistic is computed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from _loaders import Row, RunData, ToolError

DUP_POLICIES = ("error", "first", "mean")
EPOCH_POLICIES = ("mean", "cluster")


@dataclass
class Paired:
    ids: list[str]
    scores: list[list[float]]          # one list per run, aligned with ids
    clusters: Optional[list[str]]
    binary: bool
    diagnostics: dict
    tasks: Optional[list[str]] = None  # lm-eval task per id when there are 2+ tasks (secondary breakdown)


def _group(rows: list[Row]) -> dict[tuple[str, Optional[int]], list[Row]]:
    groups: dict[tuple[str, Optional[int]], list[Row]] = {}
    for row in rows:
        groups.setdefault((row.key, row.epoch), []).append(row)
    return groups


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _resolve_run(run: RunData, dup_policy: str, epoch_policy: str):
    """Return (items, dup_counts, epoch_range) with one entry per item key.

    items maps key -> (score, cluster, doc_hash)."""
    groups = _group(run.rows)
    dup_counts = {key: len(rows) for (key, _epoch), rows in groups.items() if len(rows) > 1}
    cells: dict[tuple[str, Optional[int]], Row] = {}
    for ident, rows in groups.items():
        if len(rows) == 1 or dup_policy == "first":
            cells[ident] = rows[0]
        else:  # mean (error is handled by the caller before this point)
            first = rows[0]
            cells[ident] = Row(first.key, _mean([r.score for r in rows]), first.cluster, first.epoch, first.doc_hash,
                               first.task)
    per_key: dict[str, list[Row]] = {}
    for (key, _epoch), row in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1)):
        per_key.setdefault(key, []).append(row)
    epoch_counts = [len(v) for v in per_key.values()]
    # 값: (점수, 군집, doc_hash, 태스크, 원래 문항 ID) — 에포크 행도 원래 문항 ID 를 기억한다
    items: dict[str, tuple[float, Optional[str], Optional[str], Optional[str], str]] = {}
    for key, rows in per_key.items():
        has_epochs = any(r.epoch is not None for r in rows)
        if has_epochs and epoch_policy == "cluster":
            for r in rows:
                items[f"{key}#e{r.epoch}"] = (r.score, r.cluster if r.cluster is not None else key, r.doc_hash,
                                               r.task, key)
        else:
            first = rows[0]
            score = first.score if len(rows) == 1 else _mean([r.score for r in rows])
            items[key] = (score, first.cluster, first.doc_hash, first.task, key)
    return items, dup_counts, (min(epoch_counts), max(epoch_counts))


def join_runs(runs: list[RunData], dup_policy: str = "error", epoch_policy: str = "mean") -> Paired:
    """Pair all runs by item id. ``runs[0]`` is the baseline."""
    if dup_policy not in DUP_POLICIES or epoch_policy not in EPOCH_POLICIES:
        raise ValueError("unknown policy")
    # 1. duplicates: with the default policy every duplicate is reported at once.
    per_run_dups = [{k: n for k, n in ((key, len(rows)) for (key, _e), rows in _group(r.rows).items()) if n > 1}
                    for r in runs]
    if dup_policy == "error" and any(per_run_dups):
        paths = ", ".join(r.path for r, d in zip(runs, per_run_dups) if d)
        merged: dict[str, int] = {}
        for d in per_run_dups:
            for key, count in d.items():
                merged[key] = max(merged.get(key, 0), count)
        listing = ", ".join(f"{key} (x{merged[key]})" for key in sorted(merged))
        raise ToolError("duplicate-id", 3, path=paths, count=len(merged), ids=listing)
    resolved = [_resolve_run(r, dup_policy, epoch_policy) for r in runs]
    items_per_run = [r[0] for r in resolved]
    base_keys = set(items_per_run[0])
    common = set(base_keys)
    for items in items_per_run[1:]:
        common &= set(items)
    # 2. hash mismatches among common keys (lm-eval doc_hash)
    mismatched = []
    for key in sorted(common):
        hashes = {items[key][2] for items in items_per_run if items[key][2] is not None}
        if len(hashes) > 1:
            mismatched.append(key)
    kept = sorted(common - set(mismatched))
    n_base = len(base_keys)
    n_cand = len(items_per_run[1]) if len(items_per_run) > 1 else 0
    if len(kept) < 2:
        raise ToolError("too-few-pairs", 3, n=len(kept), n_base=n_base, n_cand=n_cand)
    only_base = sorted(base_keys - common)
    only_cand = sorted(set().union(*[set(i) for i in items_per_run[1:]]) - common)
    scores = [[items[key][0] for key in kept] for items in items_per_run]
    base_clusters = [items_per_run[0][key][1] for key in kept]
    clusters = base_clusters if all(c is not None for c in base_clusters) else None
    # lm-eval 태스크가 2개 이상이면 태스크별 보조 결과를 낸다(주 판정은 전체 문항 합동)
    base_tasks = [items_per_run[0][key][3] for key in kept]
    tasks = base_tasks if all(t is not None for t in base_tasks) and len(set(base_tasks)) > 1 else None
    binary = all(v in (0.0, 1.0) for column in scores for v in column)
    dup_merged: dict[str, int] = {}
    for d in per_run_dups:
        for key, count in d.items():
            dup_merged[key] = max(dup_merged.get(key, 0), count)
    diagnostics = {
        "n_paired": len(kept),
        # 서로 다른 문항 수: --epochs cluster 이면 n_paired 는 문항×에포크 행 수다
        "n_items": len({items_per_run[0][key][4] for key in kept}),
        "only_in_baseline": only_base,
        "only_in_candidate": only_cand,
        "duplicates": {k: dup_merged[k] for k in sorted(dup_merged)},
        "dup_policy": dup_policy,
        "epochs": {
            "policy": epoch_policy,
            "per_input": [{"path": r.path, "min": lo, "max": hi}
                          for r, (_i, _d, (lo, hi)) in zip(runs, resolved)],
        },
        "hash_mismatch": mismatched,
    }
    return Paired(kept, scores, clusters, binary, diagnostics, tasks)
