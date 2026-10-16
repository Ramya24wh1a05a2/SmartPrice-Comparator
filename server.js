// server.js - SmartPrice (Node.js + Express + MySQL)
require("dotenv").config();
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const express = require("express");
const cors = require("cors");
const cookieSession = require("cookie-session");
const bcrypt = require("bcryptjs");

const { init: initDb, q } = require("./db");
const { computeBuyScore, buildUrls } = require("./services/matcher");
const { generatePriceHistoryAndForecast } = require("./services/forecast");
const { getPriceData } = require("./services/pricing");
const { buildRealHistory } = require("./services/history");
const { getCacheStats } = require("./services/live");
const { checkAlerts, startAlertJob } = require("./services/alerts");
const mailer = require("./services/mailer");

const app = express();
const PORT = process.env.PORT || 5000;
const THIRTY_DAYS = 30 * 24 * 60 * 60 * 1000;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next); // async error handling

let secret = process.env.SESSION_SECRET;
if (!secret) {
  secret = crypto.randomBytes(32).toString("hex");
  console.warn("[WARN] SESSION_SECRET not set - users will be logged out whenever the server restarts.");
}

app.use(cors({ origin: true, credentials: true }));
app.use(express.json());
app.use(cookieSession({ name: "sp_session", keys: [secret], maxAge: THIRTY_DAYS, httpOnly: true, sameSite: "lax" }));

// ── Auth helpers ─────────────────────────────────────────────────────────────
const loginRequired = wrap(async (req, res, next) => {
  const u = req.session?.user && (await q.userById(req.session.user.id));
  if (!u) { req.session = null; return res.status(401).json({ error: "Unauthorized" }); }
  req.user = u;
  next();
});
const startSession = (req, u) => { req.session.user = { id: u.id, email: u.email, name: u.name }; };

// ── Pages ────────────────────────────────────────────────────────────────────
const loginHtml = fs.readFileSync(path.join(__dirname, "public", "login.html"), "utf8");
const dashboardHtml = fs.readFileSync(path.join(__dirname, "public", "dashboard.html"), "utf8");

app.get("/", wrap(async (req, res) => {
  if (req.session?.user && (await q.userById(req.session.user.id))) return res.redirect("/dashboard");
  res.type("html").send(loginHtml);
}));

app.get("/dashboard", wrap(async (req, res) => {
  const u = req.session?.user && (await q.userById(req.session.user.id));
  if (!u) return res.redirect("/");
  // "<" is escaped so a user's name can never break out of the <script> tag
  const userJson = JSON.stringify({ email: u.email, name: u.name }).replace(/</g, "\\u003c");
  res.type("html").send(dashboardHtml.replace("{{ user|tojson }}", userJson));
}));

// ── Auth API ─────────────────────────────────────────────────────────────────
app.post("/api/register", wrap(async (req, res) => {
  const name = String(req.body.name || "").trim();
  const email = String(req.body.email || "").trim().toLowerCase();
  const pwd = String(req.body.password || "").trim();
  if (!name || !email || !pwd) return res.json({ success: false, message: "All fields required." });
  if (!EMAIL_RE.test(email)) return res.json({ success: false, message: "Enter a valid email." });
  if (pwd.length < 8) return res.json({ success: false, message: "Password must be 8+ characters." });
  if (await q.userByEmail(email)) return res.json({ success: false, message: "Account already exists." });

  const id = await q.createUser(name, email, bcrypt.hashSync(pwd, 10));
  startSession(req, { id, email, name });
  res.json({ success: true, name, redirect: "/dashboard" });
}));

app.post("/api/login", wrap(async (req, res) => {
  const email = String(req.body.email || "").trim().toLowerCase();
  const pwd = String(req.body.password || "").trim();
  if (!email || !pwd) return res.json({ success: false, message: "Email and password required." });
  const u = await q.userByEmail(email);
  if (!u) return res.json({ success: false, message: "No account found." });
  if (!bcrypt.compareSync(pwd, u.password_hash)) return res.json({ success: false, message: "Incorrect password." });
  startSession(req, u);
  res.json({ success: true, name: u.name, redirect: "/dashboard" });
}));

app.post("/api/logout", (req, res) => { req.session = null; res.json({ success: true }); });

