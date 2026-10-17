from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from .common import CATEGORY_CODE_PATTERN


class Category(Document):
    # Items store the code, so it never changes; only the name is editable.
    code: str = Field(pattern=CATEGORY_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    defaultQuestions: list[str] = Field(default_factory=list, max_length=10)

    class Settings:
        name = "categories"
        indexes = [
            IndexModel([("code", ASCENDING)], unique=True, name="code_unique"),
        ]
