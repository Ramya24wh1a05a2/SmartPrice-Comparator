// db.js - MySQL layer (mysql2 connection pool). Every query is async.
const fs = require("fs");
const path = require("path");
const mysql = require("mysql2/promise");
const bcrypt = require("bcryptjs");

let pool;
const DB_NAME = () => process.env.DB_NAME || "smartprice";

async function init() {
  const conn = {
    host: process.env.DB_HOST || "localhost",
    port: parseInt(process.env.DB_PORT || "3306", 10),
    user: process.env.DB_USER || "root",
    password: process.env.DB_PASSWORD || "",
  };

  // 1) create the database if it does not exist yet
  const admin = await mysql.createConnection(conn);
  await admin.query(`CREATE DATABASE IF NOT EXISTS \`${DB_NAME()}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`);
  await admin.end();

  // 2) connection pool
  pool = mysql.createPool({ ...conn, database: DB_NAME(), waitForConnections: true, connectionLimit: 10, charset: "utf8mb4" });

  // 3) create tables
  const schema = fs.readFileSync(path.join(__dirname, "schema.sql"), "utf8");
  for (const stmt of schema.split(";").map((s) => s.replace(/--.*$/gm, "").trim()).filter(Boolean)) {
    await pool.query(stmt);
  }

  await seedProducts();
  await seedAdmin();
  console.log(`[DB] Connected to MySQL database "${DB_NAME()}" at ${conn.host}:${conn.port}`);
}

async function seedProducts() {
  const [[{ n }]] = await pool.query("SELECT COUNT(*) AS n FROM products");
  if (n > 0) return;
  const seed = JSON.parse(fs.readFileSync(path.join(__dirname, "data", "products_seed.json"), "utf8"));
  const c = await pool.getConnection();
  try {
    await c.beginTransaction();
    for (const [key, p] of Object.entries(seed)) {
      const [r] = await c.execute(
        "INSERT INTO products (search_key, name, brand, category, description) VALUES (?, ?, ?, ?, ?)",
        [key, p.name, p.brand, p.category, p.description || ""]);
      for (const [platform, d] of Object.entries(p.platforms)) {
        await c.execute(
          `INSERT INTO platform_prices (product_id, platform, min_price, max_price, typical_price, mrp, delivery,
             delivery_fee, offer, in_stock, rating, reviews, direct_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,
          [r.insertId, platform, d.min, d.max, d.typical, d.mrp, d.delivery, d.delivery_fee, d.offer,
           d.in_stock ? 1 : 0, d.rating, d.reviews, d.direct_url || null]);
      }
    }
    await c.commit();
    console.log(`[DB] Seeded ${Object.keys(seed).length} products`);
  } catch (e) { await c.rollback(); throw e; } finally { c.release(); }
}

// Optional admin login, created only if ADMIN_EMAIL and ADMIN_PASSWORD are set in .env
async function seedAdmin() {
  const email = (process.env.ADMIN_EMAIL || "").toLowerCase();
  const pass = process.env.ADMIN_PASSWORD;
  if (!email || !pass) return;
  const [rows] = await pool.execute("SELECT id FROM users WHERE email = ?", [email]);
  if (rows.length) return;
  await pool.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
    ["Admin User", email, bcrypt.hashSync(pass, 10)]);
  console.log(`[DB] Admin account created: ${email}`);
}

const one = async (sql, params) => (await pool.execute(sql, params))[0][0] || null;
const all = async (sql, params = []) => (await pool.execute(sql, params))[0];
const pad = (n) => String(n).padStart(2, "0");
const sqlDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

const q = {
  // users
  userByEmail: (email) => one("SELECT * FROM users WHERE email = ?", [email]),
  userById: (id) => one("SELECT id, name, email FROM users WHERE id = ?", [id]),
  createUser: async (name, email, hash) => (await pool.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", [name, email, hash]))[0].insertId,

  // products
  allProducts: () => all("SELECT * FROM products"),
  pricesForProduct: (id) => all("SELECT * FROM platform_prices WHERE product_id = ?", [id]),

  // alerts
  addAlert: (userId, email, productName, query, target, best, platform) =>
    pool.execute(`INSERT INTO price_alerts (user_id, email, product_name, search_query, target_price, current_best, best_platform)
                  VALUES (?,?,?,?,?,?,?)`, [userId, email, productName, query, target, best || null, platform || ""]),
  alertsForUser: (userId) => all("SELECT * FROM price_alerts WHERE user_id = ? ORDER BY set_at DESC", [userId]),
  pendingAlerts: () => all("SELECT * FROM price_alerts WHERE fulfilled = 0"),
  markAlertDone: (id) => pool.execute("UPDATE price_alerts SET fulfilled = 1, notified_at = ? WHERE id = ?", [sqlDate(new Date()), id]),

  // search log
  addSearch: (userId, query, productName) => pool.execute("INSERT INTO search_history (user_id, query, product_name) VALUES (?,?,?)", [userId, query, productName]),

  // real price history
  recordPrices: async (productKey, platformPrices) => {
    const now = sqlDate(new Date());
    for (const [platform, price] of Object.entries(platformPrices)) {
      await pool.execute("INSERT INTO price_history (product_key, platform, price, recorded_at) VALUES (?,?,?,?)", [productKey, platform, price, now]);
    }
  },
  // cheapest price per platform per day, for the last N days
  dailyPrices: (productKey, days) => {
    const since = new Date(); since.setDate(since.getDate() - days); since.setHours(0, 0, 0, 0);
    return all(`SELECT platform, DATE_FORMAT(recorded_at, '%Y-%m-%d') AS day, MIN(price) AS price
                FROM price_history WHERE product_key = ? AND recorded_at >= ?
                GROUP BY platform, day ORDER BY day`, [productKey, sqlDate(since)]);
  },
};

module.exports = { init, q };
