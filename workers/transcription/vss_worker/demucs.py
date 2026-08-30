import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from vss_worker.command import run_command

Runner = Callable[[Sequence[str]], None]


class DemucsSeparator:
    def __init__(self, model: str = "htdemucs", runner: Runner = run_command) -> None:
        self.model = model
        self.runner = runner

    def command(self, source: Path, output_dir: Path) -> list[str]:
        return [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems",
            "vocals",
            "-n",
            self.model,
            "-o",
            str(output_dir),
            str(source),
        ]

    def separate(self, source: Path, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.runner(self.command(source, output_dir))
        vocal = output_dir / self.model / source.stem / "vocals.wav"
        if not vocal.exists():
            raise RuntimeError("Demucs completed without producing vocals.wav")
        return vocal
