from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_check: ContextVar[Callable[[], None]] = ContextVar("cancel_check", default=lambda: None)


def check_cancelled() -> None:
    _check.get()()


@contextmanager
def cancellation_scope(check: Callable[[], None]) -> Iterator[None]:
    token = _check.set(check)
    try:
        check()
        yield
    finally:
        _check.reset(token)
