import subprocess
from collections.abc import Sequence


class CommandFailedError(RuntimeError):
    pass


def run_command(arguments: Sequence[str]) -> None:
    try:
        subprocess.run(list(arguments), check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise CommandFailedError(f"Executable not found: {arguments[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip()[-2000:] if error.stderr else str(error)
        raise CommandFailedError(detail) from error
