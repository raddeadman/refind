"""$jsonSchema validators: the database-level safety net (§5.3).

Applied by scripts/setup_db.py as refindAdmin (collMod). The API account
(refindApp, readWrite) cannot change or remove them. These rules repeat the
most important Pydantic rules so that even a buggy raw update is rejected.
"""

from typing import Any

from .models.common import (
    APPROX_TIME_PATTERN,
    BCRYPT_PATTERN,
    BUILDINGS,
    CATEGORY_CODE_PATTERN,
    ClaimStatus,
    ItemStatus,
    ItemType,
    MatchStatus,
    NotificationType,
    Role,
    UserStatus,
)


def _enum(values) -> dict[str, Any]:
    return {"enum": [v.value if hasattr(v, "value") else v for v in values]}


def _nullable(bson_type: str, **extra: Any) -> dict[str, Any]:
    return {"bsonType": [bson_type, "null"], **extra}


OID = {"bsonType": "objectId"}
DATE = {"bsonType": "date"}
STRING = {"bsonType": "string"}

USERS = {
    "bsonType": "object",
    "required": ["name", "email", "role", "status", "createdAt"],
    "properties": {
        "name": {"bsonType": "string", "minLength": 1, "maxLength": 100},
        "email": {"bsonType": "string", "pattern": r"^[^@\s]+@[^@\s]+$"},
        # A plain-text password can never be stored (null = Google-only account).
        "passwordHash": _nullable("string", pattern=BCRYPT_PATTERN),
        "googleSub": _nullable("string"),
        "role": _enum(Role),
        "status": _enum(UserStatus),
        "studentId": _nullable("string"),
        "createdAt": DATE,
    },
}

ITEMS = {
    "bsonType": "object",
    "required": ["type", "title", "category", "location", "date", "timeSubmitted", "status", "reporterId", "version"],
    "properties": {
        "type": _enum(ItemType),
        "title": {"bsonType": "string", "minLength": 1, "maxLength": 100},
        "category": {"bsonType": "string", "pattern": CATEGORY_CODE_PATTERN},
        "location": {
            "bsonType": "object",
            "required": ["building"],
            "properties": {"building": _enum(BUILDINGS)},
        },
        "date": DATE,
        "approxTime": _nullable("string", pattern=APPROX_TIME_PATTERN),
        "timeSubmitted": DATE,
        "photoIds": {"bsonType": "array", "maxItems": 4, "items": OID},
        "status": _enum(ItemStatus),
        "reporterId": OID,
        "version": {"bsonType": ["int", "long"], "minimum": 1},
        "statusHistory": {
            "bsonType": "array",
            "items": {
                "bsonType": "object",
                "required": ["status", "at"],
                "properties": {"status": _enum(ItemStatus), "at": DATE},
            },
        },
    },
}

ITEM_SECRETS = {
    "bsonType": "object",
    "required": ["itemId", "verification"],
    "properties": {
        "itemId": OID,
        "verification": {
            "bsonType": "array",
            "minItems": 1,
            "items": {
                "bsonType": "object",
                "required": ["question", "answerHash"],
                "properties": {
                    "question": STRING,
                    "answerHash": {"bsonType": "string", "pattern": BCRYPT_PATTERN},
                },
            },
        },
        "serialNumberHash": _nullable("string", pattern=BCRYPT_PATTERN),
    },
}

MATCHES = {
    "bsonType": "object",
    "required": ["lostItemId", "foundItemId", "score", "status", "createdAt"],
    "properties": {
        "lostItemId": OID,
        "foundItemId": OID,
        "score": {"bsonType": ["int", "long", "double"], "minimum": 0, "maximum": 100},
        "reasons": {"bsonType": "array", "items": STRING},
        "status": _enum(MatchStatus),
        "createdAt": DATE,
    },
}

CLAIMS = {
    "bsonType": "object",
    "required": ["itemId", "claimantId", "status", "failedAttempts", "submittedAt"],
    "properties": {
        "itemId": OID,
        "claimantId": {"bsonType": "object"},  # DBRef (Beanie Link)
        "matchId": _nullable("objectId"),
        "status": _enum(ClaimStatus),
        "failedAttempts": {"bsonType": ["int", "long"], "minimum": 0},
        "submittedAt": DATE,
        "handover": {
            "bsonType": ["object", "null"],
            "required": ["at", "officerId", "idChecked", "idLast4"],
            "properties": {
                "at": DATE,
                "officerId": OID,
                "idChecked": {"bsonType": "bool"},
                "idLast4": {"bsonType": "string", "pattern": r"^\d{4}$"},
            },
        },
    },
}

NOTIFICATIONS = {
    "bsonType": "object",
    "required": ["userId", "type", "message", "dedupeKey", "createdAt"],
    "properties": {
        "userId": OID,
        "type": _enum(NotificationType),
        "message": STRING,
        "dedupeKey": STRING,
        "readAt": _nullable("date"),
        "createdAt": DATE,
    },
}

CATEGORIES = {
    "bsonType": "object",
    "required": ["code", "name"],
    "properties": {
        "code": {"bsonType": "string", "pattern": CATEGORY_CODE_PATTERN},
        "name": {"bsonType": "string", "minLength": 1},
        "defaultQuestions": {"bsonType": "array", "items": STRING},
    },
}

AUDIT_LOGS = {
    "bsonType": "object",
    "required": ["actorId", "action", "targetCollection", "timestamp"],
    "properties": {
        "actorId": _nullable("objectId"),
        "action": {"bsonType": "string", "minLength": 1},
        "targetCollection": STRING,
        "timestamp": DATE,
    },
}

VALIDATORS: dict[str, dict[str, Any]] = {
    "users": USERS,
    "items": ITEMS,
    "itemSecrets": ITEM_SECRETS,
    "matches": MATCHES,
    "claims": CLAIMS,
    "notifications": NOTIFICATIONS,
    "categories": CATEGORIES,
    "auditLogs": AUDIT_LOGS,
}
