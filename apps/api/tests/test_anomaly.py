"""R68: unusual-run detection (pure)."""
import random

import pytest

from cronsentinel import anomaly as A


def hist(durations=None, metrics=None, n=30):
    out = []
    for i in range(n):
        out.append({"duration_ms": durations[i % len(durations)] if durations else None,
                    "metrics": {k: v[i % len(v)] for k, v in (metrics or {}).items()}})
    return out


# a backup that usually takes 19–21 minutes and writes 4.1–4.3 GB
BACKUP = hist(durations=[1_140_000, 1_200_000, 1_260_000, 1_180_000, 1_230_000],
              metrics={"size_bytes": [4.1e9, 4.2e9, 4.3e9, 4.15e9, 4.25e9]})


def kinds(found):
    return [(f["kind"], f["field"]) for f in found]


def test_normal_run_is_not_flagged():
    assert A.detect(1_215_000, {"size_bytes": 4.22e9}, BACKUP) == []


def test_slow_run():
    f = A.detect(4_200_000, {"size_bytes": 4.2e9}, BACKUP)
    assert kinds(f) == [("slow", "duration")]
    assert f[0]["message"] == "ran 1 h 10 min; usually 20 min 00 s (3.5× longer)" and f[0]["runs"] == 30


def test_fast_run_that_probably_did_nothing():
    f = A.detect(3_000, {"size_bytes": 4.2e9}, BACKUP)
    assert kinds(f) == [("fast", "duration")] and "it may have done nothing" in f[0]["message"]
    assert f[0]["message"].startswith("finished in 3.0 s; usually 20 min 00 s")


def test_suspiciously_small_output():
    f = A.detect(1_200_000, {"size_bytes": 1200}, BACKUP)
    assert kinds(f) == [("low", "size_bytes")]
    assert f[0]["message"] == "size_bytes was 1.2 KB; usually 4.2 GB — suspiciously small"


def test_errors_appearing_where_there_were_none():
    h = hist(durations=[60_000], metrics={"error_count": [0]})
    f = A.detect(60_000, {"error_count": 3}, h)
    assert kinds(f) == [("high", "error_count")] and f[0]["message"] == "error_count was 3; usually 0"


def test_not_enough_history():
    assert A.detect(9_999_999, {"size_bytes": 1}, BACKUP[: A.MIN_HISTORY - 1]) == []
    assert A.detect(9_999_999, {}, BACKUP[: A.MIN_HISTORY]) != []


def test_off_and_unknown_sensitivity():
    assert A.detect(9_999_999, {}, BACKUP, "off") == [] and A.detect(9_999_999, {}, BACKUP, "bogus") == []


def test_sensitivity_changes_the_threshold():
    noisy = hist(durations=[100_000, 120_000, 140_000, 160_000, 180_000])          # median 140 s, MAD 20 s → spread 29.7 s
    d = 140_000 + 4 * 29_652 + 1_000                                              # just past 4 spreads: 3·… < x < 4.5·…
    assert kinds(A.detect(int(d), {}, noisy, "high")) == [("slow", "duration")]
    assert A.detect(int(d), {}, noisy, "normal") == [] and A.detect(int(d), {}, noisy, "low") == []


def test_absolute_and_relative_floors():
    tiny = hist(durations=[2_000, 2_100, 1_900])                                  # a 2-second job
    assert A.detect(20_000, {}, tiny) == []                                       # 10× slower, but only 18 s longer
    assert A.detect(100, {}, tiny) == []                                          # too short a job to judge "fast"
    steady = hist(durations=[600_000])                                            # always exactly 10 minutes
    assert A.detect(630_000, {}, steady) == []                                    # zero spread: the 1.5× floor keeps 5 % slower quiet
    assert kinds(A.detect(960_000, {}, steady)) == [("slow", "duration")]


def test_one_past_outlier_does_not_move_the_baseline():
    h = BACKUP[:29] + [{"duration_ms": 50_000_000, "metrics": {"size_bytes": 1}}]
    assert kinds(A.detect(4_200_000, {}, h)) == [("slow", "duration")]
    assert kinds(A.detect(1_200_000, {"size_bytes": 1000}, h)) == [("low", "size_bytes")]


def test_missing_values_and_garbage_are_ignored():
    h = BACKUP + [{"duration_ms": None, "metrics": {"size_bytes": "x"}}]
    assert A.detect(None, {"size_bytes": float("nan"), "rows": 5}, h) == []      # rows has no history


def test_history_capped():
    old = hist(durations=[60_000], n=200)
    new = hist(durations=[600_000], n=A.HISTORY)
    assert A.detect(600_000, {}, new + old) == []                                 # only the newest 50 count


@pytest.mark.parametrize("seed", range(20))
def test_false_alarm_rate_on_ordinary_noise(seed):
    """Normally distributed runtimes (CV 10 %) must almost never be flagged at normal sensitivity."""
    rng = random.Random(seed)
    h = [{"duration_ms": max(1, int(rng.gauss(600_000, 60_000))), "metrics": {}} for _ in range(50)]
    flagged = sum(bool(A.detect(int(rng.gauss(600_000, 60_000)), {}, h)) for _ in range(500))
    assert flagged <= 1


@pytest.mark.parametrize("ms,txt", [(3_000, "3.0 s"), (45_000, "45 s"), (125_000, "2 min 05 s"), (3_720_000, "1 h 02 min")])
def test_human_ms(ms, txt):
    assert A.human_ms(ms) == txt


def test_human_value():
    assert A.human_value("size_bytes", 4.2e9) == "4.2 GB" and A.human_value("bytes", 512) == "512 B"
    assert A.human_value("rows", 1_500_000) == "1.5M" and A.human_value("rows", 25_000) == "25.0k" and A.human_value("rows", 12) == "12"
