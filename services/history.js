// services/history.js - builds REAL price-history series from the price_history SQL table.
const { q } = require("../db");

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const label = (d) => `${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]}`;

// Returns { platform_histories, days } or null when fewer than 2 distinct days have been recorded.
async function buildRealHistory(productKey, platformNames) {
  const rows = await q.dailyPrices(productKey, 30);
  const daysSeen = new Set(rows.map((r) => r.day));
  if (daysSeen.size < 2) return null;

  const first = new Date(Math.min(...[...daysSeen].map((d) => new Date(d + "T00:00:00").getTime())));
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const axis = [];
  for (let d = new Date(first); d <= today; d.setDate(d.getDate() + 1)) axis.push(new Date(d));

  const byPlatform = {};
  for (const r of rows) (byPlatform[r.platform] ||= {})[r.day] = r.price;

  const histories = {};
  for (const name of platformNames) {
    const rec = byPlatform[name] || {};
    let last = null;
    histories[name] = axis.map((d) => {
      if (rec[ymd(d)] != null) last = rec[ymd(d)];          // a price recorded that day
      return { date: label(d), price: last, is_sale: false }; // otherwise carry the last known price (null before first record)
    });
  }
  return { platform_histories: histories, days: axis.length };
}

module.exports = { buildRealHistory };
