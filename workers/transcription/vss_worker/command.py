import os
import signal
import subprocess
from collections.abc import Sequence

from vss_worker.cancellation import check_cancelled


class CommandFailedError(RuntimeError):
    pass


def run_command(arguments: Sequence[str]) -> None:
    check_cancelled()
    try:
        with subprocess.Popen(
            list(arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name != "nt",
        ) as process:
            try:
                while True:
                    check_cancelled()
                    try:
                        _, stderr = process.communicate(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                check_cancelled()
                if process.returncode:
                    raise CommandFailedError(stderr.strip()[-2000:])
            except BaseException:
                if process.poll() is None:
                    if os.name == "nt":
                        process.terminate()
                    else:
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        if os.name == "nt":
                            process.kill()
                        else:
                            os.killpg(process.pid, signal.SIGKILL)
                        process.communicate()
                raise
    except FileNotFoundError as error:
        raise CommandFailedError(f"Executable not found: {arguments[0]}") from error
