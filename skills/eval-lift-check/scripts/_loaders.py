"""Format detection and adapters: generic JSONL/CSV, lm-eval, Inspect, promptfoo.

Every adapter returns a RunData whose rows carry a pairing key, a numeric score
and optional cluster / epoch / hash fields. Nothing here does statistics.
"""
from __future__ import annotations

import csv
import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

FORMATS = ("jsonl", "csv", "lm-eval", "inspect", "promptfoo")
ZSTD_METHOD = 93  # ZIP compression method id for zstd

_SCORE_WORDS = {
    "true": 1.0, "false": 0.0, "yes": 1.0, "no": 0.0,
    "c": 1.0, "i": 0.0, "p": 0.5, "n": 0.0,
    "correct": 1.0, "incorrect": 0.0, "pass": 1.0, "fail": 0.0,
}
_LM_EVAL_NAME = re.compile(r"^samples_(?P<task>.+)_(?P<ts>\d{4}-\d{2}-\d{2}T[\d\-.:]+)\.jsonl?$")
_LM_EVAL_PREFERRED = ("acc", "exact_match", "acc_norm", "pass@1", "f1", "bleu", "rouge")


class ToolError(Exception):
    """A user-facing failure: stable ``code``, exit code, message key and fields."""

    def __init__(self, code: str, exit_code: int, msg_key: Optional[str] = None, **fields: Any) -> None:
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code
        self.msg_key = msg_key or f"err.{code}"
        self.fields = fields


@dataclass
class Row:
    key: str
    score: float
    cluster: Optional[str] = None
    epoch: Optional[int] = None
    doc_hash: Optional[str] = None
    task: Optional[str] = None  # lm-eval 태스크 이름(태스크별 보조 결과용)


@dataclass
class RunData:
    path: str
    format_detected: str
    rows: list[Row]
    score_field: str = ""
    warnings: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------
