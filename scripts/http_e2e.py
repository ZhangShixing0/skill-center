from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import serve_dashboard as server_module
import skill_store as store

SESSION_TOKEN = ""


def write_skill(folder: Path, name: str, description: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        f"# {name}\n\n## Workflow\n\n1. Inspect.\n2. Deliver.\n",
        encoding="utf-8",
    )


def request_json(
    base: str,
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if SESSION_TOKEN:
        headers["X-Skill-Center-Token"] = SESSION_TOKEN
    headers.update(extra_headers or {})
    request = Request(
        base + path,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    global SESSION_TOKEN
    originals = {
        "CODEX_HOME": store.CODEX_HOME,
        "CENTER_HOME": store.CENTER_HOME,
        "DB_PATH": store.DB_PATH,
        "LEGACY_DB_PATH": store.LEGACY_DB_PATH,
        "PROJECT_ROOTS_PATH": store.PROJECT_ROOTS_PATH,
        "SCAN_SOURCES_PATH": store.SCAN_SOURCES_PATH,
        "LOCAL_CATALOG_PATH": store.LOCAL_CATALOG_PATH,
        "CLASSIFICATION_HINTS_PATH": store.CLASSIFICATION_HINTS_PATH,
        "PUBLIC_SOURCES_PATH": store.PUBLIC_SOURCES_PATH,
        "PUBLIC_LOCALIZATIONS_PATH": store.PUBLIC_LOCALIZATIONS_PATH,
        "WORKFLOWS_PATH": store.WORKFLOWS_PATH,
        "LOCAL_WORKFLOWS_PATH": store.LOCAL_WORKFLOWS_PATH,
        "READ_ONLY_MODE": store.READ_ONLY_MODE,
        "SERVER_CENTER_HOME": server_module.CENTER_HOME,
    }
    with tempfile.TemporaryDirectory(prefix="skill-center-http-e2e-") as temp_name:
        root = Path(temp_name)
        codex_home = root / ".codex"
        center_home = root / "center"
        project_root = root / "project-skills"
        invocation_workspace = root / "workspaces" / "alpha-project"
        try:
            store.CODEX_HOME = codex_home
            store.CENTER_HOME = center_home
            store.LEGACY_DB_PATH = center_home / "data" / "skill-center.sqlite3"
            store.DB_PATH = center_home / "data" / "skill-center-v2.sqlite3"
            store.PROJECT_ROOTS_PATH = center_home / "data" / "project-roots.json"
            store.SCAN_SOURCES_PATH = center_home / "data" / "scan-sources.local.json"
            store.LOCAL_CATALOG_PATH = center_home / "data" / "personal-catalog.local.json"
            store.CLASSIFICATION_HINTS_PATH = (
                center_home / "data" / "classification-suggestions.local.json"
            )
            store.PUBLIC_SOURCES_PATH = root / "public-sources.json"
            store.PUBLIC_SOURCES_PATH.write_text('{"__verified_urls__": {}}\n', encoding="utf-8")
            store.PUBLIC_LOCALIZATIONS_PATH = root / "public-skills.zh-CN.json"
            store.WORKFLOWS_PATH = root / "workflows.json"
            store.LOCAL_WORKFLOWS_PATH = center_home / "data" / "workflows.local.json"
            store.WORKFLOWS_PATH.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "workflows": [
                            {
                                "id": "alpha-beta-flow",
                                "title": "Alpha Beta Flow",
                                "description": "HTTP workflow",
                                "best_for": "HTTP verification",
                                "steps": [
                                    {"skill": "alpha", "role": "First"},
                                    {"skill": "beta", "role": "Second"},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            store.READ_ONLY_MODE = False
            server_module.CENTER_HOME = center_home

            write_skill(codex_home / "skills" / "alpha", "alpha", "HTTP alpha")
            write_skill(project_root / "beta", "beta", "HTTP project beta")
            (invocation_workspace / ".git").mkdir(parents=True)
            store.save_project_roots([{"path": str(project_root), "label": "HTTP project", "enabled": True}])
            store.install_dashboard_files()
            initial_scan = store.scan_skills()
            require(initial_scan["added_count"] == 2, "initial scan should discover two locations")
            alpha_record = next(
                item for item in store.list_skills(scope="my")
                if item["name"] == "alpha"
            )
            store.PUBLIC_LOCALIZATIONS_PATH.write_text(
                json.dumps(
                    {
                        "__meta__": {
                            "default_review_status": "assistant-draft",
                        },
                        "skills": {
                            "alpha": {
                                "display_name": "阿尔法测试",
                                "description": "用于验证 HTTP 双语字段。",
                                "use_when": "需要检查中文搜索时。",
                                "source_hash": alpha_record["content_hash"],
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store.CLASSIFICATION_HINTS_PATH.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suggestions": {
                            "alpha": {
                                "classification": "self-authored",
                                "confidence": "high",
                                "evidence": ["HTTP local creation record"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            source_hashes = {
                path: store._content_hash(path)
                for path in (codex_home / "skills" / "alpha", project_root / "beta")
            }

            server = server_module.SkillCenterHTTPServer(
                ("127.0.0.1", 0),
                server_module.SkillCenterHandler,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                status, health = request_json(base, "/api/health")
                require(status == 200 and health["status"] == "ok", "health route failed")
                status, invalid_host = request_json(
                    base,
                    "/api/health",
                    extra_headers={"Host": "example.com"},
                )
                require(status == 421 and invalid_host["error"] == "invalid host", "invalid Host was accepted")

                status, unauthorized = request_json(base, "/api/scan", "POST", {})
                require(
                    status == 403 and unauthorized.get("code") == "write_not_authorized",
                    "unauthorized local write was accepted",
                )
                SESSION_TOKEN = server.session_token

                status, payload = request_json(base, "/api/skills?scope=my")
                require(status == 200 and len(payload["skills"]) == 2, "skills route failed")
                alpha = next(item for item in payload["skills"] if item["name"] == "alpha")
                status, owned = request_json(base, "/api/skills?scope=my&ownership=owned")
                require(
                    status == 200
                    and [item["name"] for item in owned["skills"]] == ["beta"],
                    "owned inventory should exclude an unclaimed personal install",
                )
                status, inbox = request_json(base, "/api/skills?scope=my&ownership=inbox")
                require(
                    status == 200
                    and [item["name"] for item in inbox["skills"]] == ["alpha"],
                    "ownership inbox did not isolate the unclaimed personal install",
                )
                require(alpha["display_name_zh"] == "阿尔法测试", "localized display name missing")
                require(alpha["description_original"] == "HTTP alpha", "original description missing")
                require(alpha["source_status"] == "missing", "missing source status failed")
                require(not alpha["localization_stale"], "current localization was marked stale")
                status, localized_search = request_json(
                    base,
                    "/api/skills?scope=my&q=%E4%B8%AD%E6%96%87%E6%90%9C%E7%B4%A2",
                )
                require(
                    status == 200
                    and any(item["name"] == "alpha" for item in localized_search["skills"]),
                    "localized API search failed",
                )
                status, workflows = request_json(base, "/api/workflows")
                require(
                    status == 200
                    and len(workflows["workflows"]) == 1
                    and workflows["workflows"][0]["ready"],
                    "workflow catalog route failed",
                )

                database_mtime = store.DB_PATH.stat().st_mtime_ns
                status, review = request_json(base, "/api/classification-review")
                require(status == 200 and not review["writes_performed"], "classification review failed")
                require(review["summary"]["total"] == 1, "classification review candidate count failed")
                require(review["candidates"][0]["name"] == "alpha", "classification suggestion missing")
                require(str(root) not in json.dumps(review), "classification review leaked a local path")
                require(store.DB_PATH.stat().st_mtime_ns == database_mtime, "classification review wrote to database")
                decisions = [
                    {
                        "skill_id": alpha["id"],
                        "classification": "self-authored",
                    }
                ]
                status, classification_preview = request_json(
                    base,
                    "/api/classifications/preview",
                    "POST",
                    {"decisions": decisions},
                )
                require(
                    status == 200 and not classification_preview["writes_performed"],
                    "classification preview failed",
                )
                require(store.DB_PATH.stat().st_mtime_ns == database_mtime, "classification preview wrote to database")
                status, classification_apply = request_json(
                    base,
                    "/api/classifications",
                    "POST",
                    {
                        "decisions": decisions,
                        "preview_token": classification_preview["preview_token"],
                    },
                )
                require(
                    status == 200 and classification_apply["applied_count"] == 1,
                    "classification batch apply failed",
                )
                status, stale_classification = request_json(
                    base,
                    "/api/classifications",
                    "POST",
                    {
                        "decisions": decisions,
                        "preview_token": classification_preview["preview_token"],
                    },
                )
                require(
                    status == 400 and stale_classification.get("error"),
                    "stale classification preview was accepted",
                )
                status, review_after = request_json(base, "/api/classification-review")
                require(status == 200 and review_after["summary"]["total"] == 0, "applied classification remained pending")

                database_mtime = store.DB_PATH.stat().st_mtime_ns
                status, sources = request_json(base, "/api/scan-sources")
                require(status == 200 and len(sources["sources"]) >= 5, "scan sources route failed")
                require(store.DB_PATH.stat().st_mtime_ns == database_mtime, "source overview wrote to the database")
                status, preview = request_json(
                    base,
                    "/api/scan-sources/preview",
                    "POST",
                    {"config": sources["config"]},
                )
                require(status == 200 and preview["valid"], "scan source preview failed")
                require(not preview["writes_performed"], "scan source preview reported a write")
                require(store.DB_PATH.stat().st_mtime_ns == database_mtime, "preview wrote to the database")
                status, missing_token = request_json(
                    base,
                    "/api/scan-sources",
                    "POST",
                    {"config": sources["config"]},
                )
                require(status == 400 and missing_token.get("error"), "unpreviewed config save was accepted")
                status, saved_sources = request_json(
                    base,
                    "/api/scan-sources",
                    "POST",
                    {
                        "config": sources["config"],
                        "preview_token": preview["preview_token"],
                        "scan": False,
                    },
                )
                require(status == 200 and saved_sources["writes_performed"], "scan source save failed")
                status, template = request_json(base, "/api/scan-sources/template")
                require(status == 200 and not template["contains_local_paths"], "shareable template boundary failed")
                require(str(root) not in json.dumps(template), "shareable template leaked a local path")

                status, scan = request_json(base, "/api/scan", "POST", {})
                require(status == 200, "scan route failed")
                require(
                    scan["added_count"] == scan["updated_count"] == scan["removed_count"] == 0,
                    "repeat scan should have no delta",
                )
                server.scan_lock.acquire()
                try:
                    status, busy = request_json(base, "/api/scan", "POST", {})
                finally:
                    server.scan_lock.release()
                require(
                    status == 409 and busy.get("code") == "scan_busy",
                    "concurrent scan was not rejected",
                )

                status, usage = request_json(
                    base,
                    "/api/usage",
                    "POST",
                    {
                        "skill": "alpha",
                        "invocation_type": "explicit",
                        "workspace_path": str(invocation_workspace),
                        "workspace_label": "Alpha Lab",
                        "workspace_kind": "project",
                        "task_category": "dashboard-review",
                        "run_id": "http-run-001",
                        "workflow_id": "alpha-beta-flow",
                        "step_position": 1,
                    },
                )
                require(status == 201 and usage["skill"] == "alpha", "usage route failed")
                require(usage["event_id"] > 0, "usage event id missing")
                require(usage["workspace"]["label"] == "Alpha Lab", "workspace alias missing")
                require(str(invocation_workspace) not in json.dumps(usage), "usage response leaked workspace path")
                status, beta_usage = request_json(
                    base,
                    "/api/usage",
                    "POST",
                    {
                        "skill": "beta",
                        "invocation_type": "implicit",
                        "workspace_path": str(invocation_workspace),
                        "workspace_label": "Alpha Lab",
                        "workspace_kind": "project",
                        "task_category": "dashboard-review",
                        "run_id": "http-run-001",
                        "workflow_id": "alpha-beta-flow",
                        "step_position": 2,
                        "step_outcome": "solved",
                    },
                )
                require(
                    status == 201 and beta_usage["run_id"] == "http-run-001",
                    "run-aware usage route failed",
                )

                status, feedback = request_json(
                    base,
                    "/api/feedback",
                    "POST",
                    {
                        "skill_id": alpha["id"],
                        "usage_event_id": usage["event_id"],
                        "outcome": "partial",
                        "rating": 4,
                        "issue_tags": ["missing-context"],
                        "note": "需要一个更具体的例子",
                    },
                )
                require(status == 201 and feedback["id"] > 0, "feedback route failed")
                require(feedback["usage_event_id"] == usage["event_id"], "feedback was not linked to usage")

                status, usage_events = request_json(
                    base,
                    f"/api/usage?skill_id={alpha['id']}&limit=10",
                )
                require(status == 200 and len(usage_events["events"]) == 1, "usage list route failed")
                recorded_event = usage_events["events"][0]
                require(recorded_event["workspace_label"] == "Alpha Lab", "usage list workspace alias missing")
                require(recorded_event["outcome"] == "partial", "usage list feedback state missing")
                require(str(invocation_workspace) not in json.dumps(usage_events), "usage list leaked workspace path")

                status, classification = request_json(
                    base,
                    "/api/classification",
                    "POST",
                    {"skill_id": alpha["id"], "classification": "self-authored"},
                )
                require(status == 200 and classification["classification"] == "self-authored", "classification route failed")

                status, proposal = request_json(
                    base,
                    "/api/proposals",
                    "POST",
                    {"skill_id": alpha["id"]},
                )
                require(status == 201 and proposal["status"] == "pending", "proposal route failed")

                status, roots = request_json(
                    base,
                    "/api/project-roots",
                    "POST",
                    {"roots": [{"path": str(project_root), "label": "HTTP project", "enabled": True}]},
                )
                require(status == 200 and roots["scan"]["scanned"] == 2, "project roots route failed")

                status, detail = request_json(base, "/api/skill?name=alpha")
                require(status == 200 and detail["skill"]["uses_all"] == 1, "detail usage aggregation failed")
                require(detail["skill"]["feedback_count"] == 1, "detail feedback aggregation failed")
                require(detail["skill"]["classification"] == "self-authored", "detail classification failed")
                require(len(detail["usage_events"]) == 1, "detail usage timeline missing")
                require(detail["usage_events"][0]["workspace_label"] == "Alpha Lab", "detail workspace alias missing")
                require(detail["usage_events"][0]["outcome"] == "partial", "detail feedback link missing")
                require(str(invocation_workspace) not in json.dumps(detail), "detail leaked workspace path")
                require(
                    detail["related_workflows"][0]["id"] == "alpha-beta-flow",
                    "detail workflow relationship missing",
                )

                status, summary = request_json(base, "/api/summary?scope=my")
                require(status == 200 and summary["uses_30"] == 2, "summary aggregation failed")
                require(summary["usage_tracking"]["coverage"] == "partial", "usage coverage disclosure missing")
                require(summary["latest_scan"] is not None, "latest scan history missing")
                status, insights = request_json(base, "/api/insights?scope=my")
                require(status == 200, "insights route failed")
                require(
                    insights["run_tracking"]["multi_skill_runs"] == 1
                    and insights["run_tracking"]["co_use"][0]["from_skill"] == "alpha"
                    and insights["run_tracking"]["co_use"][0]["to_skill"] == "beta",
                    "reliable co-use aggregation failed",
                )

                original_summary = server_module.summary
                server_module.summary = lambda scope="all": (_ for _ in ()).throw(
                    RuntimeError(str(root / "private-path"))
                )
                try:
                    status, internal = request_json(base, "/api/summary")
                finally:
                    server_module.summary = original_summary
                require(status == 500 and internal.get("code") == "internal_error", "internal error contract failed")
                require("detail" not in internal and str(root) not in json.dumps(internal), "internal path leaked")

                for path, before_hash in source_hashes.items():
                    require(store._content_hash(path) == before_hash, f"source Skill was modified: {path}")

                (codex_home / "skills" / "alpha" / "SKILL.md").unlink()
                (codex_home / "skills" / "alpha").rmdir()
                reconciliation = store.reconcile_missing_skills()
                require(reconciliation["removed_count"] == 1, "startup reconciliation missed uninstall")

                status, present_after_uninstall = request_json(
                    base, "/api/skills?scope=my&presence=present"
                )
                require(
                    status == 200
                    and all(item["name"] != "alpha" for item in present_after_uninstall["skills"]),
                    "uninstalled Skill remained in current inventory",
                )
                status, inbox_after_uninstall = request_json(
                    base, "/api/skills?scope=my&ownership=inbox"
                )
                require(
                    status == 200
                    and all(item["name"] != "alpha" for item in inbox_after_uninstall["skills"]),
                    "uninstalled Skill remained in ownership inbox",
                )
                status, removed = request_json(base, "/api/skills?presence=removed&sort=removed")
                removed_alpha = next(
                    (item for item in removed["skills"] if item["name"] == "alpha"),
                    None,
                )
                require(status == 200 and removed_alpha is not None, "removed history route missed uninstall")
                require(removed_alpha["removed_at"], "removed history has no removal time")
                require(
                    removed_alpha["last_workspace_label"] == "Alpha Lab",
                    "removed history lost the most recent project alias",
                )
                status, removed_detail = request_json(base, "/api/skill?name=alpha")
                require(status == 200, "removed Skill detail returned an error")
                require(not removed_detail["availability"]["file_available"], "removed detail claims file exists")
                require(not removed_detail["availability"]["can_execute"], "removed detail claims executable")
                require(not removed_detail["skill"]["is_present"], "removed detail claims current presence")
                require(removed_detail["skill"]["uses_all"] == 1, "removed detail lost usage history")
                require(len(removed_detail["versions"]) == 1, "removed detail lost observed version")

                status, summary_after_uninstall = request_json(base, "/api/summary?scope=my")
                require(status == 200, "summary failed after uninstall")
                require(summary_after_uninstall["inventory"]["removed"] == 1, "removed summary count failed")
                require(summary_after_uninstall["inventory"]["inbox"] == 0, "removed Skill inflated inbox count")
            finally:
                SESSION_TOKEN = ""
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
        finally:
            store.CODEX_HOME = originals["CODEX_HOME"]
            store.CENTER_HOME = originals["CENTER_HOME"]
            store.DB_PATH = originals["DB_PATH"]
            store.LEGACY_DB_PATH = originals["LEGACY_DB_PATH"]
            store.PROJECT_ROOTS_PATH = originals["PROJECT_ROOTS_PATH"]
            store.SCAN_SOURCES_PATH = originals["SCAN_SOURCES_PATH"]
            store.LOCAL_CATALOG_PATH = originals["LOCAL_CATALOG_PATH"]
            store.CLASSIFICATION_HINTS_PATH = originals["CLASSIFICATION_HINTS_PATH"]
            store.PUBLIC_SOURCES_PATH = originals["PUBLIC_SOURCES_PATH"]
            store.PUBLIC_LOCALIZATIONS_PATH = originals["PUBLIC_LOCALIZATIONS_PATH"]
            store.WORKFLOWS_PATH = originals["WORKFLOWS_PATH"]
            store.LOCAL_WORKFLOWS_PATH = originals["LOCAL_WORKFLOWS_PATH"]
            store.READ_ONLY_MODE = originals["READ_ONLY_MODE"]
            server_module.CENTER_HOME = originals["SERVER_CENTER_HOME"]

    print(json.dumps({
        "status": "pass",
        "routes": [
            "health",
            "skills",
            "workflows",
            "insights",
            "classification-review",
            "classification-preview",
            "classification-batch-apply",
            "scan",
            "usage",
            "usage-list",
            "feedback",
            "classification",
            "proposals",
            "project-roots",
            "scan-sources",
            "scan-sources-preview",
            "scan-sources-save",
            "scan-sources-template",
            "skill-detail",
            "removed-skill-detail",
            "presence-inventory",
            "ownership-inbox",
            "summary",
            "write-authorization",
            "scan-lock",
            "host-validation",
            "internal-error-privacy",
        ],
        "source_skill_files_modified": False,
        "database": "disposable temporary SQLite database",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
