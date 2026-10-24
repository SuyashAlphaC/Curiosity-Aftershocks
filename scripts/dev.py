"""Start the local API and Vite together; Ctrl+C stops both process groups."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    processes = []
    exit_code = 0

    def interrupt(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        commands = [
            (["uv", "run", "uvicorn", "aftershocks.api:app", "--host", "127.0.0.1", "--port", "8000"], root),
            (["npm", "run", "dev"], root / "frontend"),
        ]
        for cmd, cwd in commands:
            processes.append(subprocess.Popen(cmd, cwd=cwd, start_new_session=True))
        print("Curiosity Aftershocks → http://127.0.0.1:5173", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        exit_code = next((p.returncode for p in processes if p.returncode is not None), 1) or 1
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
