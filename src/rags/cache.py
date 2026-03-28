import json
import time
from pathlib import Path
from typing import Optional

CACHE_DIR = Path.home() / ".cache" / "rags-to-riches"
CACHE_FILE = CACHE_DIR / "stars.json"
TTL = 3600  # 1 hour


def load() -> tuple[Optional[list[dict]], Optional[float]]:
    if not CACHE_FILE.exists():
        return None, None
    data = json.loads(CACHE_FILE.read_text())
    return data["repos"], data["timestamp"]


def save(repos: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"repos": repos, "timestamp": time.time()}))


def is_stale(timestamp: float) -> bool:
    return time.time() - timestamp > TTL
