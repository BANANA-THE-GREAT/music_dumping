import json
from pathlib import Path

from app.main import app

root = Path(__file__).resolve().parents[1]
target = root / "packages" / "contracts" / "openapi.json"
target.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(target)
