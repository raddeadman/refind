"""Seed data with insert_many (§4.1): 15 categories, 150 users, 600 items,
plus matches, claims, notifications and audit entries (scripts/seed_activity.py).

Every found item is inserted together with its itemSecrets document, and all
the activity that refers to it, in one transaction. Data is random but reproducible (fixed random seed).

Run from backend/:  python -m scripts.seed [--db refind_test] [--reset]
All seeded accounts use the password printed at the end.
"""

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta

from beanie import PydanticObjectId

from app import db
from app.config import get_settings
from app.models import (
    ALL_MODELS,
    Attributes,
    AuditLog,
    Category,
    Claim,
    Item,
    ItemSecret,
    Location,
    Match,
    Notification,
    StatusChange,
    User,
    VerificationQuestion,
)
from app.models.common import BUILDINGS, ItemStatus, ItemType, Role, UserStatus
from app.security import hash_password, normalise_answer

from .seed_activity import make_activity

SEED_PASSWORD = "Password123!"
N_USERS = 150
N_OFFICERS = 4
N_ITEMS = 600

COLORS = ["black", "white", "blue", "red", "green", "grey", "brown", "silver", "pink", "yellow"]
FIRST_NAMES = [
    "Ahmed", "Fatima", "Mohammed", "Maryam", "Ali", "Noor", "Hassan", "Zainab", "Omar", "Sara",
    "Yousif", "Aisha", "Khalid", "Layla", "Hamad", "Huda", "Abdulla", "Reem", "Salman", "Dana",
]
LAST_NAMES = ["Al Khalifa", "Ahmed", "Hasan", "Ebrahim", "Saleh", "Mansoor", "Jaffar", "Yousif", "Isa", "Rashid"]
FLOORS = ["Ground floor", "First floor", "Second floor", "Third floor"]
AREAS = ["Main entrance", "Corridor", "Lecture hall", "Study area", "Restrooms", "Lab", "Cafeteria seating", "Lobby"]
DETAILS = [
    "On a bench near the entrance",
    "Under a desk in the back row",
    "Next to the vending machine",
    "On the table by the window",
    "Near the elevator",
    "Left on a chair in the cafeteria",
    "On the floor beside the stairs",
    "In the corridor near the printer",
]

# code -> (display name, title nouns, brands, default questions)
CATEGORIES: dict[str, tuple[str, list[str], list[str], list[str]]] = {
    "wallets": ("Wallets & purses", ["wallet", "purse", "card holder"], ["Tommy Hilfiger", "Guess", "Fossil", "Zara"],
                ["What colour is the wallet?", "Whose name is on a card inside?"]),
    "phones": ("Phones", ["phone", "smartphone"], ["Apple", "Samsung", "Huawei", "Xiaomi"],
               ["What is the lock-screen wallpaper?", "What colour is the phone case?"]),
    "keys": ("Keys", ["car key", "key ring", "house keys"], ["Toyota", "Nissan", "Kia", "Hyundai"],
             ["What is attached to the key ring?", "How many keys are on it?"]),
    "id-cards": ("ID & university cards", ["ID card", "student card", "CPR card"], ["University"],
                 ["Whose name is on the card?", "What is the colour of the card holder?"]),
    "bags": ("Bags & backpacks", ["backpack", "handbag", "laptop bag"], ["Nike", "Adidas", "Herschel", "Jansport"],
             ["What colour is the bag?", "Name one item inside the bag"]),
    "laptops": ("Laptops & tablets", ["laptop", "tablet", "MacBook"], ["Apple", "Dell", "HP", "Lenovo"],
                ["What is the desktop wallpaper?", "What sticker is on the cover?"]),
    "headphones": ("Headphones & earbuds", ["AirPods", "earbuds", "headphones"], ["Apple", "Sony", "JBL", "Beats"],
                   ["What colour is the case?", "What is the device name when paired?"]),
    "glasses": ("Glasses", ["glasses", "sunglasses"], ["Ray-Ban", "Oakley", "Gucci"],
                ["What colour is the frame?", "What colour is the glasses case?"]),
    "bottles": ("Water bottles & cups", ["water bottle", "thermos", "tumbler"], ["Hydro Flask", "Stanley", "Contigo"],
                ["What colour is the bottle?", "What sticker is on it?"]),
    "clothing": ("Clothing", ["jacket", "hoodie", "scarf", "cap"], ["Nike", "H&M", "Zara", "Uniqlo"],
                 ["What colour is it?", "What size is it?"]),
    "jewelry": ("Jewelry", ["ring", "bracelet", "necklace"], ["Pandora", "Swarovski"],
                ["What material is it?", "Is anything engraved on it?"]),
    "books": ("Books & notebooks", ["notebook", "textbook", "folder"], ["Oxford", "Pearson", "Moleskine"],
              ["What is the subject or title?", "Whose name is written inside?"]),
    "umbrellas": ("Umbrellas", ["umbrella"], ["Totes", "Fulton"], ["What colour is it?", "What pattern is on it?"]),
    "chargers": ("Chargers & cables", ["charger", "power bank", "USB cable"], ["Anker", "Apple", "Samsung", "Belkin"],
                 ["What colour is it?", "What type of connector does it have?"]),
    "watches": ("Watches", ["watch", "smartwatch"], ["Casio", "Apple", "Seiko", "Garmin"],
                ["What colour is the strap?", "What is the watch face showing?"]),
}

