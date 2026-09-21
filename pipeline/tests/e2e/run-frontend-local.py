"""Hold one disposable synthetic API for the frontend real-backend E2E."""
from __future__ import annotations

import os
import sys

from fixture import E2EEnvironment


def main() -> int:
    env = E2EEnvironment().start()
    try:
        env.seed_official_scenario()
        url = f"http://127.0.0.1:{env.api_port}"
        print(f"UEC_E2E_API_URL={url}", flush=True)
        print(f"UEC_E2E_PROJECT={env.project}", flush=True)
        print("Synthetic backend is ready; press Enter to stop it.", flush=True)
        sys.stdin.readline()
        return 0
    finally:
        env.stop()


if __name__ == "__main__":
    os.environ.setdefault("UEC_RUN_E2E", "1")
    raise SystemExit(main())