// ── Search ───────────────────────────────────────────────────────────────────
app.post("/api/search", loginRequired, wrap(async (req, res) => {
  const query = String(req.body.query || "").trim();
  if (!query) return res.json({ success: false, message: "Please enter a product name." });

  // Live prices first, stored prices only as a fallback, never invented prices
  const data = await getPriceData(query);
  await q.addSearch(req.user.id, query, data.product ? data.product.name : null);
  req.session.lastQuery = query;                       // price alerts use this to re-check the same product later

  if (!data.product) {
    const why = data.error === "NO_KEY"
      ? "Live prices are not set up yet. Add SERPAPI_KEY to your .env file (free key from serpapi.com) so any product can be priced."
      : String(data.error).startsWith("FAILED") ? "The live price service failed. Please try again later."
      : "No matching listings were found. Try a more specific product name.";
    return res.json({ success: false, message: `No accurate prices available for "${query}". ${why}` });
  }

  const { product, platforms, hasLive, key } = data;
  const fallbackUrls = buildUrls(product.name);

  const pricesOut = {};
  for (const [pname, p] of Object.entries(platforms)) {
    const current = p.typical;
    pricesOut[pname] = {
      min: p.min, max: p.max, current, mrp: p.mrp, delivery: p.delivery, delivery_fee: p.delivery_fee,
      offer: p.offer || "", in_stock: p.in_stock, rating: p.rating || 0, reviews: p.reviews || 0,
      buy_score: computeBuyScore(current, p.min, p.max, p.rating || 3, p.delivery, p.in_stock, String(p.delivery_fee).toLowerCase() === "free"),
      url: p.direct_url || fallbackUrls[pname] || `https://www.bing.com/search?q=${encodeURIComponent(product.name + " " + pname + " buy")}`,
      price_source: hasLive ? "live" : "db",
    };
  }

  const sorted = Object.entries(pricesOut).sort((a, b) => a[1].current - b[1].current);
  const sortedPrices = Object.fromEntries(sorted);
  const bestPlatform = sorted[0][0];
  const bestPrice = sorted[0][1].current;
  const maxPrice = Math.max(...sorted.map(([, v]) => v.current));
  const liveCount = hasLive ? sorted.length : 0;

  // Forecast is always a simulation. History is REAL once >= 2 days of live prices are saved in SQL.
  const pred = generatePriceHistoryAndForecast(bestPrice, product.category, platforms);
  let historyReal = false;
  if (hasLive) {
    const real = await buildRealHistory(key, Object.keys(pricesOut));
    if (real) {
      pred.platform_histories = real.platform_histories;
      pred.history = real.platform_histories[bestPlatform].filter((h) => h.price != null);
      historyReal = true;
    }
  }

  const fmt = (n) => `₹${n.toLocaleString("en-IN")}`;
  const tips = [
    liveCount > 0 ? `🟢 Live prices from ${liveCount} store(s), fetched just now or within the last hour.` : "📦 Live prices unavailable: showing stored reference prices.",
    `Best deal on ${bestPlatform} at ${fmt(bestPrice)}. MRP: ${fmt(sortedPrices[bestPlatform].mrp)}.`,
    `Next predicted sale around ${pred.upcoming_sale_day}. Confidence: ${pred.timing.confidence}% (simulated).`,
    "Buy Score ranks platforms by price + delivery speed + rating + stock.",
  ];

  res.json({
    success: true, product: product.name, brand: product.brand, category: product.category,
    description: product.description || "", prices: sortedPrices,
    best_platform: bestPlatform, best_price: bestPrice, max_price: maxPrice, savings: maxPrice - bestPrice,
    live_count: liveCount, db_count: sorted.length - liveCount,
    price_history: pred.history, price_forecast: pred.forecast,
    platform_histories: pred.platform_histories, platform_colors: pred.platform_colors,
    sale_date_annotations: pred.sale_date_annotations, timing: pred.timing, upcoming_sale: pred.upcoming_sale_day,
    history_simulated: !historyReal, forecast_simulated: true,
    scraped_at: new Date().toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: true }),
    ai_tip: tips[Math.floor(new Date().getSeconds() / 15) % tips.length],
  });
}));

// ── Price alerts ─────────────────────────────────────────────────────────────
app.post("/api/price_alert", loginRequired, wrap(async (req, res) => {
  const b = req.body;
  if (!b.target_price) return res.json({ success: false, message: "Target price is required." });
  const target = Math.trunc(Number(b.target_price));
  if (!Number.isFinite(target) || target <= 0) return res.json({ success: false, message: "Invalid target price." });

  const productName = String(b.product_name || "this product").slice(0, 250);
  const bestPrice = Math.trunc(Number(b.best_price)) || 0;
  const bestPlatform = String(b.best_platform || "").slice(0, 60);
  const email = String(b.email_override || "").trim() || req.user.email;
  if (!EMAIL_RE.test(email)) return res.json({ success: false, message: "Invalid email address." });

  const searchQuery = req.session.lastQuery || productName;   // lets the background job re-check this product
  await q.addAlert(req.user.id, email, productName, searchQuery.slice(0, 250), target, bestPrice, bestPlatform);

  const sent = await mailer.sendAlertConfirmation(email, productName, target, bestPrice || target, bestPlatform);
  const fmt = target.toLocaleString("en-IN");
  res.json({
    success: true,
    message: sent
      ? `Alert set for ₹${fmt}! Confirmation email sent to ${email}.`
      : `Alert saved for ₹${fmt}. (Email delivery failed - check server config.)`,
  });
}));

app.get("/api/my_alerts", loginRequired, wrap(async (req, res) => res.json({ success: true, alerts: await q.alertsForUser(req.user.id) })));

// ── Admin/debug endpoints ────────────────────────────────────────────────────
app.post("/api/check_alerts", loginRequired, wrap(async (req, res) => res.json({ success: true, ...(await checkAlerts()) })));
app.get("/api/cache_stats", loginRequired, (req, res) => res.json(getCacheStats()));

app.get("/api/test_email", loginRequired, wrap(async (req, res) => {
  const ok = await mailer.sendEmail(req.user.email, "SmartPrice — SMTP test", `<p>SMTP is working! Sent to <b>${req.user.email}</b>.</p>`);
  const c = mailer.cfg();
  res.json({ EMAIL_ENABLED: c.enabled, EMAIL_HOST: c.host, EMAIL_PORT: c.port, EMAIL_USER: c.user, EMAIL_PASS: c.pass ? "****" : "NOT SET", sent_to: req.user.email, result: ok ? "SUCCESS" : "FAILED - check server terminal" });
}));

// ── Error handler ────────────────────────────────────────────────────────────
app.use((err, req, res, next) => {
  console.error("[ERROR]", err);
  res.status(500).json({ success: false, message: "Server error. Please try again." });
});

// ── Start ────────────────────────────────────────────────────────────────────
initDb()
  .then(() => {
    startAlertJob();
    app.listen(PORT, () => console.log(`SmartPrice running on http://localhost:${PORT}`));
  })
  .catch((err) => {
    console.error("\n[FATAL] Could not connect to MySQL:", err.message);
    console.error("Check that MySQL is running and DB_HOST / DB_USER / DB_PASSWORD in your .env are correct.\n");
    process.exit(1);
  });
