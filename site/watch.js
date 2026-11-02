"use strict";

const WATCH_KEY = "eaukcionai.watch";
const WATCH_ONLY_KEY = "eaukcionai.watchOnly";

function validPair(entry) {
  if (!Array.isArray(entry) || entry.length !== 2) return null;
  const [auctionId, itemNo] = entry;
  if (!Number.isInteger(auctionId) || auctionId <= 0) return null;
  if (!Number.isInteger(itemNo) || itemNo <= 0) return null;
  return [auctionId, itemNo];
}

function parseMarks(raw) {
  if (raw == null || raw === "") return [];
  let parsed = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(parsed)) return [];
  const seen = new Set();
  const marks = [];
  for (const entry of parsed) {
    const pair = validPair(entry);
    if (!pair) continue;
    const key = `${pair[0]}:${pair[1]}`;
    if (seen.has(key)) continue;
    seen.add(key);
    marks.push(pair);
  }
  return marks;
}

function dumpMarks(marks) {
  return JSON.stringify(marks);
}

function toggleMark(marks, auctionId, itemNo) {
  const next = [];
  let found = false;
  for (const pair of marks) {
    if (pair[0] === auctionId && pair[1] === itemNo) {
      found = true;
      continue;
    }
    next.push([pair[0], pair[1]]);
  }
  if (!found) next.push([auctionId, itemNo]);
  return next;
}

function parseWatchOnly(raw) {
  return raw === "1";
}

function skipDefaultWindow(watchOnly, endFrom, endTo, defaultEndFrom) {
  return Boolean(watchOnly) && endFrom === defaultEndFrom && (endTo == null || endTo === "");
}

function watchClause(watchOnly, marks) {
  if (!watchOnly) return null;
  if (marks.length === 0) return { sql: "0", params: [] };
  const tuples = marks.map(() => "(?, ?)").join(", ");
  return {
    sql: `(auction_id, item_no) IN (${tuples})`,
    params: marks.flat(),
  };
}

const Watch = {
  WATCH_KEY,
  WATCH_ONLY_KEY,
  parseMarks,
  dumpMarks,
  toggleMark,
  parseWatchOnly,
  skipDefaultWindow,
  watchClause,
};

if (typeof module === "object" && module && module.exports) module.exports = Watch;
if (typeof window !== "undefined") window.Watch = Watch;
