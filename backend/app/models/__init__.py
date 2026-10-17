from .audit_log import AuditLog
from .category import Category
from .claim import Claim, ClaimAnswer, Handover
from .item import Attributes, Item, Location, StatusChange
from .item_secret import ItemSecret, VerificationQuestion
from .match import Match
from .notification import Notification
from .user import EmailVerification, Profile, User

# Registered with init_beanie() at start-up; indexes are created from each
# model's Settings so every member's database is identical (§4.2).
ALL_MODELS = [User, Category, Item, ItemSecret, Match, Claim, Notification, AuditLog]

__all__ = [
    "ALL_MODELS",
    "Attributes",
    "AuditLog",
    "Category",
    "Claim",
    "ClaimAnswer",
    "EmailVerification",
    "Handover",
    "Item",
    "ItemSecret",
    "Location",
    "Match",
    "Notification",
    "Profile",
    "StatusChange",
    "User",
    "VerificationQuestion",
]
