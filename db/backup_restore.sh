#!/usr/bin/env bash
# Backup and restore drill (§5.5). Owner: Habib.
#
#   1. mongodump --gzip the refind database into backups/refind-<timestamp>.archive.gz
#   2. mongorestore it into refind_restore (--nsFrom/--nsTo, --drop), so the
#      live database is never touched
#   3. print the document count of every collection in both and fail if any differ
#   4. delete dumps older than RETENTION_DAYS (default 14)
#
# Connection: MONGO_BACKUP_URI from the environment or .env. On Atlas, create a
# database user "refindBackup" with read@refind and readWrite@refind_restore and
# use its connection string (mongodb+srv://refindBackup:<password>@<cluster>/).
# Without MONGO_BACKUP_URI the local docker-compose database is used with the
# refindBackup account created by scripts/setup_db.py.
#
# Tools: uses mongodump/mongorestore/mongosh if installed, otherwise runs them
# inside the refind-mongo container (local) or a throw-away mongo:7.0 container.
#
# Usage: db/backup_restore.sh            (from the repository root or anywhere)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # Only the variables this script needs; values may contain special characters.
  while IFS='=' read -r key value; do
    case "$key" in
      MONGO_BACKUP_URI|MONGO_BACKUP_PASSWORD|MONGO_DB) export "$key=${value%$'\r'}" ;;
    esac
  done < <(grep -E '^(MONGO_BACKUP_URI|MONGO_BACKUP_PASSWORD|MONGO_DB)=' .env || true)
fi

SOURCE_DB="${MONGO_DB:-refind}"
TARGET_DB="${SOURCE_DB}_restore"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${SOURCE_DB}-${STAMP}.archive.gz"
mkdir -p backups

if [[ -n "${MONGO_BACKUP_URI:-}" ]]; then
  URI="$MONGO_BACKUP_URI"
  WHERE="Atlas / MONGO_BACKUP_URI"
else
  URI="mongodb://refindBackup:${MONGO_BACKUP_PASSWORD:-change-me-backup}@localhost:27017/?authSource=admin&directConnection=true"
  WHERE="local docker-compose MongoDB"
fi

# run <tool> <args...>: the tool writes the archive to $DIR; fetch() then
# copies it into ./backups when the tool ran inside a container.
fetch() { :; }
if command -v mongodump >/dev/null && command -v mongorestore >/dev/null && command -v mongosh >/dev/null; then
  DIR="$ROOT/backups"
  run() { "$@"; }
elif [[ -z "${MONGO_BACKUP_URI:-}" ]] && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx refind-mongo; then
  DIR=/tmp/refind-backup
  run() { docker exec -i refind-mongo "$@"; }
  run mkdir -p "$DIR"
  fetch() { docker cp -q "refind-mongo:$DIR/$1" "backups/$1"; }
else
  DIR=/backups
  # Run as the current user so the container can write into ./backups.
  run() { docker run --rm -i --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT/backups:/backups" mongo:7.0 "$@"; }
fi

count_js() {
  cat <<JS
const names = db.getSiblingDB('$1').getCollectionNames().filter(n => !n.startsWith('system.')).sort();
for (const n of names) print(n + '\t' + db.getSiblingDB('$1').getCollection(n).countDocuments({}));
JS
}

echo "== ReFind backup and restore drill ($WHERE), $(date -u '+%Y-%m-%d %H:%M UTC')"
start=$SECONDS

echo "-- 1. mongodump --gzip --db $SOURCE_DB -> backups/$ARCHIVE"
run mongodump --uri="$URI" --db="$SOURCE_DB" --gzip --archive="$DIR/$ARCHIVE" --quiet
fetch "$ARCHIVE"
ls -lh "backups/$ARCHIVE" | awk '{print "   size:", $5}'

echo "-- 2. mongorestore into $TARGET_DB (--nsFrom '$SOURCE_DB.*' --nsTo '$TARGET_DB.*' --drop)"
run mongorestore --uri="$URI" --gzip --archive="$DIR/$ARCHIVE" --drop \
  --nsInclude="$SOURCE_DB.*" --nsFrom="$SOURCE_DB.*" --nsTo="$TARGET_DB.*" --quiet

echo "-- 3. document counts"
before="$(run mongosh "$URI" --quiet --eval "$(count_js "$SOURCE_DB")")"
after="$(run mongosh "$URI" --quiet --eval "$(count_js "$TARGET_DB")")"
mismatch=0
if [[ -z "$before" ]]; then
  echo "FAILED: $SOURCE_DB has no collections (wrong URI, missing permission, or not seeded)" >&2
  exit 1
fi
printf '   %-22s %10s %10s\n' collection "$SOURCE_DB" "$TARGET_DB"
while IFS=$'\t' read -r name n; do
  [[ -z "$name" ]] && continue
  m="$(awk -F'\t' -v c="$name" '$1 == c {print $2}' <<<"$after")"
  flag=""
  if [[ "$n" != "${m:-missing}" ]]; then flag="  <-- MISMATCH"; mismatch=1; fi
  printf '   %-22s %10s %10s%s\n' "$name" "$n" "${m:-missing}" "$flag"
done <<<"$before"

echo "-- 4. retention: delete dumps older than $RETENTION_DAYS days"
find backups -maxdepth 1 -name '*.archive.gz' -mtime +"$RETENTION_DAYS" -print -delete | sed 's/^/   deleted /'

[[ "$DIR" == /tmp/refind-backup ]] && run rm -f "$DIR/$ARCHIVE"
echo "== done in $((SECONDS - start)) s"
if (( mismatch )); then
  echo "FAILED: counts differ" >&2
  exit 1
fi
echo "OK: every collection has the same number of documents"
