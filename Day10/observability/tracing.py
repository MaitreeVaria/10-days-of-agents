import time
from contextlib import contextmanager


TRACING_ON = True

def set_tracing(enabled: bool) -> None:
    global TRACING_ON
    TRACING_ON = bool(enabled)

@contextmanager
def trace_span(name: str, **attrs):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        if TRACING_ON:
            dt_ms = int((time.perf_counter() - t0) * 1000)
            # Minimal console tracing; can be swapped with OpenTelemetry later
            info = {"span": name, "latency_ms": dt_ms}
            if attrs:
                info.update(attrs)
            print(f"[trace] {info}")


