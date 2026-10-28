from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from pathlib import Path

import skill_store as store
from skill_store import CODEX_HOME, IGNORED_PARTS, list_skills, promotion_preview, register_snapshot, scan_skills


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_PARTS or name in {".DS_Store", "Thumbs.db"}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote one approved project Skill as a global snapshot.")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--skill-id", help="Exact project Skill record id")
    selector.add_argument("--skill", help="Project Skill name; fails if more than one project source has that name")
    parser.add_argument("--apply", action="store_true", help="Perform the copy; default is dry-run")
    parser.add_argument("--approval-token", default="", help="Must equal APPROVED when --apply is used")
    parser.add_argument("--refresh", action="store_true", help="Refresh inventory before a dry-run (writes inventory metadata)")
    args = parser.parse_args()

    if args.apply and args.approval_token != "APPROVED":
        raise SystemExit("Refusing to write: --approval-token APPROVED is required")
    if args.apply or args.refresh:
        scan_skills()
    store.READ_ONLY_MODE = not (args.apply or args.refresh)
    try:
        skill_id = args.skill_id
        if args.skill:
            matches = [
                item for item in list_skills(scope="my", include_duplicates=True)
                if item["source_kind"] == "project" and item["name"].lower() == args.skill.lower()
            ]
            if not matches:
                raise SystemExit(f"Project Skill not found in the current inventory: {args.skill}")
            if len(matches) > 1:
                raise SystemExit(f"Multiple project sources are named {args.skill}; use --skill-id")
            skill_id = matches[0]["id"]
        plan = promotion_preview(skill_id)
    except FileNotFoundError as exc:
        raise SystemExit(f"No existing inventory for a dry-run: {exc}. Run scan_skills.py or rerun with --refresh after write approval.") from exc
    if not args.apply:
        plan["inventory_refresh_performed"] = args.refresh
        plan["skill_files_written"] = False
        plan["writes_performed"] = args.refresh
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    if plan["verdict"] not in {"ready", "already-identical"}:
        raise SystemExit(f"Refusing to write: promotion verdict is {plan['verdict']}")

    source = Path(plan["source"]).resolve()
    target = Path(plan["target"]).resolve()
    expected_parent = (CODEX_HOME / "skills").resolve()
    if target.parent != expected_parent:
        raise SystemExit("Refusing to write outside the global Skill root")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise SystemExit("Refusing to promote a Skill containing symbolic links")

    if plan["verdict"] == "ready":
        staging = target.parent / f".{target.name}.staging-{uuid.uuid4().hex[:8]}"
        shutil.copytree(source, staging, ignore=_ignore)
        if not (staging / "SKILL.md").is_file():
            shutil.rmtree(staging, ignore_errors=True)
            raise SystemExit("Staged snapshot has no SKILL.md")
        os.replace(staging, target)

    registered = register_snapshot(target, source, plan["source_hash"])
    print(json.dumps({"promotion": plan, "registered": registered, "writes_performed": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
