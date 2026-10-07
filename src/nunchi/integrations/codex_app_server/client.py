"""One `codex app-server` process, spoken to over its public JSON-RPC protocol.

The app-server reads and writes one JSON message per line on stdio
(``codex app-server --listen stdio://``). Three kinds of message come back:

- responses to our requests, matched by ``id``;
- notifications (``method``, no ``id``), handed to ``on_notification`` in
  order, on a thread of their own so a handler may make requests;
- requests from the server (``method`` and ``id``), such as approval requests,
  answered with whatever ``on_request`` returns.

``on_read`` sees each notification as it is read, before the response that
follows it is handed back: for bookkeeping that must keep the server's order.

Nothing here knows about rooms or turns; `integration.py` does.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
import itertools
import json
import os
import queue
import signal
import subprocess
import threading
from typing import Any

_DIAGNOSTIC_LINES = 40
_STOP_SECONDS = 5.0


class CodexAppServerError(RuntimeError):
    """The app-server failed, refused a request, or went away."""


class RequestRefused(CodexAppServerError):
    """The app-server answered a request with a JSON-RPC error."""

    def __init__(self, method: str, error: Mapping[str, Any]) -> None:
        self.code = error.get("code")
        self.message = str(error.get("message", "unknown error"))
        self.data = error.get("data")
        super().__init__(f"{method}: {self.message}")


class ServerRequestError(Exception):
    """Raised by ``on_request`` to answer a server request with an error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _Pending:
    def __init__(self, method: str) -> None:
        self.method = method
        self.done = threading.Event()
        self.result: Any = None
        self.error: Mapping[str, Any] | None = None
        self.exited: str | None = None


