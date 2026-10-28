// Monthly fact table for analytics (PR1 data-warehouse alignment, mongosh).
//
//   mongosh "<refindApp or refindReports uri>/refind?..." db/warehouse_fact.js
//
// Grain: one row per month x category x building x type. Measures come from
// items and their claims. The pipeline only reads; to materialise the table
// for a BI tool, uncomment the $merge stage (needs write access to the
// target database, e.g. a separate refind_dw database).

const pipeline = [
  {
    $lookup: {
      from: "claims", localField: "_id", foreignField: "itemId", as: "claims",
      pipeline: [{ $project: { status: 1, _id: 0 } }],
    },
  },
  {
    $group: {
      _id: {
        month: { $dateToString: { format: "%Y-%m", date: "$date" } },
        category: "$category",
        building: "$location.building",
        type: "$type",
      },
      reported: { $sum: 1 },
      returned: { $sum: { $cond: [{ $eq: ["$status", "returned"] }, 1, 0] } },
      matched: { $sum: { $cond: [{ $in: ["$status", ["matched", "claimed", "returned"]] }, 1, 0] } },
      claimsSubmitted: { $sum: { $size: "$claims" } },
      claimsApproved: {
        $sum: { $size: { $filter: { input: "$claims", cond: { $eq: ["$$this.status", "approved"] } } } },
      },
      avgHoursToReport: { $avg: { $divide: [{ $subtract: ["$timeSubmitted", "$date"] }, 36e5] } },
    },
  },
  { $set: { avgHoursToReport: { $round: ["$avgHoursToReport", 1] } } },
  { $sort: { "_id.month": 1, reported: -1 } },
  // { $merge: { into: { db: "refind_dw", coll: "factItemsMonthly" }, on: "_id", whenMatched: "replace" } },
];

const rows = db.items.aggregate(pipeline).toArray();
print(`${rows.length} fact rows (month x category x building x type)`);
console.table(rows.slice(0, 10).map((r) => ({ ...r._id, reported: r.reported, matched: r.matched,
  returned: r.returned, claims: r.claimsSubmitted, approved: r.claimsApproved, avgHoursToReport: r.avgHoursToReport })));

// Return rate per month, rolled up from the fact rows (the §4.5 report).
const rollup = {};
for (const r of rows.filter((r) => r._id.type === "found")) {
  const m = (rollup[r._id.month] ??= { month: r._id.month, found: 0, returned: 0 });
  m.found += r.reported;
  m.returned += r.returned;
}
console.table(Object.values(rollup).map((m) => ({ ...m, returnRate: `${((100 * m.returned) / m.found).toFixed(1)}%` })));
