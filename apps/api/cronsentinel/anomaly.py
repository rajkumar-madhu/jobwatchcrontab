"""R68 — unusual runs, learned from the job's own history. No rules to write.

A run can exit 0 and still be wrong: a backup that finished in 3 seconds instead of 20 minutes, a
nightly export that ran four times longer than ever before, a dump of 1.2 KB where it is usually
4 GB. Run checks (R54) catch these only if someone wrote the rule. This compares each successful
run with the job's recent successful runs and says, in plain words, what was unusual.

Method: robust statistics, so one past outlier cannot move the baseline.
  typical  = median of the last HISTORY successful runs (runs already flagged as unusual are left out)
  spread   = 1.4826 × median absolute deviation (MAD) — matches the standard deviation for normal data
  The relative floors below matter as much as the spread: a job whose runs are all exactly 10 minutes
  has zero spread, and only "≥ 1.5× typical" keeps a 2 % slower run from being flagged.
  unusual  = more than K spreads from typical  AND  a clear relative change  AND  an absolute floor:
    slow      duration > typical + K·spread, ≥ 1.5× typical and ≥ 30 s longer
    fast      duration < typical − K·spread, ≤ 0.25× typical, typical ≥ 20 s   ("it may have done nothing")
    low       metric   < typical − K·spread, ≤ 0.5× typical, typical > 0         ("suspiciously small")
    high      metric   > typical + K·spread, ≥ 2× typical
  K by sensitivity: low 6 · normal 4.5 · high 3. Nothing is judged before MIN_HISTORY runs.

Only successful runs are judged: a failed run is already a failure.
"""
import math
from dataclasses import dataclass
from statistics import median

HISTORY = 50
MIN_HISTORY = 10
SENSITIVITY_K = {"low": 6.0, "normal": 4.5, "high": 3.0}
SENSITIVITIES = ("off", "low", "normal", "high")
ACTIONS = ("warn", "fail")
MAD_SCALE = 1.4826
SLOW_RATIO, SLOW_ABS_MS = 1.5, 30_000
FAST_RATIO, FAST_MIN_TYPICAL_MS = 0.25, 20_000
LOW_RATIO, HIGH_RATIO = 0.5, 2.0


@dataclass(frozen=True)
class Baseline:
    typical: float
    spread: float
    n: int


def baseline(values: list[float]) -> Baseline | None:
    xs = [float(v) for v in values if isinstance(v, int | float) and math.isfinite(v)]
    if len(xs) < MIN_HISTORY:
        return None
    m = median(xs)
    mad = median(abs(x - m) for x in xs) * MAD_SCALE
    return Baseline(typical=m, spread=mad, n=len(xs))


def human_ms(ms: float) -> str:
    s = int(round(ms / 1000))
    if s < 60:
        return f"{max(ms / 1000, 0):.1f} s" if ms < 10_000 else f"{s} s"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    return f"{m} min {sec:02d} s"


def human_value(name: str, v: float) -> str:
    if "byte" in name.lower():
        for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
            if abs(v) >= size:
                return f"{v / size:.1f} {unit}"
        return f"{v:g} B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}M"
    if abs(v) >= 1e4:
        return f"{v / 1e3:.1f}k"
    return f"{v:g}"


def detect(duration_ms: int | None, metrics: dict, history: list[dict], sensitivity: str = "normal") -> list[dict]:
    """history: previous successful runs, newest first, each {"duration_ms": int | None, "metrics": dict}.
    Returns findings: {kind: slow|fast|low|high, field, value, typical, runs, message}."""
    k = SENSITIVITY_K.get(sensitivity)
    if k is None:
        return []
    hist = history[:HISTORY]
    out: list[dict] = []
    if duration_ms is not None:
        b = baseline([h.get("duration_ms") for h in hist if h.get("duration_ms") is not None])
        if b:
            d = float(duration_ms)
            if d > b.typical + k * b.spread and d >= SLOW_RATIO * b.typical and d - b.typical >= SLOW_ABS_MS:
                out.append({"kind": "slow", "field": "duration", "value": d, "typical": b.typical, "runs": b.n,
                            "message": f"ran {human_ms(d)}; usually {human_ms(b.typical)} ({d / b.typical:.1f}× longer)"})
            elif b.typical >= FAST_MIN_TYPICAL_MS and d < b.typical - k * b.spread and d <= FAST_RATIO * b.typical:
                out.append({"kind": "fast", "field": "duration", "value": d, "typical": b.typical, "runs": b.n,
                            "message": f"finished in {human_ms(d)}; usually {human_ms(b.typical)} — it may have done nothing"})
    for name, v in sorted((metrics or {}).items()):
        if not isinstance(v, int | float) or not math.isfinite(v):
            continue
        b = baseline([(h.get("metrics") or {}).get(name) for h in hist])
        if not b:
            continue
        if b.typical > 0 and v < b.typical - k * b.spread and v <= LOW_RATIO * b.typical:
            out.append({"kind": "low", "field": name, "value": float(v), "typical": b.typical, "runs": b.n,
                        "message": f"{name} was {human_value(name, v)}; usually {human_value(name, b.typical)} — suspiciously small"})
        elif v > b.typical + k * b.spread and (b.typical <= 0 or v >= HIGH_RATIO * b.typical) and b.typical >= 0:
            out.append({"kind": "high", "field": name, "value": float(v), "typical": b.typical, "runs": b.n,
                        "message": f"{name} was {human_value(name, v)}; usually {human_value(name, b.typical)}"})
    return out


def load_history(s, job_id, exclude_execution_id=None) -> list[dict]:
    """The job's recent successful runs that were not themselves unusual, newest first."""
    from sqlalchemy import text
    rows = s.execute(text("""SELECT duration_ms, metrics FROM executions
        WHERE job_id = :j AND status = 'success' AND id <> COALESCE(:x, '') AND NOT (meta ? 'anomalies')
          AND scheduled_ts > now() - interval '120 days'
        ORDER BY scheduled_ts DESC LIMIT :n"""), {"j": str(job_id), "x": exclude_execution_id, "n": HISTORY}).all()
    return [{"duration_ms": r.duration_ms, "metrics": dict(r.metrics or {})} for r in rows]
