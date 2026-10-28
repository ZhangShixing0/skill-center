from __future__ import annotations

import argparse
import json

from skill_store import load_project_roots, save_project_roots_and_scan


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure explicit project Skill roots for the local Skill Center.")
    parser.add_argument("--add", action="append", default=[], help="Project directory containing SKILL.md folders")
    parser.add_argument("--label", action="append", default=[], help="Optional label matching each --add argument")
    parser.add_argument(
        "--mode",
        action="append",
        default=[],
        choices=["skill-container", "single-skill"],
        help="Scan direct child Skills or treat the selected folder as one Skill",
    )
    parser.add_argument("--replace", action="store_true", help="Replace existing roots instead of appending")
    parser.add_argument("--list", action="store_true", help="List configured roots without writing or scanning")
    args = parser.parse_args()

    if args.list:
        print(json.dumps({"roots": load_project_roots(), "writes_performed": False}, ensure_ascii=False, indent=2))
        return

    roots = [] if args.replace else load_project_roots()
    for index, path in enumerate(args.add):
        label = args.label[index] if index < len(args.label) else ""
        mode = args.mode[index] if index < len(args.mode) else "skill-container"
        roots.append({"path": path, "label": label, "enabled": True, "mode": mode})
    result = save_project_roots_and_scan(roots)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