# Possible answers for every default question (keeps the bcrypt work small).
GENERIC_ANSWERS = ["blue sticker", "a pen", "two", "three", "silver", "gold", "leather", "cartoon cat", "family photo"]


class HashCache:
    """bcrypt is slow on purpose; hash each distinct normalised answer once."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def __call__(self, answer: str) -> str:
        key = normalise_answer(answer)
        if key not in self._cache:
            self._cache[key] = hash_password(key)
        return self._cache[key]


def make_categories() -> list[Category]:
    return [
        Category(code=code, name=name, defaultQuestions=questions)
        for code, (name, _, _, questions) in CATEGORIES.items()
    ]


def make_users(domain: str) -> list[User]:
    password_hash = hash_password(SEED_PASSWORD)  # one hash shared by all seed accounts
    users = [
        User(name="ReFind Admin", email=f"admin@{domain}", passwordHash=password_hash,
             role=Role.admin, status=UserStatus.active),
    ]
    for i in range(1, N_OFFICERS + 1):
        users.append(User(name=f"Security Officer {i}", email=f"officer{i}@{domain}", passwordHash=password_hash,
                          role=Role.officer, status=UserStatus.active))
    for i in range(1, N_USERS - len(users) + 1):
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        users.append(User(
            name=f"{first} {last}",
            email=f"student{i:03d}@{domain}",
            passwordHash=password_hash,
            studentId=f"F23{i:05d}",
            # A few accounts stay unverified so that rule can be demonstrated.
            status=UserStatus.unverified if i % 25 == 0 else UserStatus.active,
        ))
    return users


def random_moment(now: datetime) -> tuple[datetime, datetime]:
    """(when it was lost/found, when it was reported), both in the past."""
    happened = now - timedelta(minutes=random.randint(60, 50 * 24 * 60))
    delay = timedelta(minutes=random.randint(5, 48 * 60))
    return happened, min(happened + delay, now)


def make_item(item_type: ItemType, reporter: User, now: datetime) -> Item:
    code = random.choice(list(CATEGORIES))
    _, nouns, brands, _ = CATEGORIES[code]
    color, brand = random.choice(COLORS), random.choice(brands)
    happened, submitted = random_moment(now)
    has_time = random.random() < 0.6
    found = item_type == ItemType.found
    return Item(
        id=PydanticObjectId(),
        type=item_type,
        title=f"{color.capitalize()} {random.choice(nouns)}",
        category=code,
        attributes=Attributes(color=color, brand=brand if random.random() < 0.7 else None),
        description=f"{'Found' if found else 'Lost'} {color} {brand} item",
        location=Location(
            building=random.choice(BUILDINGS),
            floor=random.choice(FLOORS),
            area=random.choice(AREAS),
            details=random.choice(DETAILS),
        ),
        date=happened,
        approxTime=happened.strftime("%H:%M") if has_time else None,
        timeSubmitted=submitted,
        reporterId=reporter.id,
        heldAt="Security office, Building 5" if found else None,
        statusHistory=[StatusChange(status=ItemStatus.open, at=submitted, by=reporter.id)],
    )


def make_secret(item: Item, hash_answer: HashCache) -> ItemSecret:
    questions = CATEGORIES[item.category][3]
    answers = [item.attributes.color or random.choice(COLORS), random.choice(FIRST_NAMES + GENERIC_ANSWERS)]
    return ItemSecret(
        itemId=item.id,
        verification=[
            VerificationQuestion(question=q, answerHash=hash_answer(a)) for q, a in zip(questions, answers)
        ],
        serialNumberHash=hash_answer(f"SN{random.randint(100000, 999999)}") if item.category in {"phones", "laptops"} else None,
    )


async def seed(db_name: str, reset: bool) -> None:
    settings = get_settings()
    random.seed(412)
    await db.connect(settings.app_uri, db_name)
    try:
        if reset:
            # delete_many, not drop: dropping a collection would remove its validator.
            for model in ALL_MODELS:
                await model.get_pymongo_collection().delete_many({})
            print("Cleared existing data.")
        elif await User.count() or await Item.count():
            raise SystemExit(f"{db_name} already has data; use --reset to replace it.")

        await Category.insert_many(make_categories())
        users = make_users(settings.allowed_email_domains[0])
        await User.insert_many(users)
        users = await User.find_all().to_list()  # reload with their ids
        officers = [u for u in users if u.role == Role.officer]
        students = [u for u in users if u.role == Role.user and u.status == UserStatus.active]

        now = datetime.now(UTC)
        hash_answer = HashCache()
        items: list[Item] = []
        secrets: list[ItemSecret] = []
        for i in range(N_ITEMS):
            if i % 2 == 0:
                items.append(make_item(ItemType.lost, random.choice(students), now))
            else:
                # Most found items are handed to the security desk and logged by an officer.
                reporter = random.choice(officers) if random.random() < 0.7 else random.choice(students)
                item = make_item(ItemType.found, reporter, now)
                items.append(item)
                secrets.append(make_secret(item, hash_answer))

        questions = {code: c[3] for code, c in CATEGORIES.items()}
        activity = make_activity(items, users, questions, now)

        # Found items and their secrets go in together, as one transaction (§3).
        async def txn(session):
            await Item.insert_many(items, session=session)
            await ItemSecret.insert_many(secrets, session=session)
            await Match.insert_many(activity.matches, session=session)
            await Claim.insert_many(activity.claims, session=session)
            await Notification.insert_many(activity.notifications, session=session)
            await AuditLog.insert_many(activity.audit, session=session)

        await db.run_in_transaction(txn)

        print(
            f"Seeded {db_name}: {await Category.count()} categories, {await User.count()} users, "
            f"{await Item.count()} items ({len(secrets)} found), {await ItemSecret.count()} itemSecrets, "
            f"{await Match.count()} matches, {await Claim.count()} claims, "
            f"{await Notification.count()} notifications, {await AuditLog.count()} auditLogs."
        )
        print(f"Logins: admin@{settings.allowed_email_domains[0]}, officer1..{N_OFFICERS}@..., "
              f"student001@... - password '{SEED_PASSWORD}'")
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=get_settings().mongo_db)
    parser.add_argument("--reset", action="store_true", help="delete existing documents first")
    args = parser.parse_args()
    asyncio.run(seed(args.db, args.reset))


if __name__ == "__main__":
    main()
