// services/live.js - REAL, live prices for any product (no made-up numbers).
//
// Provider: SerpAPI "Google Shopping" (India). One call returns current prices from many Indian stores
// (Amazon, Flipkart, Croma, Reliance, JioMart ...). Needs SERPAPI_KEY in .env (free plan: 100 searches/month,
// sign up at https://serpapi.com). Without a key, this module returns nothing and the app says so honestly.
//
// Results are cached for 60 minutes (same query = same answer, saves your free searches).

const CACHE_TTL_MS = 60 * 60 * 1000;
const cache = new Map();

const PLATFORM_RULES = [
  [/amazon/i, "Amazon"], [/flipkart/i, "Flipkart"], [/croma/i, "Croma"], [/reliance/i, "Reliance"],
  [/jiomart/i, "JioMart"], [/bigbasket/i, "BigBasket"], [/blinkit/i, "Blinkit"], [/zepto/i, "Zepto"],
  [/instamart|swiggy/i, "Instamart"], [/meesho/i, "Meesho"], [/myntra/i, "Myntra"], [/apple/i, "Apple Store"],
];
const platformName = (source) => {
  const s = String(source || "").trim();
  for (const [re, name] of PLATFORM_RULES) if (re.test(s)) return name;
  return s || "Other";
};

const words = (t) => String(t).toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((w) => w.length > 1);
const median = (a) => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };


// ── Links must open the STORE, never Google ──────────────────────────────────
// Each store's own search page. {q} is replaced by the (URL-encoded) product title.
const STORE_SEARCH = {
  Amazon: "https://www.amazon.in/s?k={q}",
  Flipkart: "https://www.flipkart.com/search?q={q}",
  Croma: "https://www.croma.com/searchB?q={q}",
  Reliance: "https://www.reliancedigital.in/search?q={q}",
  JioMart: "https://www.jiomart.com/search/{q}",
  BigBasket: "https://www.bigbasket.com/ps/?q={q}",
  Blinkit: "https://blinkit.com/s/?q={q}",
  Zepto: "https://www.zeptonow.com/search?query={q}",
  Instamart: "https://www.swiggy.com/instamart/search?query={q}",
  Meesho: "https://www.meesho.com/search?q={q}",
  Myntra: "https://www.myntra.com/{q}",
  "Apple Store": "https://www.apple.com/in/search/{q}",
  "Vijay Sales": "https://www.vijaysales.com/search/{q}",
  "Tata CLiQ": "https://www.tatacliq.com/search/?searchCategory=all&text={q}",
  Snapdeal: "https://www.snapdeal.com/search?keyword={q}",
  Ajio: "https://www.ajio.com/search/?text={q}",
  Nykaa: "https://www.nykaa.com/search/result/?q={q}",
  Decathlon: "https://www.decathlon.in/search?Ntt={q}",
  FirstCry: "https://www.firstcry.com/search?q={q}",
  Pepperfry: "https://www.pepperfry.com/site_product/search?q={q}",
  Lenskart: "https://www.lenskart.com/search?q={q}",
  Poorvika: "https://www.poorvika.com/search?q={q}",
  Sangeetha: "https://www.sangeethamobiles.com/search?q={q}",
  "Samsung": "https://www.samsung.com/in/search/?searchvalue={q}",
  "OnePlus": "https://www.oneplus.in/search?keyword={q}",
};
const isGoogleUrl = (u) => { try { return /(^|\.)google\./i.test(new URL(u).hostname); } catch { return true; } };
const storeSearchTemplate = (platform) => {
  const key = Object.keys(STORE_SEARCH).find((k) => k.toLowerCase() === String(platform).toLowerCase());
  return key ? STORE_SEARCH[key] : null;
};

