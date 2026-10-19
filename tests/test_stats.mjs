import assert from "node:assert/strict";
import test from "node:test";

await import(new URL("../site/stats.js", import.meta.url));
const stats = globalThis.AuctionStats;

function row(fields) {
  return {
    share_sold: "1/1",
    area_m2: 10,
    municipality: "Vilniaus m. sav.",
    settlement: "Vilniaus m.",
    subtype: "Patalpos/Butai",
    type: null,
    highest_bid_eur: null,
    ...fields,
  };
}

test("status labels collapse onto the three outcomes", () => {
  assert.equal(stats.statusGroup("Įvykęs"), "Įvykusios");
  assert.equal(stats.statusGroup("Baigtos"), "Įvykusios");
  assert.equal(stats.statusGroup("Baigtas"), "Įvykusios");
  assert.equal(stats.statusGroup("Įvykusios"), "Įvykusios");
  assert.equal(stats.statusGroup("Neįvykęs"), "Neįvykusios");
  assert.equal(stats.statusGroup("Atšauktas"), "Atšauktos");
  assert.equal(stats.statusGroup("Paskelbtas"), "Paskelbtas");
  assert.deepEqual(new Set(stats.statusesFor("Įvykusios")), new Set(["Baigtas", "Baigtos", "Įvykęs", "Įvykusios"]));
  assert.deepEqual(stats.statusesFor("Paskelbtas"), ["Paskelbtas"]);
});

test("a week starts on Monday, including across the new year", () => {
  assert.equal(stats.weekStart("2026-10-06"), "2026-10-05");
  assert.equal(stats.weekStart("2027-01-01"), "2026-12-28");
  assert.equal(stats.median([1, 2, 3, 4]), 2.5);
});

test("summary counts an auction once and keeps a bid on a failed auction out of the wins", () => {
  const observations = [
    stats.observe(row({ auction_id: 1, status: "Įvykęs", starting_price_eur: 100, highest_bid_eur: 150, end_date: "2026-10-06T10:00:00" }), 1),
    stats.observe(row({ auction_id: 2, status: "Neįvykęs", starting_price_eur: 80, highest_bid_eur: 90, end_date: "2026-10-07T10:00:00" }), 1),
    stats.observe(row({ auction_id: 3, status: "Atšauktas", starting_price_eur: 50, end_date: "2026-10-08T10:00:00" }), 1),
    stats.observe(row({
      auction_id: 4,
      status: "Paskelbtas",
      type: "Pirmosios",
      starting_price_eur: 200,
      end_date: "2026-10-22T10:00:00",
      municipality: "Kauno m. sav.",
      settlement: "Kauno m.",
    }), 1),
    stats.observe(row({ auction_id: 5, status: "Baigtas", starting_price_eur: 100, highest_bid_eur: 100, area_m2: 10, end_date: "2026-10-06T10:00:00" }), 2),
    stats.observe(row({ auction_id: 5, status: "Baigtas", starting_price_eur: 100, highest_bid_eur: 100, area_m2: 20, end_date: "2026-10-06T10:00:00" }), 2),
  ];
  const summary = stats.summarize(observations, "2026-10-19");
  assert.equal(summary.items, 6);
  assert.equal(summary.auctions, 5);
  assert.equal(summary.won, 2);
  assert.equal(summary.lost, 1);
  assert.equal(summary.cancelled, 1);
  assert.equal(summary.live, 1);
  assert.equal(summary.wonRate, 2 / 3);
  assert.equal(summary.startingMedian, 100);
  assert.equal(summary.achievedMedian, 125);
  assert.equal(summary.premiumMedian, 1.25);
  assert.equal(summary.soldAtStart, 0.5);
  assert.equal(summary.endingWithin7Days, 1);
  assert.deepEqual(summary.rounds, [{ type: "Pirmosios", n: 1 }]);
  assert.deepEqual(summary.eurM2, [{
    subtype: "Patalpos/Butai",
    askingMedian: 9,
    achievedMedian: 15,
    askingN: 4,
    achievedN: 1,
  }]);

  const weeks = stats.byTime(observations, "week");
  assert.deepEqual(weeks.map((week) => week.period), ["2026-10-19", "2026-10-05"]);
  assert.equal(weeks[1].auctions, 4);
  assert.equal(weeks[1].wonRate, 2 / 3);
  assert.equal(weeks[1].startingMedian, 90);
  assert.equal(weeks[1].askingMedian, 8);
  assert.equal(weeks[0].auctions, 1);
  assert.equal(weeks[0].wonRate, null);
});

test("a partial share and a missing area have no eur per m2", () => {
  const partial = stats.observe(row({ auction_id: 1, status: "Įvykusios", share_sold: "1/2", starting_price_eur: 100, highest_bid_eur: 100, end_date: "2026-10-06" }), 1);
  const noArea = stats.observe(row({ auction_id: 2, status: "Įvykusios", area_m2: null, starting_price_eur: 100, highest_bid_eur: 100, end_date: "2026-10-06" }), 1);
  assert.equal(partial.askingEurM2, null);
  assert.equal(partial.achievedEurM2, null);
  assert.equal(noArea.achievedEurM2, null);
});

test("place rows compare all sales with the live lots in the current filter", () => {
  const sold = stats.observe(row({ auction_id: 1, status: "Įvykusios", starting_price_eur: 100, highest_bid_eur: 100, end_date: "2020-01-01" }), 1);
  const failed = stats.observe(row({
    auction_id: 2,
    status: "Neįvykusios",
    starting_price_eur: 50,
    end_date: "2020-01-02",
    municipality: "Kauno m. sav.",
    settlement: "Kauno m.",
  }), 1);
  const live = stats.observe(row({ auction_id: 3, status: "Vykstančios", starting_price_eur: 200, end_date: "2026-10-22" }), 1);
  const rows = stats.byPlace([sold, failed], [live], "municipality", true);
  assert.deepEqual(
    stats.byPlace([sold, failed], [live], "municipality").map((row) => row.place),
    ["Kauno m. sav.", "Vilniaus m. sav."],
  );
  assert.deepEqual(rows.map((row) => row.place), ["Vilniaus m. sav.", "Kauno m. sav."]);
  assert.equal(rows[0].auctions, 1);
  assert.equal(rows[0].live, 1);
  assert.equal(rows[0].wonRate, 1);
  assert.equal(rows[0].achievedMedian, 10);
  assert.equal(rows[0].liveAskingMedian, 20);
  assert.equal(rows[0].gap, 1);
  assert.equal(rows[1].wonRate, 0);
  assert.equal(rows[1].live, 0);
  assert.equal(rows[1].gap, null);
});
