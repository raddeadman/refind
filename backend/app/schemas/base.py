"""Base class for every request body (§5.3).

extra="forbid" turns an unknown field into a 422 instead of silently
dropping it, and Pydantic's strict types mean a field declared as a string
never accepts an object such as {"$gt": ""}, so operator injection cannot
reach a MongoDB filter.
"""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
