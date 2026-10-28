import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from skill_store import CENTER_HOME, CODEX_HOME, record_usage, scan_skills


def _record_via_server(payload: dict) -> dict:
    runtime_path = CENTER_HOME / "data" / "server-runtime.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    host = str(runtime.get("host", ""))
    port = int(runtime.get("port", 0))
    token = str(runtime.get("token", ""))
    parsed = urlparse(str(runtime.get("url", "")))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Skill Center runtime host is not loopback")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Skill Center runtime URL is not loopback")
    if port < 1 or port > 65535 or not token:
        raise ValueError("Skill Center runtime state is incomplete")
    request = Request(
        f"http://127.0.0.1:{port}/api/usage",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Skill-Center-Token": token,
        },
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    with urlopen(request, timeout=1.5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a privacy-preserving Codex skill invocation.")
    parser.add_argument("--skill", required=True, help="Skill frontmatter name")
    parser.add_argument("--invocation", choices=("explicit", "implicit"), required=True)
    parser.add_argument("--path", default="", help="Optional exact skill directory")
    parser.add_argument("--project-label", default="", help="Optional local-only workspace label")
    parser.add_argument(
        "--context-kind",
        choices=("project", "global", "temporary", "unknown"),
        default="",
        help="Optional workspace context override",
    )
    parser.add_argument("--category", default="", help="Optional task category override")
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional opaque task-run identifier shared by Skills in one workflow",
    )
    parser.add_argument(
        "--workflow",
        default="",
        help="Optional workflow template identifier",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=0,
        help="Optional 1-based position inside the workflow",
    )
    parser.add_argument(
        "--step-outcome",
        choices=("", "solved", "partial", "failed", "skipped"),
        default="",
        help="Optional result for this workflow step",
    )
    parser.add_argument(
        "--no-workspace",
        action="store_true",
        help="Record the invocation as a global task instead of detecting the current workspace",
    )
    args = parser.parse_args()
    workspace_path = str(CODEX_HOME if args.no_workspace else Path.cwd())
    payload = {
        "skill": args.skill,
        "invocation_type": args.invocation,
        "path": args.path,
        "workspace_path": workspace_path,
        "workspace_label": args.project_label,
        "workspace_kind": "global" if args.no_workspace else args.context_kind,
        "task_category": args.category,
        "run_id": args.run_id,
        "workflow_id": args.workflow,
        "step_position": args.step,
        "step_outcome": args.step_outcome,
    }
    try:
        result = _record_via_server(payload)
        result["write_route"] = "local-service"
    except (FileNotFoundError, ValueError, OSError, HTTPError, URLError, json.JSONDecodeError):
        try:
            result = record_usage(
                args.skill,
                args.invocation,
                args.path,
                workspace_path=workspace_path,
                workspace_label=args.project_label,
                workspace_kind="global" if args.no_workspace else args.context_kind,
                task_category=args.category,
                run_id=args.run_id,
                workflow_id=args.workflow,
                step_position=args.step,
                step_outcome=args.step_outcome,
            )
        except KeyError:
            scan_skills()
            result = record_usage(
                args.skill,
                args.invocation,
                args.path,
                workspace_path=workspace_path,
                workspace_label=args.project_label,
                workspace_kind="global" if args.no_workspace else args.context_kind,
                task_category=args.category,
                run_id=args.run_id,
                workflow_id=args.workflow,
                step_position=args.step,
                step_outcome=args.step_outcome,
            )
        result["write_route"] = "direct-database"
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