# score normalization
# --------------------------------------------------------------------------
def normalize_score(value: Any) -> float:
    """Turn 0/1, true/false, C/I, strings and numbers into a float; ValueError otherwise."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        word = value.strip().lower()
        if word in _SCORE_WORDS:
            return _SCORE_WORDS[word]
        number = float(word)  # ValueError if not a number
    else:
        raise ValueError(f"unsupported score type {type(value).__name__}")
    if math.isnan(number) or math.isinf(number):
        raise ValueError("score is not finite")
    return number


def _score(path: str, row_no: int, value: Any) -> float:
    try:
        return normalize_score(value)
    except ValueError:
        raise ToolError("score-not-numeric", 2, path=path, row=row_no, value=value) from None


def _seen(row: dict) -> str:
    return ", ".join(sorted(str(k) for k in row)) or "(none)"


def _dig(row: dict, dotted: str) -> Any:
    """Read ``a.b`` style nested keys, trying the literal key first."""
    if dotted in row:
        return row[dotted]
    cur: Any = row
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur


def _cluster_of(path: str, row_no: int, row: dict, cluster_key: Optional[str],
                extra: tuple[str, ...] = ()) -> Optional[str]:
    if cluster_key is None:
        return None
    for source in (row, *(row.get(name) for name in extra if isinstance(row.get(name), dict))):
        try:
            return str(_dig(source, cluster_key))
        except KeyError:
            continue
    raise ToolError("cluster-missing", 2, path=path, row=row_no, key=cluster_key, seen=_seen(row))


# --------------------------------------------------------------------------
# reading helpers
# --------------------------------------------------------------------------
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ToolError("file-not-found", 2, path=str(path)) from None
    except UnicodeDecodeError as exc:
        raise ToolError("bad-encoding", 2, path=str(path), offset=exc.start) from None


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(_read_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ToolError("bad-json", 2, path=str(path), reason=f"line {number}: {exc.msg}") from None
        if not isinstance(obj, dict):
            raise ToolError("unknown-format", 2, path=str(path))
        rows.append(obj)
    return rows


def _read_json(path: Path) -> Any:
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise ToolError("bad-json", 2, path=str(path), reason=exc.msg) from None


# --------------------------------------------------------------------------
# format detection
# --------------------------------------------------------------------------
def detect_format(path: Path) -> str:
    if not path.exists():
        raise ToolError("file-not-found", 2, path=str(path))
    if path.is_dir():
        if any(path.rglob("samples_*.jsonl")) or any(path.rglob("samples_*.json")):
            return "lm-eval"
        raise ToolError("unknown-format", 2, path=str(path))
    suffix = path.suffix.lower()
    if suffix == ".eval":
        return "inspect"
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        data = _read_json(path)
        if isinstance(data, dict) and isinstance(data.get("samples"), list):
            return "inspect"
        if isinstance(data, dict) and "results" in data:
            return "promptfoo"
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return "promptfoo" if ("testIdx" in data[0] or "success" in data[0]) else "jsonl"
        raise ToolError("unknown-format", 2, path=str(path))
    if suffix in (".jsonl", ".ndjson"):
        rows = _read_jsonl(path)
        if not rows:
            raise ToolError("no-rows", 2, path=str(path))
        first = rows[0]
        if "doc_id" in first:
            return "lm-eval"
        if "testIdx" in first or ("success" in first and "prompt" in first):
            return "promptfoo"
        return "jsonl"
    raise ToolError("unknown-format", 2, path=str(path))


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------
def _load_generic(path: Path, fmt: str, id_key: str, score_key: str, cluster_key: Optional[str]) -> RunData:
    if fmt == "csv":
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                raw_rows = list(csv.DictReader(handle))
        except FileNotFoundError:
            raise ToolError("file-not-found", 2, path=str(path)) from None
        except UnicodeDecodeError as exc:
            raise ToolError("bad-encoding", 2, path=str(path), offset=exc.start) from None
    elif path.suffix.lower() == ".json":
        data = _read_json(path)
        if not (isinstance(data, list) and all(isinstance(r, dict) for r in data)):
            raise ToolError("unknown-format", 2, path=str(path))
        raw_rows = data
    else:
        raw_rows = _read_jsonl(path)
    if not raw_rows:
        raise ToolError("no-rows", 2, path=str(path))
    rows: list[Row] = []
    for number, raw in enumerate(raw_rows, 1):
        if id_key not in raw:
            raise ToolError("id-missing", 2, path=str(path), row=number, key=id_key, seen=_seen(raw))
        if score_key not in raw:
            raise ToolError("score-missing", 2, path=str(path), row=number, key=score_key, seen=_seen(raw))
        rows.append(Row(
            key=str(raw[id_key]),
            score=_score(str(path), number, raw[score_key]),
            cluster=_cluster_of(str(path), number, raw, cluster_key),
        ))
    return RunData(str(path), fmt, rows, score_field=score_key)


def _lm_eval_files(path: Path) -> list[tuple[str, str, Path]]:
    """Return (task, timestamp, file) for a samples file or a folder of them."""
    if path.is_dir():
        files = sorted(set(path.rglob("samples_*.jsonl")) | set(path.rglob("samples_*.json")))
    else:
        files = [path]
    found = []
    for file in files:
        match = _LM_EVAL_NAME.match(file.name)
        if match:
            found.append((match["task"], match["ts"], file))
        else:
            found.append(("", "", file))
    return found


def _lm_eval_metric(row: dict, metric: Optional[str]) -> Optional[str]:
    if metric:
        return metric if metric in row else None
    listed = row.get("metrics")
    if isinstance(listed, list):
        for name in listed:
            if isinstance(name, str) and name in row:
                return name
    for name in _LM_EVAL_PREFERRED:
        if name in row:
            return name
    for name in row:
        if isinstance(name, str) and (name.startswith("acc") or name.startswith("exact_match")):
            return name
    return None


def _load_lm_eval(path: Path, id_key: Optional[str], metric: Optional[str], cluster_key: Optional[str]) -> RunData:
    found = _lm_eval_files(path)
    warnings: list[dict] = []
    latest: dict[str, tuple[str, Path]] = {}
    for task, stamp, file in found:
        if task in latest:
            warnings_task = task or file.stem
            if stamp > latest[task][0]:
                latest[task] = (stamp, file)
            name = latest[task][1].name
            if not any(w.get("task") == warnings_task for w in warnings):
                warnings.append({"code": "lm-eval-latest", "task": warnings_task, "name": name})
            else:
                for w in warnings:
                    if w.get("task") == warnings_task:
                        w["name"] = name
        else:
            latest[task] = (stamp, file)
    rows: list[Row] = []
    used_metric = ""
    for task in sorted(latest):
        file = latest[task][1]
        for number, raw in enumerate(_read_jsonl(file), 1):
            doc_key = id_key or "doc_id"
            if doc_key not in raw:
                raise ToolError("id-missing", 2, path=str(file), row=number, key=doc_key, seen=_seen(raw))
            name = _lm_eval_metric(raw, metric)
            if name is None:
                raise ToolError("score-missing", 2, path=str(file), row=number, key=metric or "acc",
                                seen=_seen(raw))
            used_metric = name
            key = f"{task}/{raw[doc_key]}" if task else str(raw[doc_key])
            doc_hash = raw.get("doc_hash")
            doc = raw.get("doc") if isinstance(raw.get("doc"), dict) else {}
            if cluster_key == "task" and "task" not in raw and "task" not in doc:
                # 태스크로 군집을 묶으려는 흔한 실수: 몇 개의 태스크는 군집이 아니다
                raise ToolError("cluster-missing", 2, "err.cluster-task", path=str(file), key=cluster_key)
            rows.append(Row(
                key=key,
                score=_score(str(file), number, raw[name]),
                cluster=_cluster_of(str(file), number, raw, cluster_key, ("doc",)),
                doc_hash=None if doc_hash is None else str(doc_hash),
                task=task or None,
            ))
    if not rows:
        raise ToolError("no-rows", 2, path=str(path))
    return RunData(str(path), "lm-eval", rows, score_field=used_metric, warnings=warnings)


def _inspect_samples(path: Path) -> list[dict]:
    if path.suffix.lower() != ".eval":
        data = _read_json(path)
        samples = data.get("samples") if isinstance(data, dict) else None
        if not isinstance(samples, list):
            raise ToolError("unknown-format", 2, path=str(path))
        return samples
    try:
        archive = zipfile.ZipFile(path)
    except FileNotFoundError:
        raise ToolError("file-not-found", 2, path=str(path)) from None
    except zipfile.BadZipFile:
        raise ToolError("unknown-format", 2, path=str(path)) from None
    samples: list[dict] = []
    with archive:
        members = [i for i in archive.infolist() if i.filename.startswith("samples/") and i.filename.endswith(".json")]
        for info in members:
            try:
                samples.append(json.loads(archive.read(info)))
            except json.JSONDecodeError as exc:
                raise ToolError("bad-json", 2, path=str(path), reason=f"{info.filename}: {exc.msg}") from None
            except Exception:
                if info.compress_type == ZSTD_METHOD:
                    raise ToolError("inspect-zstd", 2, path=str(path)) from None
                raise
    return samples


def _load_inspect(path: Path, id_key: Optional[str], metric: Optional[str], cluster_key: Optional[str]) -> RunData:
    samples = _inspect_samples(path)
    if not samples:
        raise ToolError("no-rows", 2, path=str(path))
    rows: list[Row] = []
    scorer_used = ""
    for number, sample in enumerate(samples, 1):
        if not isinstance(sample, dict):
            raise ToolError("unknown-format", 2, path=str(path))
        scores = sample.get("scores") or {}
        name = metric or (next(iter(scores)) if scores else None)
        if name is None or name not in scores:
            raise ToolError("score-missing", 2, path=str(path), row=number, key=metric or "scores",
                            seen=", ".join(sorted(scores)) or "(no scores)")
        scorer_used = name
        value = scores[name].get("value") if isinstance(scores[name], dict) else scores[name]
        sample_id = sample.get(id_key or "id")
        if sample_id is None:
            raise ToolError("id-missing", 2, path=str(path), row=number, key=id_key or "id", seen=_seen(sample))
        epoch = sample.get("epoch")
        rows.append(Row(
            key=str(sample_id),
            score=_score(str(path), number, value),
            cluster=_cluster_of(str(path), number, sample, cluster_key, ("metadata",)),
            epoch=int(epoch) if isinstance(epoch, (int, float)) else None,
        ))
    return RunData(str(path), "inspect", rows, score_field=scorer_used)


def _promptfoo_results(path: Path) -> list[dict]:
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        return _read_jsonl(path)
    data = _read_json(path)
    if isinstance(data, dict):
        inner = data.get("results")
        if isinstance(inner, dict):
            inner = inner.get("results")
        data = inner
    if not (isinstance(data, list) and all(isinstance(r, dict) for r in data)):
        raise ToolError("unknown-format", 2, path=str(path))
    return data


def _load_promptfoo(path: Path, id_key: Optional[str], score_key: Optional[str], cluster_key: Optional[str],
                    prompt_idx: Optional[int]) -> RunData:
    raw_rows = _promptfoo_results(path)
    warnings: list[dict] = []
    if prompt_idx is not None:
        raw_rows = [r for r in raw_rows if r.get("promptIdx") == prompt_idx]
    else:
        prompts = {r.get("promptIdx") for r in raw_rows if "promptIdx" in r}
        if len(prompts) > 1:
            warnings.append({"code": "prompt-idx", "path": str(path), "n": len(prompts)})
    if not raw_rows:
        raise ToolError("no-rows", 2, path=str(path))
    rows: list[Row] = []
    field_used = ""
    for number, raw in enumerate(raw_rows, 1):
        if id_key:
            key_value: Any = None
            for source in (raw.get("vars"), raw.get("testCase", {}).get("vars") if isinstance(raw.get("testCase"), dict) else None, raw):
                if isinstance(source, dict) and id_key in source:
                    key_value = source[id_key]
                    break
            if key_value is None:
                raise ToolError("id-missing", 2, path=str(path), row=number, key=id_key, seen=_seen(raw))
        elif "testIdx" in raw:
            key_value = raw["testIdx"]
        else:
            key_value = json.dumps(raw.get("vars", {}), sort_keys=True)
        if score_key:
            if score_key not in raw:
                raise ToolError("score-missing", 2, path=str(path), row=number, key=score_key, seen=_seen(raw))
            value, field_used = raw[score_key], score_key
        elif "success" in raw:
            value, field_used = raw["success"], "success"
        elif isinstance(raw.get("gradingResult"), dict) and "pass" in raw["gradingResult"]:
            value, field_used = raw["gradingResult"]["pass"], "gradingResult.pass"
        elif "pass" in raw:
            value, field_used = raw["pass"], "pass"
        else:
            raise ToolError("score-missing", 2, path=str(path), row=number, key="success", seen=_seen(raw))
        rows.append(Row(
            key=str(key_value),
            score=_score(str(path), number, value),
            cluster=_cluster_of(str(path), number, raw, cluster_key, ("vars",)),
        ))
    warnings.append({"code": "promptfoo-field", "path": str(path), "field": field_used})
    return RunData(str(path), "promptfoo", rows, score_field=field_used, warnings=warnings)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def load_run(
    path: str,
    fmt: str = "auto",
    id_key: Optional[str] = None,
    score_key: Optional[str] = None,
    metric: Optional[str] = None,
    cluster_key: Optional[str] = None,
    prompt_idx: Optional[int] = None,
) -> RunData:
    """Load one run. ``fmt='auto'`` detects the format from the extension and keys."""
    target = Path(path)
    if not target.exists():
        raise ToolError("file-not-found", 2, path=path)
    chosen = detect_format(target) if fmt == "auto" else fmt
    if chosen not in FORMATS:
        raise ToolError("unknown-format", 2, path=path)
    if chosen in ("jsonl", "csv"):
        return _load_generic(target, chosen, id_key or "id", score_key or metric or "score", cluster_key)
    if chosen == "lm-eval":
        return _load_lm_eval(target, id_key, metric or score_key, cluster_key)
    if chosen == "inspect":
        return _load_inspect(target, id_key, metric or score_key, cluster_key)
    return _load_promptfoo(target, id_key, score_key, cluster_key, prompt_idx)
