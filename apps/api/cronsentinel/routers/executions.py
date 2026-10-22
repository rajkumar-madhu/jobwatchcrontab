import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from .. import hostcontext
from ..auth import Principal, current_principal
from ..db import tenant_session
from ..schemas import ExecutionDetailOut

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])


def _logs(s, execution_id: str) -> dict[str, str]:
    rows = s.execute(text("SELECT stream, chunk_idx, content FROM execution_logs WHERE execution_id=:id ORDER BY stream, chunk_idx"),
                     {"id": execution_id}).all()
    return {st: "".join(r.content for r in rows if r.stream == st) for st in ("stdout", "stderr")}


@router.get("/{execution_id}", response_model=ExecutionDetailOut)
def get_execution(execution_id: str, p: Principal = Depends(current_principal)):
    with tenant_session(p.org_id) as s:
        e = s.execute(text("SELECT * FROM executions WHERE id=:id"), {"id": execution_id}).first()
        if not e: raise HTTPException(404)
        events = s.execute(text("SELECT sequence, kind, agent_ts, server_ts, payload FROM execution_events WHERE execution_id=:id ORDER BY sequence"),
                           {"id": execution_id}).all()
        logs = _logs(s, execution_id)
        # R70: the host this run was on. The job's server when an agent discovered it; else the
        # `host` the run reported, matched to a server of the same name if we have one.
        srv = s.execute(text("SELECT sv.id, sv.hostname, sv.facts FROM executions x JOIN jobs j ON j.id = x.job_id "
                             "LEFT JOIN servers sv ON sv.id = j.server_id OR (j.server_id IS NULL AND sv.hostname = x.host) "
                             "WHERE x.id=:id ORDER BY (sv.id = j.server_id) DESC NULLS LAST LIMIT 1"), {"id": execution_id}).first()
        host = None
        if e.host or (srv and srv.id):
            host = {"hostname": e.host or (srv.hostname if srv else None), "server_id": srv.id if srv else None, "facts": (srv.facts if srv and srv.id else None) or {},
                    "metrics_during": hostcontext.metrics_during(s, srv.id, e.agent_ts_start or e.scheduled_ts, e.agent_ts_end) if srv and srv.id else []}
    d = dict(e._mapping); d["status"] = str(d["status"])
    return {"execution": d, "timeline": [dict(r._mapping) for r in events], "logs": logs,
            "log_bytes": {k: len(v.encode()) for k, v in logs.items()}, "exit_meaning": hostcontext.exit_meaning(e.exit_code), "host": host}


@router.get("/{execution_id}/logs", response_class=PlainTextResponse, responses={200: {"content": {"text/plain": {}}}})
def download_logs(execution_id: str, stream: str = Query("both", pattern="^(stdout|stderr|both)$"), p: Principal = Depends(current_principal)):
    """R70: the run's output as a file. `both` puts stderr after stdout with a marker line."""
    with tenant_session(p.org_id) as s:
        if not s.execute(text("SELECT 1 FROM executions WHERE id=:id"), {"id": execution_id}).first(): raise HTTPException(404)
        logs = _logs(s, execution_id)
    body = logs[stream] if stream != "both" else f"{logs['stdout']}\n----- stderr -----\n{logs['stderr']}"
    # R72: execution ids are client-chosen; a non-ASCII or CR/LF id must not reach the header raw
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", execution_id).strip("_")[:80] or "run"
    utf8 = quote(f"run-{execution_id}-{stream}.log", safe="")
    return PlainTextResponse(body, headers={"Content-Disposition": f'attachment; filename="run-{safe}-{stream}.log"; filename*=UTF-8\'\'{utf8}',
                                            "X-Content-Type-Options": "nosniff"})


@router.get("/{execution_id}/compare/{other_id}")
def compare(execution_id: str, other_id: str, p: Principal = Depends(current_principal)):
    with tenant_session(p.org_id) as s:
        rows = s.execute(text("SELECT id, status, duration_ms, exit_code, host, scheduled_ts, agent_ts_start, agent_ts_end FROM executions WHERE id IN (:a, :b)"),
                         {"a": execution_id, "b": other_id}).all()
    if len(rows) != 2: raise HTTPException(404)
    a, b = ({**dict(r._mapping), "status": str(r.status)} for r in rows)
    delta = None
    if a["duration_ms"] and b["duration_ms"]:
        delta = {"duration_ms": b["duration_ms"] - a["duration_ms"], "pct": round((b["duration_ms"] - a["duration_ms"]) / a["duration_ms"] * 100, 1)}
    return {"a": a, "b": b, "delta": delta}
