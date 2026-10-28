// CRUD query demonstrations for Progress Report 1 (mongosh).
//
//   mongosh "mongodb://refindApp:<password>@localhost:27017/refind?authSource=refind&directConnection=true" db/crud_demo.js
//
// Run against the seeded database. Every document the script creates is
// tagged "crud-demo" and deleted again at the end, so it can be re-run.
// Each step prints a heading, the query, and its result for the screenshots.

const TAG = "crud-demo";
const now = new Date();
const daysAgo = (n) => new Date(now.getTime() - n * 864e5);
const midnight = (d) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));

function step(title, query, run) {
  print(`\n=== ${title} ===`);
  print(query);
  try {
    printjson(run());
  } catch (e) {
    print(`Rejected by MongoDB: ${e.codeName || e.name} (code ${e.code}) - ${e.errmsg || e.message}`);
  }
}

const officer = db.users.findOne({ role: "officer" });
const student = db.users.findOne({ role: "user", status: "active" });
const other = db.users.findOne({ role: "user", status: "active", _id: { $ne: student._id } });

// ---------------------------------------------------------------- CREATE
const foundId = new ObjectId();
const lostId = new ObjectId();

step("C1 items.insertMany - one found and one lost report", "db.items.insertMany([found, lost])", () =>
  db.items.insertMany([
    {
      _id: foundId, type: "found", title: "Black wallet", category: "wallets",
      attributes: { color: "black", brand: "Fossil" }, description: `${TAG}: leather wallet`,
      location: { building: "Library", floor: "Ground floor", area: "Main entrance", details: "On the bench" },
      date: midnight(daysAgo(1)), approxTime: "14:30", timeSubmitted: now, photoIds: [], status: "open",
      reporterId: officer._id, heldAt: "Security office, Building 5", version: 1,
      statusHistory: [{ status: "open", at: now, by: officer._id }],
    },
    {
      _id: lostId, type: "lost", title: "Wallet", category: "wallets",
      attributes: { color: "black" }, description: `${TAG}: lost near the library`,
      location: { building: "Library" }, date: midnight(daysAgo(2)), timeSubmitted: now, photoIds: [],
      status: "open", reporterId: student._id, version: 1,
      statusHistory: [{ status: "open", at: now, by: student._id }],
    },
  ]));

step("C2 itemSecrets.insertOne - the found item's verification questions (hashed answers)",
  "db.itemSecrets.insertOne({ itemId, verification: [{ question, answerHash }] })", () =>
    db.itemSecrets.insertOne({
      itemId: foundId,
      // A bcrypt hash (cost 12) borrowed from a seeded secret: answers are never stored in plain text.
      verification: [{ question: "Whose name is on a card inside?", answerHash: db.itemSecrets.findOne().verification[0].answerHash }],
      serialNumberHash: null,
    }));

step("C3 matches.updateOne upsert + $setOnInsert - how the matching engine saves a candidate",
  "db.matches.updateOne({ lostItemId, foundItemId }, { $setOnInsert: {...} }, { upsert: true })", () =>
    db.matches.updateOne(
      { lostItemId: lostId, foundItemId: foundId },
      { $setOnInsert: { score: 85, reasons: ["same category", "same building (Library)", "same colour (black)"], status: "suggested", createdAt: now } },
      { upsert: true }));

step("C3b the same upsert again - matchedCount 1, upsertedCount 0, so no duplicate and no second alert",
  "(same call)", () =>
    db.matches.updateOne(
      { lostItemId: lostId, foundItemId: foundId },
      { $setOnInsert: { score: 85, reasons: [], status: "suggested", createdAt: now } },
      { upsert: true }));

const matchId = db.matches.findOne({ lostItemId: lostId })._id;
const claimId = new ObjectId();
step("C4 claims.insertOne - the owner claims the found item with answers",
  "db.claims.insertOne({ itemId, claimantId: DBRef('users', id), matchId, answers, status: 'pending' })", () =>
    db.claims.insertOne({
      _id: claimId, itemId: foundId, claimantId: new DBRef("users", student._id), matchId,
      answers: [{ question: "Whose name is on a card inside?", answer: "Ahmed" }], proofNote: TAG,
      status: "pending", failedAttempts: 0, submittedAt: now, reviewedBy: null, reviewedAt: null, handover: null,
    }));

