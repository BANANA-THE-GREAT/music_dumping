import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="vocal-score-tests-"))
os.environ["VSS_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["VSS_DATABASE_URL"] = f"sqlite:///{(TEST_DATA_DIR / 'tests.db').as_posix()}"
os.environ["VSS_WORKER_BACKEND"] = "thread"


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection: object, record: object) -> None:
    del record
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    del session, exitstatus
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
