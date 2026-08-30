import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps" / "api"))
sys.path.insert(0, str(root / "workers" / "transcription"))

from app.main import app  # noqa: E402

target = root / "packages" / "contracts" / "openapi.json"
target.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(target)
