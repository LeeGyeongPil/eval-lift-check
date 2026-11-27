#!/usr/bin/env python3
"""Plan an eval before running it: required items (Connor 1987) or minimum detectable difference.

Binary scores:     plan_n.py --discordant-rate 0.16 --delta 0.02
                   plan_n.py --discordant-rate 0.16 --n 300
                   plan_n.py --from-runs run_a.jsonl run_b.jsonl --delta 0.02
Continuous scores: plan_n.py --sd-diff 0.2 --delta 0.03 [--design-effect 1.5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _i18n  # noqa: E402
import _stats as st  # noqa: E402
from _i18n import phrase, tr  # noqa: E402
from _join import join_runs  # noqa: E402
from _loaders import FORMATS, ToolError, load_run  # noqa: E402
from _verdict import CONNOR, CONNOR_CODE, PAIRED_NORMAL, PAIRED_NORMAL_CODE  # noqa: E402


def build_parser(lang: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plan_n.py", description=tr(lang, "help.plan.desc"),
                                     epilog=tr(lang, "help.compare.epilog"))
    parser.add_argument("--discordant-rate", type=float, default=None, help=tr(lang, "help.plan.rate"))
    parser.add_argument("--delta", type=float, default=None, help=tr(lang, "help.plan.delta"))
    parser.add_argument("--n", type=int, default=None, help=tr(lang, "help.plan.n"))
    parser.add_argument("--sd-diff", type=float, default=None, help=tr(lang, "help.plan.sd_diff"))
    parser.add_argument("--design-effect", type=float, default=1.0, help=tr(lang, "help.plan.deff"))
    parser.add_argument("--from-runs", nargs=2, metavar=("A", "B"), default=None, help=tr(lang, "help.plan.from_runs"))
    parser.add_argument("--format", default="auto", metavar="{auto,%s}" % ",".join(FORMATS), help=tr(lang, "help.format"))
    parser.add_argument("--id-key", default=None, help=tr(lang, "help.id_key"))
    parser.add_argument("--score-key", default=None, help=tr(lang, "help.score_key"))
    parser.add_argument("--metric", default=None, help=tr(lang, "help.metric"))
    parser.add_argument("--alpha", type=float, default=0.05, help=tr(lang, "help.alpha"))
    parser.add_argument("--power", type=float, default=0.8, help=tr(lang, "help.power"))
    parser.add_argument("--json", metavar="PATH", default=None, help=tr(lang, "help.json"))
    parser.add_argument("--lang", choices=_i18n.LANGS, default=None, help=tr(lang, "help.lang"))
    return _i18n.localize_parser(parser, lang)


def _bad(key: str, **fields: object) -> ToolError:
    return ToolError("bad-argument", 2, key, **fields)


def _rate_from_runs(args: argparse.Namespace) -> tuple[float, int]:
    runs = [load_run(p, args.format, args.id_key, args.score_key, args.metric) for p in args.from_runs]
    paired = join_runs(runs, "first", "mean")
    if not paired.binary:
        raise _bad("bad.from-runs")
    a, b = paired.scores
    n = len(a)
    differ = sum(1 for x, y in zip(a, b) if x != y)
    return differ / n, n


def plan(args: argparse.Namespace) -> dict:
    """Validate arguments and compute the plan; raises ToolError on bad input."""
    if not (0.0 < args.alpha < 1.0 and 0.0 < args.power < 1.0):
        raise _bad("bad.alpha")
    if (args.delta is None) == (args.n is None):
        raise _bad("bad.mode")
    if args.n is not None and args.n < 2:
        raise _bad("bad.n", value=args.n)
    from_runs_n: Optional[int] = None
    if args.sd_diff is not None:  # continuous scores
        if args.sd_diff <= 0.0:
            raise _bad("bad.sd", value=args.sd_diff)
        if args.delta is not None and args.delta <= 0.0:
            raise _bad("bad.delta", delta=args.delta, rate="n/a")
        deff = args.design_effect
        parts = [phrase("a.sd_fixed", sd=args.sd_diff), phrase("a.alpha_power", alpha=args.alpha, power=args.power),
                 phrase("a.plan_deff", deff=deff)]
        assumptions = [text for text, _code in parts]
        codes = [code for _text, code in parts]
        if args.delta is not None:
            needed = st.required_n_continuous(args.sd_diff, args.delta, args.alpha, args.power, deff)
            return {"mode": "required-n", "score_type": "continuous", "n": needed, "delta": args.delta,
                    "method": PAIRED_NORMAL, "assumptions": assumptions,
                    "method_code": PAIRED_NORMAL_CODE, "assumption_codes": codes}
        mde = st.mde_continuous(args.n, args.sd_diff, args.alpha, args.power, deff)
        return {"mode": "mde", "score_type": "continuous", "n_items": args.n, "mde": mde,
                "method": PAIRED_NORMAL, "assumptions": assumptions,
                "method_code": PAIRED_NORMAL_CODE, "assumption_codes": codes}
    rate = args.discordant_rate
    if args.from_runs:
        rate, from_runs_n = _rate_from_runs(args)
    if rate is None:
        raise _bad("bad.need-rate")
    if not 0.0 < rate <= 1.0:
        raise _bad("bad.rate", value=rate)
    parts = [phrase("a.plan_rate", rate=f"{rate:.6f}"), phrase("a.alpha_power", alpha=args.alpha, power=args.power),
             phrase("a.plan_mcnemar")]
    assumptions = [text for text, _code in parts]
    codes = [code for _text, code in parts]
    if args.delta is not None:
        if args.delta <= 0.0 or args.delta >= rate:
            raise _bad("bad.delta", delta=args.delta, rate=rate)
        needed = st.required_n_for_delta(rate, args.delta, args.alpha, args.power)
        result = {"mode": "required-n", "score_type": "binary", "n": needed, "delta": args.delta,
                  "discordant_rate": rate, "method": CONNOR, "assumptions": assumptions,
                  "method_code": CONNOR_CODE, "assumption_codes": codes}
    else:
        mde = st.mde_binary(args.n, rate, args.alpha, args.power)
        result = {"mode": "mde", "score_type": "binary", "n_items": args.n, "mde": mde,
                  "discordant_rate": rate, "method": CONNOR, "assumptions": assumptions,
                  "method_code": CONNOR_CODE, "assumption_codes": codes}
    if from_runs_n is not None:
        result["from_runs_paired"] = from_runs_n
    return result


def render(result: dict, lang: str) -> str:
    out = [tr(lang, "plan.title")]
    if "from_runs_paired" in result:
        out.append(tr(lang, "plan.from_runs", rate=f"{result['discordant_rate']:.4f}", n=result["from_runs_paired"]))
    if result["mode"] == "required-n":
        out.append(tr(lang, "plan.required", n=result["n"]))
    else:
        mde = result["mde"]
        out.append(tr(lang, "plan.mde", n=result["n_items"], mde="n/a" if mde is None else f"{mde:.4f}"))
    method_code = dict(result["method_code"])
    out.append(tr(lang, "plan.method", method=tr(lang, method_code.pop("code"), **method_code)))
    for record in result["assumption_codes"]:
        fields = dict(record)
        out.append(tr(lang, "plan.assumption", text=tr(lang, fields.pop("code"), **fields)))
    return "\n".join(out) + "\n"


def run(argv: Optional[Sequence[str]] = None, env: Optional[dict] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ) if env is None else env
    lang = _i18n.peek_lang(argv, env)
    args = build_parser(lang).parse_args(argv)
    lang = _i18n.detect_lang(args.lang, env)
    try:
        result = plan(args)
    except ToolError as err:
        print(f"error: {err.code}: {tr(lang, err.msg_key, **err.fields)}", file=sys.stderr)
        return err.exit_code
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
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
    text = render(result, lang)
    if args.json:
        # 저장 위치를 절대 경로로 알려 준다
        text += tr(lang, "sum.saved", path=os.path.abspath(args.json)) + "\n"
    sys.stdout.write(text)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
