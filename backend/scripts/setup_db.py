"""One-time database set-up (§5.1, §5.3). Safe to run again.

1. As root: create/update the least-privilege accounts
     refindApp     readWrite on refind (+ refind_test)  -> used by the API
     refindAdmin   dbAdmin on refind (+ refind_test)    -> used only by step 2
     refindReports read on refind
     refindBackup  backup + restore (admin db)
2. As refindAdmin: create the eight collections and apply the $jsonSchema
   validators with collMod. The API account cannot change them.

Run from backend/:  python -m scripts.setup_db
"""

import sys

from pymongo import MongoClient
from pymongo.errors import OperationFailure

from app.config import get_settings
from app.db_validators import VALIDATORS


def upsert_user(db, name: str, password: str, roles: list) -> None:
    exists = db.command("usersInfo", name)["users"]
    command = "updateUser" if exists else "createUser"
    db.command(command, name, pwd=password, roles=roles, mechanisms=["SCRAM-SHA-256"])
    print(f"  {command[:6]}d {db.name}.{name}")


def create_accounts(settings) -> None:
    main, test = settings.mongo_db, settings.mongo_test_db
    accounts = settings.mongo_auth_db
    with MongoClient(settings.root_uri) as client:
        upsert_user(
            client[accounts],
            "refindApp",
            settings.mongo_app_password,
            [{"role": "readWrite", "db": main}, {"role": "readWrite", "db": test}],
        )
        upsert_user(
            client[accounts],
            "refindAdmin",
            settings.mongo_admin_password,
            [{"role": "dbAdmin", "db": main}, {"role": "dbAdmin", "db": test}],
        )
        upsert_user(client[accounts], "refindReports", settings.mongo_reports_password, [{"role": "read", "db": main}])
        upsert_user(
            client["admin"],
            "refindBackup",
            settings.mongo_backup_password,
            [{"role": "backup", "db": "admin"}, {"role": "restore", "db": "admin"}],
        )


def apply_validators(settings) -> None:
    with MongoClient(settings.admin_uri) as client:
        for db_name in (settings.mongo_db, settings.mongo_test_db):
            db = client[db_name]
            existing = set(db.list_collection_names())
            for name, schema in VALIDATORS.items():
                options = {
                    "validator": {"$jsonSchema": schema},
                    "validationLevel": "strict",
                    "validationAction": "error",
                }
                if name in existing:
                    db.command("collMod", name, **options)
                    print(f"  updated validator {db_name}.{name}")
                else:
                    db.create_collection(name, **options)
                    print(f"  created {db_name}.{name}")


def main() -> int:
    settings = get_settings()
    try:
        print("Creating database accounts (root)...")
        create_accounts(settings)
        print("Applying $jsonSchema validators (refindAdmin)...")
        apply_validators(settings)
    except OperationFailure as exc:
        print(f"MongoDB refused: {exc.details.get('errmsg', exc)}", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
