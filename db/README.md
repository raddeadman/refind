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
