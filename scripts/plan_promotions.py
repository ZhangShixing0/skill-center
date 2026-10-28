from __future__ import annotations

import argparse
import json

import skill_store as store
from skill_store import list_skills, promotion_preview, scan_skills


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a read-only global snapshot promotion plan for project Skills.")
    parser.add_argument("--skill", action="append", default=[], help="Project Skill name; repeat for multiple Skills")
    parser.add_argument("--refresh", action="store_true", help="Refresh the SQLite inventory before planning (writes inventory metadata)")
    args = parser.parse_args()

    if args.refresh:
        scan_skills()
    store.READ_ONLY_MODE = not args.refresh
    try:
        project_skills = [item for item in list_skills(scope="my", include_duplicates=True) if item["source_kind"] == "project"]
    except FileNotFoundError as exc:
        raise SystemExit(f"No existing inventory for a read-only plan: {exc}. Run scan_skills.py or rerun with --refresh after write approval.") from exc
    requested = {name.lower() for name in args.skill}
    selected = [item for item in project_skills if not requested or item["name"].lower() in requested]
    plans = [promotion_preview(item["id"]) for item in selected]
    print(
        json.dumps(
            {
                "plans": plans,
                "inventory_refresh_performed": args.refresh,
                "skill_files_written": False,
                "writes_performed": args.refresh,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
