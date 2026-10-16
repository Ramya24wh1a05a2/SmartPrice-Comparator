// services/matcher.js - product matching + buy score (ported from app.py)
const { q } = require("../db");

// Load a product (with its platform prices) from SQL in the same shape the frontend expects
async function loadProduct(row) {
  const platforms = {};
  for (const p of await q.pricesForProduct(row.id)) {
    platforms[p.platform] = {
      min: p.min_price, max: p.max_price, typical: p.typical_price, mrp: p.mrp,
      delivery: p.delivery, delivery_fee: p.delivery_fee, offer: p.offer,
      in_stock: !!p.in_stock, rating: p.rating == null ? null : Number(p.rating), reviews: p.reviews, direct_url: p.direct_url,
    };
  }
  return { name: row.name, brand: row.brand, category: row.category, description: row.description, platforms };
}

async function matchProduct(query) {
  const qs = query.toLowerCase().trim();
  const qWords = qs.split(/\s+/).filter((w) => w.length > 1);
  let best = null, bestScore = 0;

  for (const row of await q.allProducts()) {
    const keyWords = row.search_key.split(" ");
    const forward = keyWords.filter((w) => qWords.includes(w)).length;
    const backward = qWords.filter((w) => keyWords.includes(w)).length;
    const score = forward * 2 + backward + (qs.includes(row.search_key) ? 1 : 0);
    if (score > bestScore) { bestScore = score; best = row; }
  }
  return best ? await loadProduct(best) : null; // unknown product: never invent prices
}

const DELIVERY_MINS = {
  "10 Mins": 10, "8-12 Mins": 11, "10 Min": 10, "15-20 Mins": 17, "30-45 Mins": 37,
  "2 Hours": 120, "Same Day": 480, "Next Day": 1440, "2-3 Days": 3000, "3-5 Days": 5000, "4-7 Days": 7000,
};

function computeBuyScore(price, minP, maxP, rating, delivery, inStock, freeDelivery) {
  const range = maxP - minP || 1;
  const priceScore = (1 - (price - minP) / range) * 40;
  const ratingScore = ((rating - 1) / 4) * 25;
  const mins = DELIVERY_MINS[delivery] ?? 480;
  const deliveryScore = Math.max(0, 1 - mins / 2000) * 20;
  const total = priceScore + ratingScore + deliveryScore + (inStock ? 10 : 0) + (freeDelivery ? 5 : 0);
  return Math.min(100, Math.max(0, Math.round(total)));
}

function buildUrls(name) {
  const e = encodeURIComponent(name).replace(/%20/g, "+");
  return {
    Amazon: `https://www.amazon.in/s?k=${e}`, Flipkart: `https://www.flipkart.com/search?q=${e}`,
    BigBasket: `https://www.bigbasket.com/ps/?q=${e}`, Blinkit: `https://blinkit.com/s/?q=${e}`,
    Instamart: `https://www.swiggy.com/instamart/search?query=${e}`, JioMart: `https://www.jiomart.com/search/${e}`,
    Croma: `https://www.croma.com/searchB?q=${e}`, Meesho: `https://www.meesho.com/search?q=${e}`,
    Myntra: `https://www.myntra.com/${e}`, Reliance: `https://www.reliancedigital.in/search?q=${e}`,
    "Apple Store": "https://www.apple.com/in/shop/buy-iphone", Zepto: `https://www.zeptonow.com/search?query=${e}`,
  };
}

module.exports = { matchProduct, computeBuyScore, buildUrls };
