"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const Watch = require("./watch.js");

test("parseMarks drops junk and duplicate pairs and reads empty or corrupt values as no marks", () => {
  const stored = JSON.stringify([
    [1, 2],
    [1, 2],
    [0, 1],
    [-1, 2],
    [1.5, 2],
    ["1", 2],
    [1],
    [1, 2, 3],
    null,
    "nope",
    { auction_id: 3, item_no: 4 },
    [3, 4],
  ]);
  assert.deepEqual(Watch.parseMarks(stored), [[1, 2], [3, 4]]);
  assert.equal(stored.includes("[1,2]") || stored.includes("[1, 2]"), true);

  for (const raw of [null, "", "{", "not json", "{}", "42", "null", "true", '"x"']) {
    assert.deepEqual(Watch.parseMarks(raw), []);
  }
  assert.deepEqual(Watch.parseMarks({}), []);
  assert.deepEqual(Watch.parseMarks(42), []);

  const input = [[1, 2], [1, 2], [0, 9], [5, 6]];
  const parsed = Watch.parseMarks(input);
  assert.deepEqual(parsed, [[1, 2], [5, 6]]);
  assert.notEqual(parsed, input);
  assert.deepEqual(input, [[1, 2], [1, 2], [0, 9], [5, 6]]);

  assert.equal(Watch.parseWatchOnly("1"), true);
  for (const raw of [null, undefined, "", "0", "true", "1 ", 1, true]) {
    assert.equal(Watch.parseWatchOnly(raw), false);
  }
});

test("toggleMark appends or removes a pair without mutating, and dumpMarks round-trips", () => {
  const marks = [[1, 2]];
  Object.freeze(marks[0]);
  Object.freeze(marks);
  const added = Watch.toggleMark(marks, 3, 4);
  assert.deepEqual(marks, [[1, 2]]);
  assert.deepEqual(added, [[1, 2], [3, 4]]);
  const removed = Watch.toggleMark(added, 1, 2);
  assert.deepEqual(added, [[1, 2], [3, 4]]);
  assert.deepEqual(removed, [[3, 4]]);
  assert.deepEqual(Watch.parseMarks(Watch.dumpMarks(added)), [[1, 2], [3, 4]]);
  assert.deepEqual(Watch.parseMarks(Watch.dumpMarks(removed)), [[3, 4]]);
  assert.deepEqual(Watch.toggleMark(removed, 3, 4), []);
});

test("skipDefaultWindow is true only for the default range while Tik stebimi is on", () => {
  const defaultEndFrom = "2026-07-31";
  assert.equal(Watch.skipDefaultWindow(true, defaultEndFrom, "", defaultEndFrom), true);
  assert.equal(Watch.skipDefaultWindow(true, defaultEndFrom, null, defaultEndFrom), true);
  assert.equal(Watch.skipDefaultWindow(true, defaultEndFrom, undefined, defaultEndFrom), true);

  assert.equal(Watch.skipDefaultWindow(false, defaultEndFrom, "", defaultEndFrom), false);
  assert.equal(Watch.skipDefaultWindow(true, "2026-01-01", "", defaultEndFrom), false);
  assert.equal(Watch.skipDefaultWindow(true, undefined, "", defaultEndFrom), false);
  assert.equal(Watch.skipDefaultWindow(true, null, "", defaultEndFrom), false);
  assert.equal(Watch.skipDefaultWindow(true, "", "", defaultEndFrom), false);
  assert.equal(Watch.skipDefaultWindow(true, defaultEndFrom, "2026-08-01", defaultEndFrom), false);
});

test("watchClause is a bound mark conjunct, or matches nothing when the set is empty", () => {
  assert.equal(Watch.watchClause(false, [[1, 2]]), null);
  assert.equal(Watch.watchClause(false, []), null);
  assert.deepEqual(Watch.watchClause(true, []), { sql: "0", params: [] });

  const marks = [[7, 8], [9, 10]];
  const clause = Watch.watchClause(true, marks);
  assert.equal(clause.sql, "(auction_id, item_no) IN ((?, ?), (?, ?))");
  assert.deepEqual(clause.params, [7, 8, 9, 10]);
  assert.equal(clause.sql.includes("7"), false);
  assert.equal(clause.sql.includes("10"), false);
  assert.deepEqual(marks, [[7, 8], [9, 10]]);
});
