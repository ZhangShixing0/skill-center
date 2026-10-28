import json

from skill_store import scan_skills


if __name__ == "__main__":
    print(json.dumps(scan_skills(), ensure_ascii=False, indent=2))
