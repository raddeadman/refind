from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from .common import BCRYPT_PATTERN


class VerificationQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=200)
    # Normalised answer, hashed with bcrypt; never returned by the API.
    answerHash: str = Field(pattern=BCRYPT_PATTERN)


class ItemSecret(Document):
    """Kept apart from items so no item query can ever return secrets (§3).

    Read only by the verification service.
    """

    itemId: PydanticObjectId
    verification: list[VerificationQuestion] = Field(min_length=1, max_length=5)
    serialNumberHash: str | None = Field(default=None, pattern=BCRYPT_PATTERN)

    class Settings:
        name = "itemSecrets"
        indexes = [
            IndexModel([("itemId", ASCENDING)], unique=True, name="itemId_unique"),
        ]
