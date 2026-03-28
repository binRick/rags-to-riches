import os
import subprocess
from typing import Callable, Optional

import requests

GITHUB_API = "https://api.github.com"


def get_token() -> Optional[str]:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def fetch_starred(token: str, on_page: Optional[Callable[[int, int], None]] = None) -> list[dict]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }

    repos = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}/user/starred",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        if on_page:
            on_page(page, len(repos))
        if len(data) < 100:
            break
        page += 1

    return repos
