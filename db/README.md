# Progress Report 1: mock data and query scripts

Run these after `docker compose up -d`, `python -m scripts.setup_db` and `python -m scripts.seed --reset` (see the main README).

```bash
URI="mongodb://refindApp:<MONGO_APP_PASSWORD>@localhost:27017/refind?authSource=refind&directConnection=true"

mongosh "$URI" db/crud_demo.js        # insert / find / update ($set $push $inc $addToSet) / delete, plus rejected writes
mongosh "$URI" db/explain_indexes.js  # explain("executionStats"): forced COLLSCAN vs index, per key query
mongosh "$URI" db/warehouse_fact.js   # monthly fact table (month x category x building x type) and return rate
```

| File | Contents |
| --- | --- |
| `mock/<collection>.json` | All seeded documents as Extended JSON arrays (`python -m scripts.export_mock` regenerates them) |
| `import_mock.sh` | Loads `mock/*.json` into an empty database with `mongoimport` |
| `crud_demo.js` | CRUD demonstration; tags and deletes its own documents, so it can be re-run |
| `explain_indexes.js` | Index evidence; no index is dropped (the "before" run uses `hint({ $natural: 1 })`) |
| `warehouse_fact.js` | Read-only aggregation; uncomment `$merge` to materialise `refind_dw.factItemsMonthly` |
| `*_output.txt` | Output of the three scripts on the seed data |

## Backup and restore (§5.5)

```bash
db/backup_restore.sh
```

Dumps `refind` with `mongodump --gzip` into `backups/` (git-ignored), restores it into `refind_restore` with `--nsFrom/--nsTo` (the live database is never touched), prints the document count of every collection in both and fails if any differ, then deletes dumps older than 14 days (`RETENTION_DAYS`).

- **Atlas:** create a database user `refindBackup` with `read` on `refind` and `readWrite` on `refind_restore` (Database Access → Add New Database User → Specific Privileges), then set `MONGO_BACKUP_URI=mongodb+srv://refindBackup:<password>@<cluster>/` in `.env`.
- **Local:** without `MONGO_BACKUP_URI` the script uses the docker-compose database and the `refindBackup` account from `scripts/setup_db.py`.
- No MongoDB tools installed? The script runs them in the `refind-mongo` container, or in a temporary `mongo:7.0` container for Atlas.

Output of the drill on the seed data: `docs/evidence/backup_restore_output.txt`.
