// Index evidence (mongosh), updated for PR2 with the queries the API sends: explain("executionStats")
// for each key query, BEFORE (forced collection scan with hint({ $natural: 1 }))
// and AFTER (the planner's choice, which should be the named index).
//
//   mongosh "mongodb://refindApp:<password>@localhost:27017/refind?authSource=refind&directConnection=true" db/explain_indexes.js
//
// No index is dropped, so it is safe on the shared database. To see the
// same plans in Compass, paste a query into the Documents tab and open
// "Explain Plan".

const now = new Date();
const daysAgo = (n) => new Date(now.getTime() - n * 864e5);
const sample = db.items.findOne({ type: "lost" });
const reporter = db.items.aggregate([{ $group: { _id: "$reporterId", n: { $sum: 1 } } }, { $sort: { n: -1 } }, { $limit: 1 }]).next()._id;
const someone = db.notifications.findOne().userId;
const foundItem = db.itemSecrets.findOne().itemId;
const claimant = db.claims.findOne().claimantId.oid; // DBRef: mongosh calls $id "oid"
const claimed = db.claims.findOne();
// Someone whose lost report has matches, for "my matches".
const matchOwner = db.items.findOne({ _id: db.matches.findOne().lostItemId }).reporterId;
const myItems = db.items.find({ reporterId: matchOwner }, { _id: 1 }).toArray().map((d) => d._id);
const visible = { $in: ["open", "matched"] };
const week = 7 * 864e5;

// Each query is written exactly as the service sends it for that endpoint (PR2).
const queries = [
  { name: "GET /items (guest, category)", index: "type_category_status_date", coll: "items",
    filter: { type: "found", status: visible, category: sample.category },
    sort: { date: -1, timeSubmitted: -1 }, limit: 20 },
  { name: "GET /items?building=", index: "building_date", coll: "items",
    filter: { type: "found", status: visible, "location.building": "Library" },
    sort: { date: -1, timeSubmitted: -1 }, limit: 20 },
  { name: "GET /items/mine", index: "reporter_submitted", coll: "items",
    filter: { reporterId: reporter }, sort: { date: -1, timeSubmitted: -1 }, limit: 20 },
  { name: "Matching candidates ($match)", index: "type_category_status_date", coll: "items",
    filter: { type: "found", category: sample.category, status: visible,
              date: { $gte: new Date(sample.date.getTime() - week), $lte: new Date(sample.date.getTime() + week) },
              _id: { $ne: sample._id }, reporterId: { $ne: sample.reporterId } } },
  { name: "Archive job (stale items)", index: "status_date", coll: "items",
    // 45 days, not 60, because the seed spreads items over the last 50 days.
    filter: { status: visible, date: { $lt: daysAgo(45) } } },
  { name: "Login by email", index: "email_unique", coll: "users",
    filter: { email: "student001@university.edu" } },
  { name: "GET /items/{id}/questions", index: "itemId_unique", coll: "itemSecrets",
    filter: { itemId: foundItem } },
  { name: "GET /matches/mine (lost side)", index: "pair_unique", coll: "matches",
    filter: { lostItemId: { $in: myItems } }, sort: { score: -1, createdAt: -1 } },
  { name: "GET /matches/mine (found side)", index: "found_status", coll: "matches",
    filter: { foundItemId: { $in: myItems } }, sort: { score: -1, createdAt: -1 } },
  { name: "Approve: suggestions to dismiss", index: "found_status", coll: "matches",
    filter: { foundItemId: claimed.itemId, status: "suggested" } },
  { name: "GET /claims/review", index: "review_queue", coll: "claims",
    filter: { status: "pending", answers: { $ne: [] } }, sort: { submittedAt: 1 }, limit: 20 },
  { name: "GET /claims/mine", index: "claimant_submitted", coll: "claims",
    filter: { "claimantId.$id": claimant }, sort: { submittedAt: -1 }, limit: 20 },
  { name: "Approve: rival claims", index: "item_claimant_unique", coll: "claims",
    filter: { itemId: claimed.itemId, _id: { $ne: claimed._id }, status: { $in: ["pending", "locked"] } } },
  { name: "GET /notifications", index: "user_created", coll: "notifications",
    filter: { userId: someone }, sort: { createdAt: -1 }, limit: 20 },
  { name: "Unread count", index: "user_created", coll: "notifications",
    filter: { userId: someone, readAt: null } },
];

// The winning plan's stages from the root down, e.g. "FETCH > IXSCAN(type_category_status_date)".
function stages(plan) {
  const out = [];
  for (let p = plan; p; p = p.inputStage || (p.inputStages && p.inputStages[0])) {
    out.push(p.indexName ? `${p.stage}(${p.indexName})` : p.stage);
  }
  return out.join(" > ");
}

function run(q, hint) {
  let cursor = db.getCollection(q.coll).find(q.filter);
  if (q.sort) cursor = cursor.sort(q.sort);
  if (q.limit) cursor = cursor.limit(q.limit);
  if (hint) cursor = cursor.hint(hint);
  const e = cursor.explain("executionStats");
  const s = e.executionStats;
  return {
    plan: stages(e.queryPlanner.winningPlan),
    returned: s.nReturned,
    keys: s.totalKeysExamined,
    docs: s.totalDocsExamined,
    ms: s.executionTimeMillis,
  };
}

const rows = [];
for (const q of queries) {
  const before = run(q, { $natural: 1 });
  const after = run(q);
  rows.push({
    query: q.name, coll: q.coll, returned: after.returned,
    "docs before": before.docs, "docs after": after.docs, "keys after": after.keys,
    "ms before": before.ms, "ms after": after.ms, "plan after": after.plan,
    ok: after.plan.includes(`IXSCAN(${q.index})`) ? "yes" : `expected ${q.index}`,
  });
}

// Keyword search (GET /items?q=): without the text index the only option is a regex scan.
const regex = db.items.find({ type: "found", status: visible, $or: [{ title: /wallet/i }, { description: /wallet/i }] })
  .explain("executionStats");
const text = db.items.find({ type: "found", status: visible, $text: { $search: "wallet" } }).explain("executionStats");
rows.push({
  query: "GET /items?q=wallet", coll: "items", returned: text.executionStats.nReturned,
  "docs before": regex.executionStats.totalDocsExamined, "docs after": text.executionStats.totalDocsExamined,
  "keys after": text.executionStats.totalKeysExamined,
  "ms before": regex.executionStats.executionTimeMillis, "ms after": text.executionStats.executionTimeMillis,
  "plan after": stages(text.queryPlanner.winningPlan), ok: stages(text.queryPlanner.winningPlan).includes("item_text") ? "yes" : "expected item_text",
});

print(`Collection sizes: items ${db.items.estimatedDocumentCount()}, users ${db.users.estimatedDocumentCount()}, ` +
      `claims ${db.claims.estimatedDocumentCount()}, notifications ${db.notifications.estimatedDocumentCount()}`);
console.table(rows);
if (typeof process !== "undefined" && process.env.EXPLAIN_JSON) print(JSON.stringify(rows));