step("C5 notifications.insertOne - new_match alert with its dedupeKey",
  "db.notifications.insertOne({ userId, type: 'new_match', dedupeKey: 'new_match:<matchId>:<userId>' })", () =>
    db.notifications.insertOne({
      userId: student._id, type: "new_match", message: `${TAG}: possible match for your wallet (85%)`,
      refId: matchId, dedupeKey: `new_match:${matchId}:${student._id}`, readAt: null, createdAt: now,
    }));

step("C6 the same alert again - rejected by the unique dedupeKey index",
  "db.notifications.insertOne({ ...same dedupeKey })", () =>
    db.notifications.insertOne({
      userId: student._id, type: "new_match", message: "duplicate", refId: matchId,
      dedupeKey: `new_match:${matchId}:${student._id}`, readAt: null, createdAt: now,
    }));

step("C7 a second claim by the same user on the same item - rejected by { itemId, claimantId } unique",
  "db.claims.insertOne({ itemId, claimantId: <same user> })", () =>
    db.claims.insertOne({
      itemId: foundId, claimantId: new DBRef("users", student._id), status: "pending", failedAttempts: 0, submittedAt: now,
    }));

step("C8 an item in an unknown building - rejected by the $jsonSchema validator",
  "db.items.insertOne({ ..., location: { building: 'Mars' } })", () =>
    db.items.insertOne({
      type: "found", title: TAG, category: "wallets", location: { building: "Mars" }, date: now,
      timeSubmitted: now, status: "open", reporterId: officer._id, version: 1,
    }));

// ------------------------------------------------------------------ READ
step("R1 find with filters + projection + sort - open found wallets in the Library, newest first",
  "db.items.find({ type: 'found', category: 'wallets', status: { $in: ['open','matched'] }, 'location.building': 'Library' }, { title: 1, date: 1, status: 1 }).sort({ date: -1 }).limit(5)",
  () => db.items.find(
    { type: "found", category: "wallets", status: { $in: ["open", "matched"] }, "location.building": "Library" },
    { title: 1, date: 1, status: 1, "location.building": 1 }).sort({ date: -1 }).limit(5).toArray());

step("R2 find on an embedded field + date range - items found in the last 7 days on the ground floor",
  "db.items.find({ type: 'found', 'location.floor': 'Ground floor', date: { $gte: <7 days ago> } }).count()",
  () => db.items.countDocuments({ type: "found", "location.floor": "Ground floor", date: { $gte: daysAgo(7) } }));

step("R3 $text keyword search - 'black wallet', ranked by text score",
  "db.items.find({ $text: { $search: 'black wallet' } }, { score: { $meta: 'textScore' } }).sort({ score: { $meta: 'textScore' } }).limit(5)",
  () => db.items.find({ $text: { $search: "black wallet" } }, { title: 1, score: { $meta: "textScore" } })
    .sort({ score: { $meta: "textScore" } }).limit(5).toArray());

step("R4 officer review queue - pending claims, oldest first",
  "db.claims.find({ status: 'pending' }).sort({ submittedAt: 1 })",
  () => db.claims.find({ status: "pending" }, { itemId: 1, status: 1, submittedAt: 1 }).sort({ submittedAt: 1 }).toArray());

step("R5 aggregate + $lookup - a claim with its item and claimant (referenced documents joined)",
  "db.claims.aggregate([{ $match: { _id } }, { $lookup: items }, { $lookup: users }, { $project }])",
  () => db.claims.aggregate([
    { $match: { _id: claimId } },
    { $lookup: { from: "items", localField: "itemId", foreignField: "_id", as: "item" } },
    { $lookup: { from: "users", localField: "claimantId.$id", foreignField: "_id", as: "claimant" } },
    { $project: { status: 1, "item.title": 1, "item.location.building": 1, "claimant.name": 1, "claimant.email": 1 } },
  ]).toArray());

step("R6 itemSecrets are never returned by an item query - the item has no verification field",
  "db.items.findOne({ _id: foundId }).verification",
  () => ({ verificationOnItem: db.items.findOne({ _id: foundId }).verification ?? null }));

// ---------------------------------------------------------------- UPDATE
step("U1 $set + $inc with a version check - optimistic edit of the item (version 1 -> 2)",
  "db.items.updateOne({ _id, version: 1 }, { $set: { description }, $inc: { version: 1 } })",
  () => db.items.updateOne({ _id: foundId, version: 1 }, { $set: { description: `${TAG}: brown leather wallet` }, $inc: { version: 1 } }));

