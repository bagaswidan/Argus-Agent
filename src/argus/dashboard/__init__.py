"""Dashboard — Argus (Phase 6).

Read-only web dashboard over the observability store. Serves system
summary, recent traces, and recent logs as a single self-contained HTML
page. Uses only the standard library — no aiohttp required.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

from argus.observability.store import ObservabilityStore, create_obs_store

DASHBOARD_PORT = 8787

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Argus Dashboard</title>
<style>
:root, [data-theme="dark"] {
  --bg:#0c0c0f; --surface:#16161a; --surface2:#1c1c21; --border:rgba(255,255,255,0.08);
  --text:#ececee; --text2:#a3a3ad; --text3:#64646e; --accent:#c9a86b;
  --accent-dim:rgba(201,168,107,0.12); --ok:#7bc99a; --err:#e07a7a; --warn:#e8cd8e;
}
[data-theme="bright"] {
  --bg:#f4f3ef; --surface:#faf9f6; --surface2:#ffffff; --border:rgba(38,37,30,0.10);
  --text:#26251e; --text2:#5c5b54; --text3:#8a8982; --accent:#a8813a;
  --accent-dim:rgba(168,129,58,0.10); --ok:#1f8a65; --err:#cf2d56; --warn:#8a6528;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;min-height:100vh}
header{display:flex;align-items:center;gap:14px;padding:14px 24px;background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0}
header .brand{font-weight:700;font-size:15px;letter-spacing:.3px}
header .brand span{color:var(--accent)}
header .sub{font-size:12px;color:var(--text3);font-family:ui-monospace,monospace}
header .right{margin-left:auto;display:flex;gap:10px;align-items:center}
.toggle{display:flex;border:1px solid var(--border);border-radius:999px;padding:3px;background:var(--surface2)}
.toggle button{border:none;background:transparent;color:var(--text3);font-size:11px;padding:4px 10px;border-radius:999px;cursor:pointer;font-weight:500}
.toggle button.active{background:var(--accent);color:var(--bg)}
main{padding:24px;max-width:1100px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:24px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
.card .label{font-size:10.5px;text-transform:uppercase;letter-spacing:1.5px;color:var(--text3);margin-bottom:6px}
.card .value{font-size:30px;font-weight:700;font-family:ui-monospace,monospace}
.card .value.ok{color:var(--ok)} .card .value.err{color:var(--err)} .card .value.warn{color:var(--warn)}
.section{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin-bottom:20px}
.section h2{font-size:13px;font-weight:600;margin-bottom:12px;letter-spacing:.3px}
table{width:100%;border-collapse:collapse;font-size:12.5px;font-family:ui-monospace,monospace}
th{text-align:left;color:var(--text3);font-weight:500;font-size:10.5px;text-transform:uppercase;letter-spacing:1.2px;padding:6px 8px;border-bottom:1px solid var(--border)}
td{padding:7px 8px;border-bottom:1px solid var(--border);color:var(--text2)}
tr:hover td{background:var(--accent-dim)}
.status{display:inline-block;padding:2px 8px;border-radius:999px;font-size:10.5px}
.status.ok{background:rgba(123,201,154,.15);color:var(--ok)}
.status.err{background:rgba(224,122,122,.15);color:var(--err)}
.status.warn{background:rgba(232,205,142,.15);color:var(--warn)}
.empty{color:var(--text3);font-size:12.5px;padding:12px 4px;font-style:italic}
footer{padding:16px 24px;color:var(--text3);font-size:11px;font-family:ui-monospace,monospace;text-align:center;border-top:1px solid var(--border)}
</style>
</head>
<body>
<header>
  <div class="brand">argus<span>◆</span></div>
  <div class="sub">dashboard · $version</div>
  <div class="right">
    <div class="toggle" id="toggle">
      <button data-t="bright">Bright</button>
      <button data-t="dark" class="active">Dark</button>
    </div>
    <button class="toggle" onclick="location.reload()" style="padding:4px 10px;border-radius:999px;border:1px solid var(--border);background:var(--surface2);color:var(--text2);font-size:11px;cursor:pointer">↻ refresh</button>
  </div>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="label">Metrics</div><div class="value warn">$metric_count</div></div>
    <div class="card"><div class="label">Traces</div><div class="value ok">$trace_count</div></div>
    <div class="card"><div class="label">Logs</div><div class="value">$log_count</div></div>
    <div class="card"><div class="label">Errors</div><div class="value err">$error_count</div></div>
    <div class="card"><div class="label">Slow traces</div><div class="value">$slow_traces</div></div>
  </div>

  <div class="section">
    <h2>Recent traces</h2>
    $traces_table
  </div>

  <div class="section">
    <h2>Recent logs</h2>
    $logs_table
  </div>
</main>
<footer>argus v$version · observability store: $db_path</footer>
<script>
document.getElementById('toggle').querySelectorAll('button').forEach(b => {
  b.addEventListener('click', () => {
    document.documentElement.dataset.theme = b.dataset.t;
    document.querySelectorAll('#toggle button').forEach(x => x.classList.toggle('active', x === b));
  });
});
</script>
</body>
</html>
"""


