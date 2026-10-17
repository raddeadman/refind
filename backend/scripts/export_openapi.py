"""Write FastAPI's OpenAPI schema to frontend/openapi.json for Orval.

No database needed. Run from backend/:  python -m scripts.export_openapi
(The frontend's `npm run api` calls this, then Orval.)
"""

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"Wrote {OUT}")
