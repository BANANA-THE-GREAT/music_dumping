"""Run neural inference in an interruptible process owned by one job."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from vss_worker.basic_pitch_adapter import BasicPitchTranscriber


def main() -> None:
    source, target = map(Path, sys.argv[1:3])
    notes = BasicPitchTranscriber().transcribe(source)
    target.write_text(json.dumps([asdict(n) for n in notes]), encoding="utf-8")


if __name__ == "__main__":
    main()
