import hmac
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException

from .config import get_settings


def require_admin(x_admin_token: str = Header(default="")) -> None:
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN is not configured")
    if not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin token")


class RateLimiter:
    """Sliding-window limiter held in process memory (fine for a single API container)."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 20_000:
            self._prune(now)
        return True

    def _prune(self, now: float) -> None:
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window]:
            del self._hits[key]
