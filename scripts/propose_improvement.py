import argparse
import json

from skill_store import connect, create_proposal, scan_skills


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an approval-gated skill improvement proposal.")
    parser.add_argument("--skill", required=True, help="Skill name")
    args = parser.parse_args()
    with connect() as connection:
        row = connection.execute(
            "SELECT id FROM skills WHERE lower(name)=lower(?) AND is_present=1 LIMIT 1", (args.skill,)
        ).fetchone()
    if row is None:
        scan_skills()
        with connect() as connection:
            row = connection.execute(
                "SELECT id FROM skills WHERE lower(name)=lower(?) AND is_present=1 LIMIT 1", (args.skill,)
            ).fetchone()
    if row is None:
        raise SystemExit(f"Skill not found: {args.skill}")
    print(json.dumps(create_proposal(row["id"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
