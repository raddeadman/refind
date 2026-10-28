#!/usr/bin/env bash
# Load db/mock/*.json into a database with mongoimport (PR1 mock data).
#
#   db/import_mock.sh "mongodb://refindApp:<password>@localhost:27017/?authSource=refind&directConnection=true" refind
#
# Run scripts/setup_db.py first so the collections exist with their
# $jsonSchema validators; --drop is not used because dropping a collection
# removes its validator. The target collections should be empty.
set -euo pipefail

uri="${1:?usage: import_mock.sh <mongodb-uri> [database]}"
database="${2:-refind}"
dir="$(cd "$(dirname "$0")/mock" && pwd)"

for file in "$dir"/*.json; do
  collection="$(basename "$file" .json)"
  mongoimport --uri "$uri" --db "$database" --collection "$collection" --jsonArray --file "$file"
done
