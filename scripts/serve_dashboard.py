from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import secrets
import threading
import webbrowser
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from skill_store import (
    CENTER_HOME,
    DB_PATH,
    add_feedback,
    apply_classifications,
    classification_review,
    create_proposal,
    get_skill_detail,
    insights,
    install_dashboard_files,
    list_feedback,
    load_project_roots,
    list_proposals,
    list_skills,
    list_usage_events,
    list_workflows,
    preview_scan_sources,
    preview_classifications,
    promotion_preview,
    record_usage,
    reconcile_missing_skills,
    save_project_roots_and_scan,
    save_scan_sources,
    save_scan_sources_and_scan,
    scan_skills,
    scan_sources_overview,
    set_classification,
    shareable_scan_sources_template,
    snapshot_diff,
    summary,
)

RUNTIME_STATE_PATH = CENTER_HOME / "data" / "server-runtime.json"
SESSION_COOKIE = "skill_center_session"


class ScanBusyError(RuntimeError):
    pass


class SkillCenterHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler]):
        super().__init__(server_address, handler)
        self.session_token = secrets.token_urlsafe(32)
        self.scan_lock = threading.Lock()


class SkillCenterHandler(BaseHTTPRequestHandler):
    server_version = "SkillCenter/2.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _loopback_request(self) -> bool:
        host = self.headers.get("Host", "")
        parsed = urlparse(f"//{host}")
        return parsed.hostname in {"127.0.0.1", "localhost", "::1"}

    def _write_authorized(self) -> bool:
        token = str(getattr(self.server, "session_token", ""))
        header_token = self.headers.get("X-Skill-Center-Token", "")
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        cookie_token = cookie.get(SESSION_COOKIE)
        supplied = header_token or (cookie_token.value if cookie_token else "")
        if not token or not supplied or not hmac.compare_digest(token, supplied):
            return False
        origin = self.headers.get("Origin", "")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                return False
            expected_port = int(getattr(self.server, "server_port", 0))
            if parsed.port not in {None, expected_port}:
                return False
        fetch_site = self.headers.get("Sec-Fetch-Site", "")
        return fetch_site in {"", "none", "same-origin", "same-site"}

    def _run_scan(self, callback):
        lock = getattr(self.server, "scan_lock", None)
        if lock is None or not lock.acquire(blocking=False):
            raise ScanBusyError("A Skill scan is already running. Wait for it to finish and retry.")
        try:
            return callback()
        finally:
            lock.release()

    def _internal_error(self, exc: Exception) -> None:
        print(f"[SkillCenter] internal error: {type(exc).__name__}")
        self._json(
            {
                "error": "Skill Center encountered an internal error.",
                "code": "internal_error",
                "recovery": "Run doctor, then retry the action.",
            },
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("request body too large")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "my-skills.html"
        target = (CENTER_HOME / relative).resolve()
        root = CENTER_HOME.resolve()
        if root not in target.parents and target != root:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if target.is_dir():
            target = target / "my-skills.html"
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") or content_type == "application/javascript" else content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN" if relative.startswith("showcases/") else "DENY")
        token = str(getattr(self.server, "session_token", ""))
        if token:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict",
            )
        is_showcase = relative.startswith("showcases/")
        frame_ancestors = "'self'" if is_showcase else "'none'"
        script_policy = "'self' 'unsafe-inline'" if is_showcase else "'self'"
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src {script_policy}; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-src 'self'; "
            f"base-uri 'none'; frame-ancestors {frame_ancestors}",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._loopback_request():
            self._json({"error": "invalid host"}, HTTPStatus.MISDIRECTED_REQUEST)
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/health":
                self._json({"status": "ok", "service": "Codex Skill Center"})
            elif parsed.path == "/api/summary":
                self._json(summary(query.get("scope", ["all"])[0]))
            elif parsed.path == "/api/skills":
                self._json(
                    {
                        "skills": list_skills(
                            scope=query.get("scope", ["all"])[0],
                            query=query.get("q", [""])[0],
                            classification=query.get("classification", [""])[0],
                            sort=query.get("sort", ["usage30"])[0],
                            category=query.get("category", [""])[0],
                            include_duplicates=query.get("include_duplicates", ["0"])[0] == "1",
                            presence=query.get("presence", ["present"])[0],
                            ownership=query.get("ownership", [""])[0],
                        )
                    }
                )
            elif parsed.path == "/api/insights":
                self._json(insights(query.get("scope", ["my"])[0]))
            elif parsed.path == "/api/workflows":
                self._json(
                    {
                        "workflows": list_workflows(
                            query.get("skill", [""])[0]
                        )
                    }
                )
            elif parsed.path == "/api/skill":
                self._json(
                    get_skill_detail(
                        skill_id=query.get("id", [""])[0],
                        name=query.get("name", [""])[0],
                    )
                )
            elif parsed.path == "/api/project-roots":
                self._json({"roots": load_project_roots()})
            elif parsed.path == "/api/classification-review":
                self._json(classification_review())
            elif parsed.path == "/api/scan-sources":
                self._json(scan_sources_overview())
            elif parsed.path == "/api/scan-sources/template":
                self._json(shareable_scan_sources_template())
            elif parsed.path == "/api/promotion-preview":
                self._json(promotion_preview(query.get("skill_id", [""])[0]))
            elif parsed.path == "/api/snapshot-diff":
                self._json(snapshot_diff(query.get("skill_id", [""])[0]))
            elif parsed.path == "/api/feedback":
                self._json({"feedback": list_feedback(query.get("skill_id", [""])[0])})
            elif parsed.path == "/api/usage":
                self._json(
                    {
                        "events": list_usage_events(
                            skill_id=query.get("skill_id", [""])[0],
                            workspace_id=query.get("workspace_id", [""])[0],
                            limit=int(query.get("limit", ["30"])[0]),
                        )
                    }
                )
            elif parsed.path == "/api/proposals":
                self._json({"proposals": list_proposals(query.get("scope", ["all"])[0])})
            elif parsed.path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            else:
                self._serve_static(parsed.path)
        except (ValueError, KeyError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._internal_error(exc)

    def do_POST(self) -> None:
        if not self._loopback_request():
            self._json({"error": "invalid host"}, HTTPStatus.MISDIRECTED_REQUEST)
            return
        if not self._write_authorized():
            self._json(
                {
                    "error": "This write request is not authorized for the local session.",
                    "code": "write_not_authorized",
                    "recovery": "Reload the Skill Center page and try again.",
                },
                HTTPStatus.FORBIDDEN,
            )
            return
        parsed = urlparse(self.path)
        try:
            payload = self._body()
            if parsed.path == "/api/scan":
                self._json(self._run_scan(scan_skills))
            elif parsed.path == "/api/usage":
                self._json(
                    record_usage(
                        payload.get("skill", ""),
                        payload.get("invocation_type", "implicit"),
                        payload.get("path", ""),
                        payload.get("workspace_path", ""),
                        payload.get("workspace_label", ""),
                        payload.get("workspace_kind", ""),
                        payload.get("task_category", ""),
                        payload.get("run_id", ""),
                        payload.get("workflow_id", ""),
                        int(payload.get("step_position", 0)),
                        payload.get("step_outcome", ""),
                    ),
                    HTTPStatus.CREATED,
                )
            elif parsed.path == "/api/feedback":
                self._json(
                    add_feedback(
                        payload.get("skill_id", ""),
                        payload.get("outcome", ""),
                        int(payload.get("rating", 0)),
                        payload.get("issue_tags", []),
                        payload.get("note", ""),
                        int(payload.get("usage_event_id", 0)),
                    ),
                    HTTPStatus.CREATED,
                )
            elif parsed.path == "/api/classification":
                self._json(
                    set_classification(
                        payload.get("skill_id", ""),
                        payload.get("classification", ""),
                        payload.get("upstream_source", ""),
                        payload.get("upstream_author", ""),
                    )
                )
            elif parsed.path == "/api/classifications/preview":
                self._json(
                    preview_classifications(payload.get("decisions", []))
                )
            elif parsed.path == "/api/classifications":
                self._json(
                    apply_classifications(
                        payload.get("decisions", []),
                        str(payload.get("preview_token", "")),
                    )
                )
            elif parsed.path == "/api/project-roots":
                self._json(
                    self._run_scan(
                        lambda: save_project_roots_and_scan(payload.get("roots", []))
                    )
                )
            elif parsed.path == "/api/scan-sources/preview":
                self._json(preview_scan_sources(payload.get("config", payload)))
            elif parsed.path == "/api/scan-sources":
                if payload.get("scan"):
                    result = self._run_scan(
                        lambda: save_scan_sources_and_scan(
                            payload.get("config", payload),
                            preview_token=str(payload.get("preview_token", "")),
                            require_preview=True,
                        )
                    )
                else:
                    result = save_scan_sources(
                        payload.get("config", payload),
                        preview_token=str(payload.get("preview_token", "")),
                        require_preview=True,
                    )
                self._json(result)
            elif parsed.path == "/api/proposals":
                self._json(create_proposal(payload.get("skill_id", "")), HTTPStatus.CREATED)
            elif parsed.path == "/api/shutdown":
                self._json({"status": "stopping"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except ScanBusyError as exc:
            self._json(
                {"error": str(exc), "code": "scan_busy", "recovery": "Retry after the active scan finishes."},
                HTTPStatus.CONFLICT,
            )
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._internal_error(exc)


def _write_runtime_state(server: SkillCenterHTTPServer, url: str) -> None:
    RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RUNTIME_STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": server.server_port,
                "url": url,
                "token": server.session_token,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(RUNTIME_STATE_PATH)


def _remove_runtime_state() -> None:
    try:
        data = json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if data.get("pid") == os.getpid():
        try:
            RUNTIME_STATE_PATH.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local Codex Skill Center dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--open", action="store_true", help="Open the dashboard in the default browser")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("For safety, Skill Center only binds to a loopback address.")
    install_dashboard_files()
    if not DB_PATH.is_file():
        scan_skills()
    else:
        reconcile_missing_skills()
    server = SkillCenterHTTPServer((args.host, args.port), SkillCenterHandler)
    url = f"http://127.0.0.1:{args.port}/my-skills.html"
    _write_runtime_state(server, url)
    print(f"Codex Skill Center: {url}")
    print("Press Ctrl+C to stop.")
    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _remove_runtime_state()


if __name__ == "__main__":
    main()
