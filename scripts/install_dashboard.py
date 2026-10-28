import json

from skill_store import install_dashboard_files, scan_skills


if __name__ == "__main__":
    destination = install_dashboard_files()
    result = scan_skills()
    result["dashboard"] = str(destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))
