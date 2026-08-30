import os
import shutil
import tempfile
from pathlib import Path

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="vocal-score-tests-"))
os.environ["VSS_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["VSS_DATABASE_URL"] = f"sqlite:///{(TEST_DATA_DIR / 'tests.db').as_posix()}"
os.environ["VSS_WORKER_BACKEND"] = "thread"


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    del session, exitstatus
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
