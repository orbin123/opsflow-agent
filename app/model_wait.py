"""Wait only for an explicitly rate-limited model request during agent execution."""

from contextlib import contextmanager
from contextvars import ContextVar
from math import ceil, isfinite
from time import perf_counter, sleep

from groq import RateLimitError

from app.execution_events import start_step, finish_step


_deadline: ContextVar[float | None] = ContextVar("model_wait_deadline", default=None)


@contextmanager
def rate_limit_wait(deadline: float):
    token = _deadline.set(deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def invoke_model(model, messages):
    """Retry one rejected request, never a tool or turn; SDK retries stay disabled."""
    try:
        return model.invoke(messages)
    except RateLimitError as error:
        deadline = _deadline.get()
        if deadline is None:
            raise
        try:
            delay = float(error.response.headers["retry-after"])
        except (KeyError, ValueError):
            raise error
        if not isfinite(delay) or delay < 0:
            raise
        # Round up and allow a second for provider clock/reset rounding.
        delay = ceil(delay) + 1
        if delay > 60 or perf_counter() + delay >= deadline:
            raise
        started = perf_counter()
        step = start_step(f"Model busy — waiting {delay} seconds", kind="model")
        sleep(delay)
        finish_step(step, {"status": "completed", "reason": "rate_limit",
                           "elapsed_ms": (perf_counter() - started) * 1000})
        if perf_counter() >= deadline:
            raise
        # A second rejection is reported accurately through existing failure handling.
        return model.invoke(messages)
