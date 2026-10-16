# SmartPrice - Live Price Comparison & Price-Drop Alerts
Node.js + Express + MySQL

Search any product, see live prices from Indian stores, find the cheapest, and get an email when the price drops to your target.

## 1. One-time setup (Windows)

**Install Node.js (LTS)** from https://nodejs.org

**Install MySQL**
1. Download "MySQL Installer" from https://dev.mysql.com/downloads/installer/ (or use XAMPP / WAMP, which include MySQL).
2. Install "MySQL Server". Set a root password and remember it.
3. Check it is running: open Services (Win+R, `services.msc`) and look for "MySQL80" = Running.

## 2. Run the project
    cd smartprice-node
    npm install
    copy .env.example .env      (Mac/Linux: cp .env.example .env)

Open `.env` and set at least:
- `DB_PASSWORD` = your MySQL root password
- `SESSION_SECRET` = any long random text
- `SERPAPI_KEY` = free key from https://serpapi.com (needed for live prices of any product)
- `EMAIL_ENABLED=false` while testing (so no real emails are sent)

Then:
    npm start
Open http://localhost:5000 and register an account. The database `smartprice` and all tables are created automatically.

## 3. Tech stack
| Part | Technology |
|---|---|
| Server / REST API | Node.js, Express |
| Database | MySQL (mysql2 connection pool, async/await) |
| Login | bcryptjs password hashing + signed cookie sessions |
| Live prices | SerpAPI Google Shopping (third-party API), 60-minute cache |
| Background job | node-cron (checks price alerts) |
| Email | Nodemailer (Gmail SMTP) |
| Frontend | HTML, CSS, vanilla JS, Chart.js |

## 4. SQL tables
| Table | Purpose |
|---|---|
| users | accounts (bcrypt hash, unique email) |
| products, platform_prices | stored reference prices (fallback only); platform_prices.product_id is a foreign key |
| price_alerts | user's target prices; fulfilled flag; foreign key to users |
| search_history | what each user searched |
| price_history | every live price fetched (product, store, price, time). Powers the real history chart |

## 5. How prices work (be honest about this in interviews)
1. The user searches. The app asks the live price API for real listings.
2. Listings are filtered: the title must match the search and extreme prices (cases, bundles) are dropped. The cheapest listing per store is kept.
3. If live data is unavailable, stored reference prices are used for known products and are marked "DB".
4. For unknown products with no live data, the app shows NO price (it never invents one).
5. Every fresh live lookup is saved in `price_history`. After 2+ days of data, the history chart shows REAL recorded prices instead of a simulation.
6. The forecast and BUY NOW / WAIT recommendation are still a simulation (trend + weekly cycle + sale dips), not a trained ML model.
7. Prices can differ slightly by seller, pincode and bank offers. Each store row has a link so users can verify.
8. Buy links open the STORE itself, never Google: the store's direct product page when available, otherwise that store's own search page for the exact product title.

## 6. Price-drop alerts
- User sets a target price on the dashboard -> saved in `price_alerts`, confirmation email sent.
- A node-cron job (default every 6 hours, change `ALERT_CRON`) re-checks each product once, and emails the user when the best price is at or below the target. The alert is then marked fulfilled so it is never emailed twice.
- To trigger it manually while testing: send `POST /api/check_alerts` while logged in.
- Each re-check uses one live-price lookup per product, so mind your SerpAPI free quota.

## 7. API routes
    POST /api/register       POST /api/login       POST /api/logout
    POST /api/search         POST /api/price_alert GET  /api/my_alerts
    POST /api/check_alerts   GET  /api/cache_stats GET  /api/test_email

## 8. Project structure
    server.js                 Express app and routes
    db.js                     MySQL pool, creates database/tables, seeds data, all queries
    schema.sql                CREATE TABLE statements
    useful_queries.sql        example SQL (joins, GROUP BY) to practise / show in interviews
    data/products_seed.json   stored reference products
    services/live.js          live price API + cache + result filtering
    services/pricing.js       decides which prices can honestly be shown; saves price_history
    services/history.js       builds real history series from SQL
    services/alerts.js        node-cron alert checker
    services/matcher.js       product matching, buy score
    services/forecast.js      simulated forecast
    services/mailer.js        emails
    public/                   login.html, dashboard.html

## 9. Troubleshooting
- "Could not connect to MySQL": MySQL is not running, or DB_PASSWORD / DB_USER in `.env` is wrong.
- `npm install` says package.json not found: you are in the wrong folder; `cd` into the inner `smartprice-node` folder.
- "No accurate prices available": SERPAPI_KEY is missing/invalid, or the product name is too vague.
- Port busy: set `PORT=3000` in `.env`.
