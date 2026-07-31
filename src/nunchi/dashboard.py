"""Dependency-free dashboard over the same validated operator schema as CLI."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .errors import ValidationError
from .operator import OperatorStore, ServiceManager, _MAX_CONFIG_BYTES


DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nunchi</title><style>
:root{color-scheme:light dark;font:15px system-ui,sans-serif}body{max-width:1100px;margin:2rem auto;padding:0 1rem}
h1{margin-bottom:.2rem}.muted{opacity:.7}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}
section{border:1px solid #8886;border-radius:12px;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:34rem;overflow:auto}
button{padding:.55rem .8rem;margin:.2rem}input,textarea{width:100%;box-sizing:border-box;margin:.25rem 0 .75rem;padding:.45rem}
.warning{color:#b65b00}.ok{color:#188038}</style></head>
<body><h1>Nunchi</h1><p class="muted">One profile, one validated schema, one service surface.</p>
<div class="grid"><section><h2>Health</h2><pre id="health">Loading…</pre></section>
<section><h2>Identity and rooms</h2><pre id="config">Loading…</pre></section>
<section><h2>Capabilities and compatibility</h2><pre id="capabilities">Loading…</pre></section>
<section><h2>Recent receipts</h2><pre id="receipts">Loading…</pre></section></div>
<script>
async function refresh(){const r=await fetch('/api/v1/operator',{headers:{Accept:'application/json'}});const d=await r.json();
for(const [id,v] of Object.entries({health:d.health,config:{identity:d.config.identity,rooms:d.config.rooms,models:d.config.models,attention_policy:d.config.attention_policy,ack_policy:d.config.ack_policy},capabilities:{capabilities:d.capabilities,compatibility:d.compatibility},receipts:d.recent_receipts}))document.getElementById(id).textContent=JSON.stringify(v,null,2)}
refresh().catch(e=>document.getElementById('health').textContent=String(e));setInterval(refresh,5000);
</script></body></html>"""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def dashboard_handler(store: OperatorStore) -> type[BaseHTTPRequestHandler]:
    services = ServiceManager(store)

    class Handler(BaseHTTPRequestHandler):
        server_version = "NunchiDashboard/1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()

        def _send_json(self, status: int, value: Any) -> None:
            payload = _json_bytes(value)
            self._headers(status, "application/json; charset=utf-8", len(payload))
            self.wfile.write(payload)

        def _error(self, status: int, detail: str) -> None:
            self._send_json(status, {"error": HTTPStatus(status).phrase, "detail": detail})

        def _body(self) -> Any:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type != "application/json":
                raise ValidationError("dashboard writes require application/json")
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "")
            except ValueError as exc:
                raise ValidationError("dashboard Content-Length is invalid") from exc
            if not 1 <= length <= _MAX_CONFIG_BYTES:
                raise ValidationError("dashboard request body exceeds the bounded size")
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError as exc:
                raise ValidationError(f"dashboard request is invalid JSON: {exc.msg}") from exc

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/":
                    payload = DASHBOARD_HTML.encode("utf-8")
                    self._headers(200, "text/html; charset=utf-8", len(payload))
                    self.wfile.write(payload)
                    return
                if parsed.path == "/api/v1/operator":
                    query = parse_qs(parsed.query)
                    limit = int(query.get("receipts", ["50"])[0])
                    self._send_json(200, store.snapshot(receipt_limit=limit))
                    return
                if parsed.path == "/api/v1/diagnostics":
                    self._send_json(200, store.diagnose())
                    return
                if parsed.path.startswith("/api/v1/services/") and parsed.path.endswith("/logs"):
                    name = parsed.path.removeprefix("/api/v1/services/").removesuffix("/logs").strip("/")
                    self._send_json(200, services.logs(name))
                    return
                self._error(404, "unknown dashboard route")
            except (ValidationError, OSError, ValueError) as exc:
                self._error(400, str(exc))

        def do_PUT(self) -> None:  # noqa: N802
            if urlsplit(self.path).path != "/api/v1/operator/config":
                self._error(404, "unknown dashboard route")
                return
            try:
                expected = self.headers.get("If-Match")
                if not expected:
                    raise ValidationError("dashboard config writes require If-Match revision")
                result = store.write(self._body(), expected_revision=expected.strip('"'))
                self._send_json(200, result)
            except ValidationError as exc:
                status = 409 if "changed since" in str(exc) else 400
                self._error(status, str(exc))
            except OSError as exc:
                self._error(500, str(exc))

        def do_POST(self) -> None:  # noqa: N802
            parts = urlsplit(self.path).path.strip("/").split("/")
            if len(parts) != 5 or parts[:3] != ["api", "v1", "services"]:
                self._error(404, "unknown dashboard route")
                return
            _, _, _, name, action = parts
            operations = {
                "start": services.start,
                "stop": services.stop,
                "drain": services.drain,
                "restart": services.restart,
                "reset": services.reset,
                "install": services.install_persistent,
                "uninstall": services.uninstall_persistent,
            }
            operation = operations.get(action)
            if operation is None:
                self._error(404, "unknown service operation")
                return
            try:
                current_revision = store.read()[1]
                expected = self.headers.get("If-Match", "").strip('"')
                if expected != current_revision:
                    raise ValidationError("service operation requires the current profile revision")
                self._send_json(200, operation(name))
            except ValidationError as exc:
                self._error(409 if "revision" in str(exc) else 400, str(exc))
            except OSError as exc:
                self._error(500, str(exc))

    return Handler


def serve_dashboard(
    store: OperatorStore,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValidationError("dashboard host must be an IP address") from exc
    if not address.is_loopback:
        raise ValidationError("dashboard is loopback-only; remote operator access is unsupported")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValidationError("dashboard port must be within 1..65535")
    server = ThreadingHTTPServer((host, port), dashboard_handler(store))
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