class AppServer:
    """A `codex app-server` child process and its JSON-RPC conversation."""

    def __init__(
        self,
        *,
        executable: str,
        environment: Mapping[str, str],
        working_directory: str,
        on_notification: Callable[[str, Mapping[str, Any]], None],
        on_request: Callable[[str, Mapping[str, Any]], Any],
        on_exit: Callable[[int | None], None] | None = None,
        on_read: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.executable = executable
        self.environment = dict(environment)
        self.working_directory = working_directory
        self.on_notification = on_notification
        self.on_request = on_request
        self.on_exit = on_exit
        self.on_read = on_read
        self.diagnostics: deque[str] = deque(maxlen=_DIAGNOSTIC_LINES)
        self._ids = itertools.count(1)
        self._pending: dict[int, _Pending] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._events: "queue.Queue[tuple[str, Mapping[str, Any]] | None]" = queue.Queue()
        self._exited = threading.Event()

    # -- lifecycle -----------------------------------------------------------------

    def command(self) -> list[str]:
        return [self.executable, "app-server", "--listen", "stdio://"]

    def start(self) -> None:
        try:
            process = subprocess.Popen(
                self.command(),
                cwd=self.working_directory,
                env=self.environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                # Its own process group: `codex` may be a launcher (npm's is a
                # Node script) whose app-server and MCP servers must end with it.
                start_new_session=True,
            )
        except OSError as exc:
            raise CodexAppServerError(f"codex app-server could not start: {exc}") from exc
        self._process = process
        threading.Thread(target=self._read_stdout, args=(process,), name="nunchi-codex-stdout", daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(process,), name="nunchi-codex-stderr", daemon=True).start()
        threading.Thread(target=self._dispatch_events, name="nunchi-codex-events", daemon=True).start()

    @property
    def alive(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None and not self._exited.is_set()

    def stop(self) -> None:
        """Close stdin, which ends the app-server; terminate it if it lingers."""

        process = self._process
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        if not self._exited.wait(_STOP_SECONDS):
            self._signal(signal.SIGTERM)
            if not self._exited.wait(_STOP_SECONDS):
                self._signal(signal.SIGKILL)
                self._exited.wait(_STOP_SECONDS)

    def kill(self) -> None:
        """End the app-server and everything it started, at once."""

        self._signal(signal.SIGKILL)

    def _signal(self, number: int) -> None:
        process = self._process
        if process is None:
            return
        try:
            os.killpg(process.pid, number)
        except (ProcessLookupError, PermissionError):
            pass

    def diagnostic_suffix(self) -> str:
        tail = " | ".join(list(self.diagnostics)[-3:])
        return f": {tail[-500:]}" if tail else ""

    # -- talking -------------------------------------------------------------------------

    def _write(self, message: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or not self.alive:
            raise CodexAppServerError("codex app-server is not running" + self.diagnostic_suffix())
        line = json.dumps(message, ensure_ascii=False) + "\n"
        with self._write_lock:
            try:
                process.stdin.write(line)
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise CodexAppServerError(f"codex app-server stopped reading: {exc}") from exc

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = dict(params)
        self._write(message)

    def request(self, method: str, params: Mapping[str, Any], *, timeout: float) -> Any:
        """Send one request and wait for its result; raise on an error or a timeout."""

        request_id = next(self._ids)
        pending = _Pending(method)
        with self._lock:
            self._pending[request_id] = pending
        try:
            self._write({"id": request_id, "method": method, "params": dict(params)})
            if not pending.done.wait(timeout):
                raise CodexAppServerError(f"{method}: no answer within {timeout:g} seconds")
        finally:
            with self._lock:
                self._pending.pop(request_id, None)
        if pending.exited is not None:
            raise CodexAppServerError(f"{method}: {pending.exited}")
        if pending.error is not None:
            raise RequestRefused(method, pending.error)
        return pending.result

    def _answer(self, request_id: Any, *, result: Any = None, error: Mapping[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"id": request_id}
        if error is not None:
            message["error"] = dict(error)
        else:
            message["result"] = result
        try:
            self._write(message)
        except CodexAppServerError:
            pass

    # -- reading -----------------------------------------------------------------------

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.diagnostics.append(line.strip()[:500])
                continue
            if not isinstance(message, dict):
                continue
            method = message.get("method")
            if isinstance(method, str) and "id" in message:
                self._serve_request(message["id"], method, message.get("params"))
            elif isinstance(method, str):
                params = message.get("params")
                params = params if isinstance(params, Mapping) else {}
                if self.on_read is not None:
                    try:
                        self.on_read(method, params)
                    except Exception:
                        pass
                self._events.put((method, params))
            elif "id" in message:
                with self._lock:
                    pending = self._pending.get(message["id"])
                if pending is not None:
                    error = message.get("error")
                    pending.error = error if isinstance(error, Mapping) else None
                    pending.result = message.get("result")
                    pending.done.set()
        process.wait()
        for stream in (process.stdin, process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        self._exited.set()
        with self._lock:
            pending_requests = list(self._pending.values())
        for pending in pending_requests:
            pending.exited = "codex app-server exited" + self.diagnostic_suffix()
            pending.done.set()
        # The exit is reported after every notification already read.
        self._events.put(("", {"returncode": process.returncode}))
        self._events.put(None)

    def _serve_request(self, request_id: Any, method: str, params: Any) -> None:
        try:
            result = self.on_request(method, params if isinstance(params, Mapping) else {})
        except ServerRequestError as exc:
            self._answer(request_id, error={"code": exc.code, "message": exc.message})
            return
        except Exception as exc:  # never leave the server waiting
            self._answer(request_id, error={"code": -32603, "message": f"{type(exc).__name__}: {exc}"})
            return
        self._answer(request_id, result=result)

    def _dispatch_events(self) -> None:
        while True:
            event = self._events.get()
            if event is None:
                return
            method, params = event
            if method == "":
                if self.on_exit is not None:
                    try:
                        self.on_exit(params.get("returncode"))
                    except Exception:
                        pass
                continue
            try:
                self.on_notification(method, params)
            except Exception as exc:  # a handler's bug must not stop the stream
                self.diagnostics.append(f"notification handler failed on {method}: {exc}"[:500])

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        assert process.stderr is not None
        for line in process.stderr:
            text = line.strip()
            if text:
                self.diagnostics.append(text[:500])
        process.stderr.close()
