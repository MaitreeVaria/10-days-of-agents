import time, random
from typing import Callable

class TransientError(Exception):
    """Operation can be retried (network / 429 / 5xx)."""

def backoff_retry(
    fn: Callable[[], dict],
    max_attempts: int = 4,
    base: float = 0.5,
    factor: float = 2.0,
    jitter: float = 0.25
) -> dict:
    attempt = 1
    last_err: Exception | None = None
    while attempt <= max_attempts:
        try:
            return fn()
        except TransientError as e:
            last_err = e
        except Exception as e:
            msg = str(e).lower()
            if any(s in msg for s in ["timed out", "timeout", "connection", "429", "rate limit", " 5"]):
                last_err = e
            else:
                raise
        # sleep before retry
        sleep = base * (factor ** (attempt - 1)) + random.uniform(0, jitter)
        time.sleep(sleep)
        attempt += 1
    raise last_err or Exception("exhausted retries")
