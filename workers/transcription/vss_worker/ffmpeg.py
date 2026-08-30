from collections.abc import Callable, Sequence
from pathlib import Path

from vss_worker.command import run_command

Runner = Callable[[Sequence[str]], None]


class FfmpegNormalizer:
    def __init__(self, executable: str = "ffmpeg", runner: Runner = run_command) -> None:
        self.executable = executable
        self.runner = runner

    def command(self, source: Path, destination: Path) -> list[str]:
        return [
            self.executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]

    def normalize(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.runner(self.command(source, destination))
        if not destination.exists():
            raise RuntimeError("FFmpeg completed without producing normalized audio")
        return destination
