// Index evidence for Progress Report 1 (mongosh): explain("executionStats")
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

const queries = [
  {
    name: "Matching candidates",
    index: "type_category_status_date",
    coll: "items",
    filter: { type: "found", category: sample.category, status: { $in: ["open", "matched"] },
              date: { $gte: new Date(sample.date.getTime() - 7 * 864e5), $lte: new Date(sample.date.getTime() + 7 * 864e5) } },
    sort: { date: -1 },
  },
  { name: "Items in a building", index: "building_date", coll: "items",
    filter: { "location.building": "Library" }, sort: { date: -1 }, limit: 20 },
  { name: "My reports", index: "reporter_submitted", coll: "items",
    filter: { reporterId: reporter }, sort: { timeSubmitted: -1 } },
  { name: "Archive job (stale items)", index: "status_date", coll: "items",
    // 45 days, not 60, because the seed spreads items over the last 50 days.
    filter: { status: { $in: ["open", "matched"] }, date: { $lt: daysAgo(45) } } },
  { name: "Login by email", index: "email_unique", coll: "users",
    filter: { email: "student001@university.edu" } },
  { name: "Secrets for one item", index: "itemId_unique", coll: "itemSecrets",
    filter: { itemId: foundItem } },
  { name: "Officer review queue", index: "review_queue", coll: "claims",
    filter: { status: "pending" }, sort: { submittedAt: 1 } },
  { name: "My notifications", index: "user_created", coll: "notifications",
    filter: { userId: someone }, sort: { createdAt: -1 } },
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

// Keyword search: without the text index the only option is a regex scan.
const regex = db.items.find({ $or: [{ title: /wallet/i }, { description: /wallet/i }] }).explain("executionStats");
const text = db.items.find({ $text: { $search: "wallet" } }).explain("executionStats");
rows.push({
  query: "Keyword search", coll: "items", returned: text.executionStats.nReturned,
  "docs before": regex.executionStats.totalDocsExamined, "docs after": text.executionStats.totalDocsExamined,
  "keys after": text.executionStats.totalKeysExamined,
  "ms before": regex.executionStats.executionTimeMillis, "ms after": text.executionStats.executionTimeMillis,
  "plan after": stages(text.queryPlanner.winningPlan), ok: stages(text.queryPlanner.winningPlan).includes("item_text") ? "yes" : "expected item_text",
});

print(`Collection sizes: items ${db.items.estimatedDocumentCount()}, users ${db.users.estimatedDocumentCount()}, ` +
      `claims ${db.claims.estimatedDocumentCount()}, notifications ${db.notifications.estimatedDocumentCount()}`);
console.table(rows);
if (typeof process !== "undefined" && process.env.EXPLAIN_JSON) print(JSON.stringify(rows));
