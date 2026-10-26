"""R74 — JobWatch monitors its own workers as ordinary jobs in the operator's organisation."""
import pytest
from sqlalchemy import text

from cronsentinel import selfmonitor
from cronsentinel.config import settings
from cronsentinel.db import system_session


@pytest.fixture
def selfmon(org, monkeypatch):
    monkeypatch.setattr(settings, "self_monitor_org_id", org["id"])
    selfmonitor.forget_cache()
    with system_session() as s:
        rows = selfmonitor.ensure_jobs(s, org["id"])
    yield {"org": org, "rows": {r["service"]: r for r in rows}}
    selfmonitor.forget_cache()


def _runs(job_id):
    with system_session() as s:
        return s.execute(text("SELECT status, exit_code, duration_ms, host FROM executions WHERE job_id=:j ORDER BY scheduled_ts, id"),
                         {"j": job_id}).all()


def test_ensure_jobs_is_idempotent_and_tagged(selfmon):
    rows = selfmon["rows"]
    assert set(rows) == set(selfmonitor.SERVICES)
    assert all(r["created"] for r in rows.values())
    with system_session() as s:
        again = selfmonitor.ensure_jobs(s, selfmon["org"]["id"])
        tags = s.execute(text("SELECT name, tags, schedule_expr, grace_s FROM jobs WHERE org_id=CAST(:o AS uuid) AND name LIKE 'jobwatch/%' ORDER BY name"),
                         {"o": selfmon["org"]["id"]}).all()
    assert all(not r["created"] for r in again)
    assert {r["job_id"] for r in again} == {r["job_id"] for r in rows.values()}
    assert [t.name for t in tags] == sorted(n for n, *_ in selfmonitor.SERVICES.values())
    assert all("self-monitor" in t.tags for t in tags)
    assert dict((t.name, t.schedule_expr) for t in tags)["jobwatch/scorer"] == "0 * * * *"


def test_report_records_a_run_and_throttles_successes(selfmon):
    jid = selfmon["rows"]["reconciler"]["job_id"]
    with system_session() as s:
        assert selfmonitor.report(s, "reconciler", duration_ms=120) is True
        assert selfmonitor.report(s, "reconciler", duration_ms=130) is False     # within THROTTLE_S
        assert selfmonitor.report(s, "reconciler", duration_ms=140, force=True) is True
    runs = _runs(jid)   # both land in the same millisecond, so their order is not defined
    assert [r.status for r in runs] == ["success", "success"]
    assert sorted(r.duration_ms for r in runs) == [120, 140]
    assert all(r.exit_code == 0 and r.host for r in runs)


def test_failure_is_always_recorded_with_the_error(selfmon):
    jid = selfmon["rows"]["schedule-generator"]["job_id"]
    with system_session() as s:
        assert selfmonitor.report(s, "schedule-generator", duration_ms=5) is True
        assert selfmonitor.report(s, "schedule-generator", ok=False, error="boom: generator exploded") is True
        status = s.execute(text("SELECT status FROM jobs WHERE id=:j"), {"j": jid}).scalar()
        err = s.execute(text("SELECT content FROM execution_logs l JOIN executions e ON e.id=l.execution_id WHERE e.job_id=:j AND l.stream='stderr'"),
                        {"j": jid}).scalar()
    assert [r.status for r in _runs(jid)] == ["success", "failed"]
    assert status == "failed"
    assert "generator exploded" in (err or "")


def test_timed_context_manager_reports_and_reraises(selfmon):
    jid = selfmon["rows"]["scorer"]["job_id"]
    with selfmonitor.timed(system_session, "scorer"):
        pass
    with pytest.raises(ZeroDivisionError):
        with selfmonitor.timed(system_session, "scorer"):
            1 / 0
    runs = _runs(jid)
    assert [r.status for r in runs] == ["success", "failed"]


def test_disabled_or_unknown_service_is_a_noop(org, monkeypatch):
    monkeypatch.setattr(settings, "self_monitor_org_id", "")
    selfmonitor.forget_cache()
    with system_session() as s:
        assert selfmonitor.report(s, "reconciler") is False
        monkeypatch.setattr(settings, "self_monitor_org_id", org["id"])
        assert selfmonitor.report(s, "not-a-service") is False
        assert selfmonitor.report(s, "reconciler") is False       # jobs not created yet → nothing to report to
    selfmonitor.forget_cache()
