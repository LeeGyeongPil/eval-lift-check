#!/usr/bin/env python3
"""Pair two or more eval runs item by item and decide whether B really beats A.

Usage: python3 compare.py BASELINE CANDIDATE [CANDIDATE ...] [options]
Run with --help (or --lang ko --help) for all options. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _i18n  # noqa: E402
from _i18n import tr  # noqa: E402
from _join import DUP_POLICIES, EPOCH_POLICIES, join_runs  # noqa: E402
from _loaders import FORMATS, ToolError, load_run  # noqa: E402
from _verdict import Settings, analyze, build_report  # noqa: E402

MAX_LISTED_IDS = 10


def build_parser(lang: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compare.py",
        description=tr(lang, "help.compare.desc"),
        epilog=tr(lang, "help.compare.epilog"),
    )
    parser.add_argument("runs", nargs="*", metavar="RUN", help=tr(lang, "help.runs"))
    parser.add_argument("--format", default="auto", metavar="{auto,%s}" % ",".join(FORMATS), help=tr(lang, "help.format"))
    parser.add_argument("--id-key", default=None, help=tr(lang, "help.id_key"))
    parser.add_argument("--score-key", default=None, help=tr(lang, "help.score_key"))
    parser.add_argument("--metric", default=None, help=tr(lang, "help.metric"))
    parser.add_argument("--cluster-key", default=None, help=tr(lang, "help.cluster_key"))
    parser.add_argument("--dup", default="error", choices=DUP_POLICIES, help=tr(lang, "help.dup"))
    parser.add_argument("--epochs", default="mean", choices=EPOCH_POLICIES, help=tr(lang, "help.epochs"))
    parser.add_argument("--alpha", type=float, default=0.05, help=tr(lang, "help.alpha"))
    parser.add_argument("--power", type=float, default=0.8, help=tr(lang, "help.power"))
    parser.add_argument("--margin", type=float, default=None, help=tr(lang, "help.margin"))
    parser.add_argument("--seed", type=int, default=0, help=tr(lang, "help.seed"))
    parser.add_argument("--reps", type=int, default=10000, help=tr(lang, "help.reps"))
    parser.add_argument("--prompt-idx", type=int, default=None, help=tr(lang, "help.prompt_idx"))
    parser.add_argument("--json", metavar="PATH", default=None, help=tr(lang, "help.json"))
    parser.add_argument("--lang", choices=_i18n.LANGS, default=None, help=tr(lang, "help.lang"))
    return _i18n.localize_parser(parser, lang)


def _bad(key: str, **fields: object) -> ToolError:
    return ToolError("bad-argument", 2, key, **fields)


def validate(args: argparse.Namespace) -> None:
    if len(args.runs) < 2:
        raise _bad("bad.runs")
    if not (0.0 < args.alpha < 1.0 and 0.0 < args.power < 1.0):
        raise _bad("bad.alpha")
    if args.margin is not None and args.margin <= 0.0:
        raise _bad("bad.margin")
    if args.reps < 200:
        raise _bad("bad.reps")
    if args.format != "auto" and args.format not in FORMATS:
        raise ToolError("unknown-format", 2, path=args.format)


def _fmt(value: Optional[float], digits: int = 4, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def _fmt_p(p: Optional[float]) -> str:
    if p is None:
        return "n/a"
    return "<0.0001" if p < 0.0001 else f"{p:.4f}"


def _code_text(lang: str, record: dict) -> str:
    """Render a ``{"code": key, **fields}`` record from the report in ``lang``."""
    fields = dict(record)
    return tr(lang, fields.pop("code"), **fields)


def _ids(ids: Sequence[str]) -> str:
    shown = ", ".join(ids[:MAX_LISTED_IDS])
    return shown + (f", ... (+{len(ids) - MAX_LISTED_IDS})" if len(ids) > MAX_LISTED_IDS else "")


def render_summary(report: dict, lang: str, saved_to: Optional[str] = None) -> str:
    """Human-readable summary in ``lang``; every number comes from the report."""
    out: list[str] = [tr(lang, "sum.title"), "", tr(lang, "sum.inputs")]
    for number, item in enumerate(report["inputs"]):
        role = tr(lang, "role.baseline" if number == 0 else "role.candidate")
        out.append(tr(lang, "sum.input_line", role=role, path=item["path"], fmt=item["format_detected"],
                      rows=item["rows"]))
    join = report["join"]
    out += ["", tr(lang, "sum.join")]
    if join.get("n_items", join["n_paired"]) != join["n_paired"]:
        # --epochs cluster: 분석 단위는 문항×에포크 행이지만, 문항 수와 행 수를 구분해 보여 준다
        out.append(tr(lang, "sum.paired_rows", items=join["n_items"], n=join["n_paired"]))
    else:
        out.append(tr(lang, "sum.paired", n=join["n_paired"]))
    issues = False
    if join["only_in_baseline"]:
        issues = True
        out.append(tr(lang, "sum.only_base", n=len(join["only_in_baseline"]), ids=_ids(join["only_in_baseline"])))
    if join["only_in_candidate"]:
        issues = True
        out.append(tr(lang, "sum.only_cand", n=len(join["only_in_candidate"]), ids=_ids(join["only_in_candidate"])))
    if join["duplicates"]:
        issues = True
        listing = ", ".join(f"{k} (x{v})" for k, v in list(join["duplicates"].items())[:MAX_LISTED_IDS])
        out.append(tr(lang, "sum.dups", n=len(join["duplicates"]), ids=listing, policy=join["dup_policy"]))
    if join["hash_mismatch"]:
        issues = True
        out.append(tr(lang, "sum.hash", n=len(join["hash_mismatch"]), ids=_ids(join["hash_mismatch"])))
    epoch_ranges = {(e["min"], e["max"]) for e in join["epochs"]["per_input"]}
    if any(hi > 1 for _lo, hi in epoch_ranges):
        issues = True
        shown: list[str] = []
        for e in join["epochs"]["per_input"]:
            text = f"{e['min']}-{e['max']}" if e["min"] != e["max"] else str(e["max"])
            if text not in shown:
                shown.append(text)
        value = "; ".join(shown)
        out.append(tr(lang, "sum.epochs", value=value, policy=join["epochs"]["policy"]))
    if not issues:
        out.append(tr(lang, "sum.no_issues"))
    for warning in report["warnings"]:
        if warning["code"] in ("lm-eval-latest", "prompt-idx"):
            fields = {k: v for k, v in warning.items() if k != "code"}
            out.append(tr(lang, "sum.warn", text=tr(lang, f"warn.{warning['code']}", **fields)))
    settings = report["settings"]
    n_cmp = len(report["comparisons"])
    for comp in report["comparisons"]:
        out += ["", tr(lang, "sum.cmp", name=comp["candidate"])]
        out.append(tr(lang, "sum.means", a=_fmt(comp["mean_baseline"]), b=_fmt(comp["mean_candidate"]),
                      d=_fmt(comp["diff"], signed=True)))
        out.append(tr(lang, "sum.ci", lo=_fmt(comp["ci95"][0], signed=True), hi=_fmt(comp["ci95"][1], signed=True),
                      method=_code_text(lang, comp["ci_method_code"])))
        out.append(tr(lang, "sum.p", p=_fmt_p(comp["p"]), method=_code_text(lang, comp["p_method_code"])))
        if n_cmp > 1:
            out.append(tr(lang, "sum.p_holm", p=_fmt_p(comp["p_holm"]), m=n_cmp))
        if comp["discordant"]:
            out.append(tr(lang, "sum.discordant", a=comp["discordant"]["baseline_only"],
                          b=comp["discordant"]["candidate_only"]))
        se = comp["se"]
        if se["cluster"] is not None:
            out.append(tr(lang, "sum.se", paired=_fmt(se["paired"]), cluster=_fmt(se["cluster"]), g=se["clusters"]))
        else:
            out.append(tr(lang, "sum.se_nocluster", paired=_fmt(se["paired"])))
        req = comp["required_n"]
        if req["n"] is not None:
            target = (tr(lang, "target.margin", margin=settings["margin"])
                      if settings["margin"] else tr(lang, "target.observed"))
            out.append(tr(lang, "sum.reqn", target=target, power=settings["power"], n=req["n"], method=_code_text(lang, req["method_code"]),
                          have=join["n_paired"], ratio=_fmt(req["ratio"], 2)))
        else:
            reason = tr(lang, "reason.rate_le_margin" if comp["discordant"] else "reason.zero_variance")
            out.append(tr(lang, "sum.reqn_none", reason=reason))
        if comp["mde"] is not None:
            out.append(tr(lang, "sum.mde", mde=_fmt(comp["mde"])))
        for warning in comp["warnings"]:
            fields = {k: v for k, v in warning.items() if k != "code"}
            out.append(tr(lang, "sum.warn", text=tr(lang, f"warn.{warning['code']}", **fields)))
        out.append(tr(lang, "sum.verdict", verdict=tr(lang, f"verdict.{comp['verdict']}")))
        why_fields = {"p": _fmt_p(comp["p_holm"]), "alpha": settings["alpha"], "margin": settings["margin"]}
        if comp["ci95_check"] is not None:
            # 부트스트랩만 좁고 분석적 구간이 넓을 때 이유 문장에 그 구간을 그대로 보여 준다
            why_fields.update(check_lo=_fmt(comp["ci95_check"][0], signed=True),
                              check_hi=_fmt(comp["ci95_check"][1], signed=True),
                              check_method=_code_text(lang, comp["ci_check_method_code"]))
        out.append(tr(lang, "sum.why", text=tr(lang, f"why.{comp['verdict_reason']}", **why_fields)))
        # 태스크별 결과는 보조 정보: 판정은 위의 합동 결과 하나뿐이다
        if comp.get("per_task"):
            out.append(tr(lang, "sum.per_task", m=len(comp["per_task"])))
            for entry in comp["per_task"]:
                out.append(tr(lang, "sum.per_task_line", task=entry["task"], n=entry["n_paired"],
                              d=_fmt(entry["diff"], signed=True), p=_fmt_p(entry["p"]),
                              ph=_fmt_p(entry["p_holm_tasks"])))
    out += ["", tr(lang, "sum.seed", reps=settings["reps"], seed=settings["seed"])]
    if saved_to:
        out.append(tr(lang, "sum.saved", path=saved_to))
    return "\n".join(out) + "\n"


def run(argv: Optional[Sequence[str]] = None, env: Optional[dict] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ) if env is None else env
    lang = _i18n.peek_lang(argv, env)
    parser = build_parser(lang)
    args = parser.parse_args(argv)
    lang = _i18n.detect_lang(args.lang, env)
    try:
        validate(args)
        loaded = [load_run(p, args.format, args.id_key, args.score_key, args.metric, args.cluster_key,
                           args.prompt_idx) for p in args.runs]
        paired = join_runs(loaded, args.dup, args.epochs)
        if args.epochs == "cluster" and paired.clusters is None and any(
                e["max"] > 1 for e in paired.diagnostics["epochs"]["per_input"]):
            paired.clusters = [pid.rsplit("#e", 1)[0] for pid in paired.ids]
        settings = Settings(args.alpha, args.power, args.margin, args.seed, args.reps)
        names = [r.path for r in loaded[1:]]
        comparisons, margin = analyze(paired, names, settings)
        inputs = [{"path": r.path, "format_detected": r.format_detected, "rows": len(r.rows),
                   "score_field": r.score_field} for r in loaded]
        loader_warnings = [w for r in loaded for w in r.warnings]
        report = build_report(inputs, paired, comparisons, settings, margin, loader_warnings)
    except ToolError as err:
        text = tr(lang, err.msg_key, **err.fields)
        print(f"error: {err.code}: {text}", file=sys.stderr)
        return err.exit_code
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.json == "-":
        sys.stdout.write(payload)
        return 0
    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except OSError as exc:
            print(f"error: bad-argument: {args.json}: {exc.strerror}", file=sys.stderr)
            return 2
    # 저장한 경로를 절대 경로로 알려 준다(에이전트가 다른 폴더에서 실행해도 파일 위치가 보이게)
    saved_to = os.path.abspath(args.json) if args.json else None
    sys.stdout.write(render_summary(report, lang, saved_to))
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