// Direct store product link if the data has one; otherwise the store's own search page for this exact product.
function storeUrl(platform, title, link) {
  if (link && !isGoogleUrl(link)) return link;
  const tpl = storeSearchTemplate(platform);
  if (tpl) return tpl.replace("{q}", encodeURIComponent(String(title).slice(0, 90)).replace(/%20/g, "+"));
  return ""; // unknown store: no Google link; the server builds a plain search link for that store name
}

// Keep only listings that are really the product searched (avoids cheap cases/accessories and unrelated items)
function filterRelevant(items, query) {
  const qw = words(query);
  if (!qw.length) return items;
  const hits = (it) => { const tw = new Set(words(it.title)); return qw.filter((w) => tw.has(w)).length / qw.length; };
  let kept = items.filter((it) => hits(it) === 1);                 // all search words in the title
  if (kept.length < 2) kept = items.filter((it) => hits(it) >= 0.6); // else allow 60%+
  if (kept.length >= 3) {                                          // drop price outliers (accessories, bundles)
    const med = median(kept.map((i) => i.price));
    kept = kept.filter((i) => i.price >= med * 0.4 && i.price <= med * 3);
  }
  return kept;
}

async function fromSerpApi(query) {
  const key = process.env.SERPAPI_KEY;
  if (!key) return { items: [], error: "NO_KEY" };
  const endpoint = process.env.SERPAPI_ENDPOINT || "https://serpapi.com/search.json";
  const url = `${endpoint}?engine=google_shopping&q=${encodeURIComponent(query)}&gl=in&hl=en&google_domain=google.co.in&num=40&api_key=${key}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
  if (!res.ok) throw new Error(`SerpAPI HTTP ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  const items = (data.shopping_results || [])
    .map((r) => ({
      title: r.title || "", source: r.source || "", price: Number(r.extracted_price) || 0,
      oldPrice: Number(r.extracted_old_price) || 0, link: r.link || r.product_link || "",
      rating: r.rating ? Number(r.rating) : null, reviews: r.reviews ? Number(r.reviews) : null,
      delivery: r.delivery || "", tag: r.tag || r.extensions?.[0] || "",
    }))
    .filter((r) => r.price > 0 && r.source);
  return { items };
}

// Returns { platforms: { Name: {...} }, error }  - cheapest relevant listing per store
async function fetchLivePrices(query) {
  const key = query.toLowerCase().trim();
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return { ...hit.data, fresh: false };

  let out = { platforms: {}, error: null, fresh: false };
  try {
    const { items, error } = await fromSerpApi(query);
    if (error) { out.error = error; return out; }          // not cached: user may add a key later
    const relevant = filterRelevant(items, query);
    for (const it of relevant) {
      const name = platformName(it.source);
      if (!out.platforms[name] || it.price < out.platforms[name].price) {
        out.platforms[name] = {
          price: it.price, mrp: it.oldPrice > it.price ? it.oldPrice : it.price, url: storeUrl(name, it.title, it.link), title: it.title,
          rating: it.rating, reviews: it.reviews, delivery: it.delivery, offer: it.tag,
        };
      }
    }
    out.fresh = true;
    if (Object.keys(out.platforms).length) cache.set(key, { at: Date.now(), data: out }); // never cache empty results
  } catch (err) {
    console.warn("[LIVE] lookup failed:", err.message);
    out = { platforms: {}, error: "FAILED: " + err.message };
  }
  return out;
}

function getCacheStats() {
  const now = Date.now();
  return {
    provider: process.env.SERPAPI_KEY ? "SerpAPI Google Shopping" : "none (SERPAPI_KEY not set)",
    cached_queries: cache.size,
    entries: [...cache.entries()].map(([k, v]) => ({ query: k, stores: Object.keys(v.data.platforms).length, expires_in_sec: Math.max(0, Math.round((CACHE_TTL_MS - (now - v.at)) / 1000)) })),
  };
}

const productKey = (query) => words(query).join(" ");

module.exports = { storeUrl, productKey, fetchLivePrices, getCacheStats, filterRelevant, platformName };
