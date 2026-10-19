"use strict";

const STATUS_GROUP = {
  "Įvykusios": "Įvykusios",
  "Įvykęs": "Įvykusios",
  "Baigtos": "Įvykusios",
  "Baigtas": "Įvykusios",
  "Neįvykusios": "Neįvykusios",
  "Neįvykęs": "Neįvykusios",
  "Atšauktos": "Atšauktos",
  "Atšauktas": "Atšauktos",
};

const WON = "Įvykusios";
const LOST = "Neįvykusios";
const CANCELLED = "Atšauktos";
const LIVE = new Set(["Paskelbtas", "Paskelbtos", "Vykstančios", "Vykstantis"]);

function statusGroup(status) {
  return STATUS_GROUP[status] ?? status;
}

function statusesFor(label) {
  const raw = Object.keys(STATUS_GROUP).filter((status) => STATUS_GROUP[status] === label);
  return raw.length ? raw : [label];
}

function eurPerM2(price, row, itemCount) {
  if (itemCount !== 1 || row.share_sold !== "1/1" || !(row.area_m2 > 0) || price == null) return null;
  return price / row.area_m2;
}

function observe(row, itemCount) {
  const status = statusGroup(row.status);
  return {
    auctionId: row.auction_id,
    status,
    type: row.type ?? null,
    endDay: typeof row.end_date === "string" ? row.end_date.slice(0, 10) : "",
    municipality: row.municipality ?? null,
    settlement: row.settlement ?? null,
    subtype: row.subtype ?? null,
    startingPrice: row.starting_price_eur ?? null,
    highestBid: row.highest_bid_eur ?? null,
    askingEurM2: eurPerM2(row.starting_price_eur, row, itemCount),
    achievedEurM2: status === WON ? eurPerM2(row.highest_bid_eur, row, itemCount) : null,
  };
}

function median(values) {
  const xs = values.filter((value) => value != null && Number.isFinite(value)).sort((a, b) => a - b);
  if (!xs.length) return null;
  const mid = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[mid] : (xs[mid - 1] + xs[mid]) / 2;
}

function weekStart(iso) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const weekday = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() - weekday + 1);
  return date.toISOString().slice(0, 10);
}

function periodOf(endDay, grain) {
  if (!endDay) return "";
  if (grain === "month") return endDay.slice(0, 7);
  if (grain === "week") return weekStart(endDay);
  return endDay;
}

function daysBetween(start, end) {
  const from = Date.parse(`${start}T00:00:00Z`);
  const to = Date.parse(`${end}T00:00:00Z`);
  return Math.round((to - from) / 86400000);
}

function auctionsOf(observations) {
  const map = new Map();
  for (const obs of observations) {
    let entry = map.get(obs.auctionId);
    if (!entry) {
      entry = {
        auctionId: obs.auctionId,
        status: obs.status,
        type: obs.type,
        endDay: obs.endDay,
        startingPrice: obs.startingPrice,
        highestBid: obs.highestBid,
        asking: [],
        achieved: [],
      };
      map.set(obs.auctionId, entry);
    }
    if (obs.askingEurM2 != null) entry.asking.push(obs.askingEurM2);
    if (obs.achievedEurM2 != null) entry.achieved.push(obs.achievedEurM2);
  }
  return [...map.values()];
}

function outcome(auctions) {
  let won = 0;
  let lost = 0;
  let cancelled = 0;
  let live = 0;
  for (const auction of auctions) {
    if (auction.status === WON) won += 1;
    else if (auction.status === LOST) lost += 1;
    else if (auction.status === CANCELLED) cancelled += 1;
    else if (LIVE.has(auction.status)) live += 1;
  }
  const decided = won + lost;
  return { won, lost, cancelled, live, decided, wonRate: decided ? won / decided : null };
}

function priceStats(auctions) {
  const starting = [];
  const achieved = [];
  const premium = [];
  let atStart = 0;
  for (const auction of auctions) {
    if (auction.startingPrice != null) starting.push(auction.startingPrice);
    if (auction.status !== WON || auction.highestBid == null || !(auction.startingPrice > 0)) continue;
    achieved.push(auction.highestBid);
    premium.push(auction.highestBid / auction.startingPrice);
    if (auction.highestBid === auction.startingPrice) atStart += 1;
  }
  return {
    startingMedian: median(starting),
    achievedMedian: median(achieved),
    premiumMedian: median(premium),
    soldAtStart: premium.length ? atStart / premium.length : null,
  };
}

