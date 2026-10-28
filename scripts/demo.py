"""Run original sample skills in a temporary, isolated Skill Center."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use a port between 1024 and 65535.')
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', args.port))
        except OSError:
            parser.error('The demo port is already occupied. Choose another --port.')
    package = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='skill-center-demo-') as directory:
        root = Path(directory)
        shutil.copytree(package / 'examples' / 'skills', root / '.codex' / 'skills')
        environment = dict(os.environ)
        environment.update(CODEX_HOME=str(root / '.codex'), SKILL_CENTER_HOME=str(root / 'center'), PYTHONIOENCODING='utf-8')
        environment.pop('SKILL_PROJECT_ROOTS', None)
        command = [sys.executable, str(package / 'scripts' / 'serve_dashboard.py'), '--port', str(args.port)]
        if args.open:
            command.append('--open')
        print(f'Demo: 3 original sample skills only. Open http://127.0.0.1:{args.port}/my-skills.html', flush=True)
        print('Your installed skills are not scanned. Press Ctrl+C to stop.', flush=True)
        process = subprocess.Popen(command, env=environment)
        try:
            return process.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
