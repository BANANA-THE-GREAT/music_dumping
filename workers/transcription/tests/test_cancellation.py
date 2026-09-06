import sys
import time

import pytest
from vss_worker.cancellation import cancellation_scope
from vss_worker.command import CommandFailedError, run_command


def test_running_command_is_stopped_when_cancelled() -> None:
    started = time.monotonic()

    def check() -> None:
        if time.monotonic() - started > 0.3:
            raise InterruptedError("cancelled")

    with cancellation_scope(check), pytest.raises(InterruptedError):
        run_command([sys.executable, "-c", "import time; time.sleep(30)"])
    assert time.monotonic() - started < 5


def test_command_errors_are_reported_and_scope_is_reset() -> None:
    with pytest.raises(CommandFailedError, match="failure"):
        run_command([sys.executable, "-c", "import sys; sys.stderr.write('failure'); sys.exit(1)"])
    run_command([sys.executable, "-c", "pass"])