function summarize(observations, asOf) {
  const auctions = auctionsOf(observations);
  const bySubtype = new Map();
  for (const obs of observations) {
    if (obs.askingEurM2 == null && obs.achievedEurM2 == null) continue;
    const subtype = obs.subtype || "Nenurodyta";
    let bucket = bySubtype.get(subtype);
    if (!bucket) {
      bucket = { subtype, asking: [], achieved: [] };
      bySubtype.set(subtype, bucket);
    }
    if (obs.askingEurM2 != null) bucket.asking.push(obs.askingEurM2);
    if (obs.achievedEurM2 != null) bucket.achieved.push(obs.achievedEurM2);
  }
  const rounds = new Map();
  let endingWithin7Days = 0;
  for (const auction of auctions) {
    if (!LIVE.has(auction.status)) continue;
    const type = auction.type || "Nenurodyta";
    rounds.set(type, (rounds.get(type) ?? 0) + 1);
    if (asOf && auction.endDay && daysBetween(asOf, auction.endDay) >= 0 && daysBetween(asOf, auction.endDay) < 7) {
      endingWithin7Days += 1;
    }
  }
  return {
    items: observations.length,
    auctions: auctions.length,
    ...outcome(auctions),
    ...priceStats(auctions),
    eurM2: [...bySubtype.values()]
      .map((bucket) => ({
        subtype: bucket.subtype,
        askingMedian: median(bucket.asking),
        achievedMedian: median(bucket.achieved),
        askingN: bucket.asking.length,
        achievedN: bucket.achieved.length,
      }))
      .sort((a, b) => b.askingN + b.achievedN - (a.askingN + a.achievedN) || a.subtype.localeCompare(b.subtype, "lt")),
    rounds: [...rounds.entries()]
      .map(([type, n]) => ({ type, n }))
      .sort((a, b) => b.n - a.n || a.type.localeCompare(b.type, "lt")),
    endingWithin7Days,
  };
}

function byTime(observations, grain) {
  const groups = new Map();
  for (const auction of auctionsOf(observations)) {
    const period = periodOf(auction.endDay, grain);
    if (!period) continue;
    let group = groups.get(period);
    if (!group) groups.set(period, (group = []));
    group.push(auction);
  }
  return [...groups.entries()]
    .map(([period, auctions]) => {
      const counts = outcome(auctions);
      const prices = priceStats(auctions);
      return {
        period,
        auctions: auctions.length,
        won: counts.won,
        decided: counts.decided,
        wonRate: counts.wonRate,
        startingMedian: prices.startingMedian,
        achievedMedian: prices.achievedMedian,
        premiumMedian: prices.premiumMedian,
        askingMedian: median(auctions.flatMap((auction) => auction.asking)),
        achievedM2Median: median(auctions.flatMap((auction) => auction.achieved)),
      };
    })
    .sort((a, b) => (a.period < b.period ? 1 : -1));
}

function indexAuctions(observations, placeKey) {
  const map = new Map();
  for (const obs of observations) {
    const place = obs[placeKey] || "Nenurodyta";
    const key = `${place}\0${obs.auctionId}`;
    let entry = map.get(key);
    if (!entry) {
      entry = {
        place,
        auctionId: obs.auctionId,
        status: obs.status,
        startingPrice: obs.startingPrice,
        highestBid: obs.highestBid,
        asking: [],
        achieved: [],
      };
      map.set(key, entry);
    }
    if (obs.askingEurM2 != null) entry.asking.push(obs.askingEurM2);
    if (obs.achievedEurM2 != null) entry.achieved.push(obs.achievedEurM2);
  }
  const byPlaceName = new Map();
  for (const entry of map.values()) {
    let list = byPlaceName.get(entry.place);
    if (!list) byPlaceName.set(entry.place, (list = []));
    list.push(entry);
  }
  return byPlaceName;
}

function byPlace(marketObservations, currentObservations, placeKey, rankByGap = false) {
  const market = indexAuctions(marketObservations, placeKey);
  const current = indexAuctions(currentObservations, placeKey);
  return [...new Set([...market.keys(), ...current.keys()])]
    .map((place) => {
      const history = market.get(place) ?? [];
      const live = (current.get(place) ?? []).filter((auction) => LIVE.has(auction.status));
      const counts = outcome(history);
      const achievedMedian = median(history.flatMap((auction) => auction.achieved));
      const liveAskingMedian = median(live.flatMap((auction) => auction.asking));
      const gap = achievedMedian > 0 && liveAskingMedian != null ? liveAskingMedian / achievedMedian - 1 : null;
      return {
        place,
        auctions: history.length,
        live: live.length,
        won: counts.won,
        decided: counts.decided,
        wonRate: counts.wonRate,
        achievedMedian,
        liveAskingMedian,
        gap,
      };
    })
    .sort((a, b) => {
      if (!rankByGap || (a.gap == null && b.gap == null)) {
        return b.auctions - a.auctions || a.place.localeCompare(b.place, "lt");
      }
      if (a.gap == null) return 1;
      if (b.gap == null) return -1;
      return a.gap - b.gap || b.auctions - a.auctions;
    });
}

globalThis.AuctionStats = {
  statusGroup,
  statusesFor,
  observe,
  median,
  weekStart,
  summarize,
  byTime,
  byPlace,
};
