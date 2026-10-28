"""Export the seeded collections as Extended JSON files (PR1 mock data).

Writes ../db/mock/<collection>.json, one JSON array per collection, in
relaxed Extended JSON so ObjectId, Date and DBRef values survive the trip.
Load them into an empty database with ../db/import_mock.sh or Compass
(Add Data > Import JSON).

Run from backend/ after seeding:  python -m scripts.export_mock [--db refind]
"""

import argparse
from pathlib import Path

from bson.json_util import JSONOptions, JSONMode, dumps
from pymongo import MongoClient

from app.config import get_settings
from app.db_validators import VALIDATORS

OUT_DIR = Path(__file__).resolve().parents[2] / "db" / "mock"
RELAXED = JSONOptions(json_mode=JSONMode.RELAXED, tz_aware=True)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=settings.mongo_db)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with MongoClient(settings.app_uri) as client:
        db = client[args.db]
        for name in VALIDATORS:
            docs = list(db[name].find().sort("_id", 1))
            (OUT_DIR / f"{name}.json").write_text(dumps(docs, json_options=RELAXED, indent=2) + "\n")
            print(f"  {name}: {len(docs)} documents")
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
