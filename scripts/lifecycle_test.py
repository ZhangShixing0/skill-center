from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


SCRIPT = Path(__file__).resolve().parent / "skill_center.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def run(command: list[str], env: dict[str, str], expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *command],
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"{' '.join(command)} returned {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="skill-center-lifecycle-") as temp_name:
        root = Path(temp_name)
        codex_home = root / ".codex"
        center_home = root / "center"
        skill = codex_home / "skills" / "alpha"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Lifecycle test\n---\n\n# Alpha\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["CODEX_HOME"] = str(codex_home)
        env["SKILL_CENTER_HOME"] = str(center_home)
        env["PYTHONIOENCODING"] = "utf-8"
        port = free_port()

        doctor = run(["doctor", "--port", str(port), "--json"], env)
        report = json.loads(doctor.stdout)
        if report["status"] != "pass":
            raise AssertionError(report)

        run(["start", "--port", str(port), "--timeout", "10"], env)
        status = run(["status", "--json"], env)
        payload = json.loads(status.stdout)
        if not payload["running"] or payload["port"] != port:
            raise AssertionError(payload)

        with urlopen(f"http://127.0.0.1:{port}/my-skills.html", timeout=3) as response:
            if response.status != 200:
                raise AssertionError(f"dashboard returned {response.status}")
            cookie = response.headers.get("Set-Cookie", "")
            if "skill_center_session=" not in cookie or "SameSite=Strict" not in cookie:
                raise AssertionError("local session cookie was not issued")

        run(["stop", "--timeout", "5"], env)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.2)
            except (OSError, URLError):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("service still responded after stop")

        if (center_home / "data" / "server-runtime.json").exists():
            raise AssertionError("runtime state remained after stop")

    print(
        json.dumps(
            {
                "status": "pass",
                "commands": ["doctor", "start", "status", "stop"],
                "background_service": True,
                "session_cookie": "verified",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