def _traces_table(traces: list[dict[str, Any]]) -> str:
    if not traces:
        return '<div class="empty">No traces yet. Run something first.</div>'
    rows = []
    for t in traces:
        status_cls = "ok" if t.get("status") == "ok" else ("err" if t.get("status") == "error" else "warn")
        rows.append(
            f"<tr><td>{t.get('trace_id','')[:12]}</td><td>{t.get('name','')}</td>"
            f"<td><span class='status {status_cls}'>{t.get('status','')}</span></td>"
            f"<td>{t.get('duration_ms',0):.1f}ms</td><td>{t.get('span_count',0)}</td></tr>"
        )
    return (
        "<table><tr><th>Trace</th><th>Name</th><th>Status</th><th>Duration</th><th>Spans</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _logs_table(logs: list[dict[str, Any]]) -> str:
    if not logs:
        return '<div class="empty">No logs yet.</div>'
    rows = []
    for log in logs:
        level = log.get("level", "info")
        cls = "ok" if level == "info" else ("err" if level in ("error", "critical") else "warn")
        ts = str(log.get("timestamp", ""))[11:19]
        msg = str(log.get("message", ""))[:90]
        rows.append(
            f"<tr><td>{ts}</td><td><span class='status {cls}'>{level}</span></td>"
            f"<td>{log.get('logger','')}</td><td>{msg}</td></tr>"
        )
    return (
        "<table><tr><th>Time</th><th>Level</th><th>Logger</th><th>Message</th></tr>"
        + "".join(rows)
        + "</table>"
    )


class DashboardHandler(BaseHTTPRequestHandler):
    """Serves the dashboard page from the attached store."""

    store: ObservabilityStore = None  # type: ignore[assignment]
    version: str = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        body = render_dashboard(self.store, self.version).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # keep console quiet


def render_dashboard(store: ObservabilityStore, version: str = "") -> str:
    summary = store.get_summary()
    traces = store.list_traces(limit=12)
    logs = store.query_logs(limit=15)
    import string
    return string.Template(PAGE_TEMPLATE).substitute(
        version=version or "1.1.0",
        metric_count=summary["metric_count"],
        trace_count=summary["trace_count"],
        log_count=summary["log_count"],
        error_count=summary["error_count"],
        slow_traces=summary["slow_traces"],
        traces_table=_traces_table(traces),
        logs_table=_logs_table(logs),
        db_path=str(store.db_path),
    )


def serve_dashboard(
    store: ObservabilityStore,
    host: str = "127.0.0.1",
    port: int = DASHBOARD_PORT,
    version: str = "",
) -> None:
    """Start a dashboard server in the current thread. Blocks."""
    DashboardHandler.store = store
    DashboardHandler.version = version
    server = HTTPServer((host, port), DashboardHandler)
    server.serve_forever()


def run_dashboard_in_thread(
    store: ObservabilityStore,
    host: str = "127.0.0.1",
    port: int = DASHBOARD_PORT,
    version: str = "",
) -> tuple[HTTPServer, threading.Thread]:
    """Start the dashboard server in a background thread. Returns (server, thread)."""
    DashboardHandler.store = store
    DashboardHandler.version = version
    server = HTTPServer((host, port), DashboardHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t


def create_dashboard_store(path: Optional[str] = None) -> ObservabilityStore:
    """Convenience factory; defaults to a tempfile path (cross-platform)."""
    import tempfile
    path = path or str(Path(tempfile.gettempdir()) / "argus_dashboard.db")
    """Convenience factory for a dashboard-backed store."""
    return create_obs_store(path)
