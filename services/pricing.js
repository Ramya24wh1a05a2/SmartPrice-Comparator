// services/pricing.js - ONE place that decides which prices we can honestly show for a query.
// Used by the search route AND the background alert checker.
const { q } = require("../db");
const { matchProduct } = require("./matcher");
const { fetchLivePrices, productKey } = require("./live");

// Returns { product, platforms, hasLive, error, key }  (product is null when nothing accurate exists)
async function getPriceData(query) {
  const key = productKey(query);
  const dbProduct = await matchProduct(query);
  const live = await fetchLivePrices(query);
  const stores = live.platforms;
  const hasLive = Object.keys(stores).length > 0;

  if (hasLive) {
    const title = query.replace(/\w\S*/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
    const product = dbProduct || { name: title, brand: "Various", category: "General", description: `Live prices for '${title}' from Indian stores.` };
    const platforms = {};
    const toRecord = {};
    for (const [name, l] of Object.entries(stores)) {
      platforms[name] = {
        min: Math.round(l.price * 0.9), max: Math.round(l.price * 1.1), typical: l.price, mrp: l.mrp,
        delivery: l.delivery || "Check site", delivery_fee: /free/i.test(l.delivery) ? "Free" : "Check site",
        offer: l.offer || "", in_stock: true, rating: l.rating, reviews: l.reviews, direct_url: l.url,
      };
      toRecord[name] = l.price;
    }
    // Save this fresh lookup so charts can show REAL history over time
    if (live.fresh) { try { await q.recordPrices(key, toRecord); } catch (e) { console.warn("[HISTORY] save failed:", e.message); } }
    return { product, platforms, hasLive: true, error: null, key };
  }
  if (dbProduct) return { product: dbProduct, platforms: dbProduct.platforms, hasLive: false, error: live.error, key };
  return { product: null, platforms: {}, hasLive: false, error: live.error || "NO_RESULTS", key };
}

module.exports = { getPriceData };