step("U1b a stale edit (still version 1) changes nothing - the API turns matchedCount 0 into 409",
  "(same call)",
  () => db.items.updateOne({ _id: foundId, version: 1 }, { $set: { description: "stale" }, $inc: { version: 1 } }));

step("U2 $set + $push + $inc - matching moves both items to 'matched' and appends to statusHistory",
  "db.items.updateMany({ _id: { $in: [lostId, foundId] }, status: 'open' }, { $set: { status: 'matched' }, $push: { statusHistory: {...} }, $inc: { version: 1 } })",
  () => db.items.updateMany(
    { _id: { $in: [lostId, foundId] }, status: "open" },
    { $set: { status: "matched" }, $push: { statusHistory: { status: "matched", at: now, by: null } }, $inc: { version: 1 } }));

step("U3 $inc - a wrong set of answers increments failedAttempts",
  "db.claims.updateOne({ _id: claimId, status: 'pending' }, { $inc: { failedAttempts: 1 } })",
  () => db.claims.updateOne({ _id: claimId, status: "pending" }, { $inc: { failedAttempts: 1 } }));

step("U4 $addToSet - add a reason to the match only if it is not there yet",
  "db.matches.updateOne({ _id: matchId }, { $addToSet: { reasons: 'dates 1 day(s) apart' } })",
  () => db.matches.updateOne({ _id: matchId }, { $addToSet: { reasons: "dates 1 day(s) apart" } }));

step("U5 $set readAt - the user opens the notification (starts its 90-day TTL)",
  "db.notifications.updateOne({ dedupeKey }, { $set: { readAt: new Date() } })",
  () => db.notifications.updateOne({ dedupeKey: `new_match:${matchId}:${student._id}` }, { $set: { readAt: now } }));

step("U6 conditional approval - only a still-pending claim can be approved (step 1 of the §5.4 transaction)",
  "db.claims.updateOne({ _id: claimId, status: 'pending' }, { $set: { status: 'approved', reviewedBy, reviewedAt } })",
  () => db.claims.updateOne({ _id: claimId, status: "pending" }, { $set: { status: "approved", reviewedBy: officer._id, reviewedAt: now } }));

step("U7 a second confirmed match for the same found item - rejected by the partial unique index",
  "db.matches.insertOne({ lostItemId: <another>, foundItemId, status: 'confirmed' }) after confirming the first",
  () => {
    db.matches.updateOne({ _id: matchId }, { $set: { status: "confirmed" } });
    return db.matches.insertOne({ lostItemId: new ObjectId(), foundItemId: foundId, score: 70, reasons: [TAG], status: "confirmed", createdAt: now });
  });

step("U8 the item after the updates",
  "db.items.findOne({ _id: foundId }, { status: 1, version: 1, description: 1, statusHistory: 1 })",
  () => db.items.findOne({ _id: foundId }, { status: 1, version: 1, description: 1, statusHistory: 1 }));

// ---------------------------------------------------------------- DELETE
step("D1 deleteOne - the claimant's notification", "db.notifications.deleteOne({ dedupeKey })",
  () => db.notifications.deleteOne({ dedupeKey: `new_match:${matchId}:${student._id}` }));

step("D2 deleteMany - remove everything this demo created",
  "db.claims / matches / itemSecrets / items .deleteMany({ <demo ids> })",
  () => ({
    claims: db.claims.deleteMany({ itemId: foundId }).deletedCount,
    matches: db.matches.deleteMany({ foundItemId: foundId }).deletedCount,
    itemSecrets: db.itemSecrets.deleteMany({ itemId: foundId }).deletedCount,
    items: db.items.deleteMany({ _id: { $in: [foundId, lostId] } }).deletedCount,
  }));

// Users are never hard-deleted (§4.1): soft delete is a $set on status.
step("D3 soft delete of a user - $set status 'disabled', then restore",
  "db.users.updateOne({ _id }, { $set: { status: 'disabled' } })",
  () => {
    const r = db.users.updateOne({ _id: other._id }, { $set: { status: "disabled" } });
    db.users.updateOne({ _id: other._id }, { $set: { status: "active" } });
    return r;
  });

print("\nDone. Demo documents removed.");
