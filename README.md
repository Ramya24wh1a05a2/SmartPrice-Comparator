# SmartPrice: Intelligent Price Comparison and Price-Drop Alert System

SmartPrice helps shoppers compare product listings and prices across Indian online stores, identify potential deals, and receive email alerts when prices reach their target.

Built using **Node.js, Express.js, MySQL, and SerpAPI**.

## Highlights

- **Live price comparison** using Google Shopping results through SerpAPI.
- **Direct store links** to verify product listings and prices before purchasing.
- **Automated price-drop alerts** using scheduled background jobs and email notifications.
- **Price history tracking** with MySQL and interactive charts.
- **Transparent price data** with live listings and stored reference prices clearly distinguished.

## Features

- Highlights the cheapest available listing and calculates potential savings.
- Displays product listings, store details, and a Buy Score.
- Interactive charts for price history, current store prices, and prototype forecasts.
- User registration, login, and session-based authentication.
- Price alerts with email notifications.
- 60-minute caching to reduce API calls and improve performance.
- Stored reference prices as a fallback when live data is unavailable.

## Tech Stack

| Area | Technology |
|---|---|
| Backend | Node.js, Express.js |
| Database | MySQL, mysql2 |
| Authentication | bcryptjs, cookie-session |
| Live price listings | SerpAPI, Google Shopping |
| Background jobs | node-cron |
| Email notifications | Nodemailer, Gmail SMTP |
| Frontend | HTML, CSS, JavaScript |
| Charts | Chart.js |
| Configuration | dotenv |

## How It Works

1. The user searches for a product through the web interface.
2. Express.js handles the request and verifies the user's session.
3. SerpAPI retrieves available Google Shopping listings.
4. The application filters listings, removes price outliers, and selects the cheapest listing per store.
5. If live results are unavailable, stored reference prices may be displayed with a clear label.
6. Retrieved live prices are saved in MySQL for price history.
7. Users can view price comparisons, charts, and prototype forecasts.
8. A scheduled background job checks price alerts and sends email notifications when the configured target is reached.

## Reliability and Limitations

- Product relevance filtering helps remove unrelated listings.
- Price outlier filtering helps exclude suspiciously priced accessories and bundles.
- Live prices and stored reference prices are labelled separately.
- Direct store links allow users to verify listings before purchasing.
- Price history uses saved data when sufficient records are available; simulated history is labelled accordingly.
- Price forecasts are experimental and are not guaranteed to predict future prices accurately.
- Final prices may vary based on seller, product variant, delivery location, and available offers.

## Database

The application uses MySQL to store user accounts, product reference prices, price alerts, search history, and price history.

The database schema is provided in `schema.sql`, with example queries in `useful_queries.sql`.

## Getting Started

### Prerequisites

- Node.js 18 or newer
- MySQL Server
- A SerpAPI API key for live product listings
- Gmail App Password if email notifications are enabled

### Installation

Clone your repository and install the dependencies:

```bash
git clone https://github.com/YOUR_USERNAME/smartprice.git
cd smartprice
npm install
```

Create your environment file.

**Windows:**

```powershell
copy .env.example .env
```

Edit `.env` and configure the required settings:

```env
PORT=5000
SESSION_SECRET=your_long_random_secret

DB_HOST=localhost
DB_PORT=3306
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password
DB_NAME=smartprice

SERPAPI_KEY=your_serpapi_key

EMAIL_ENABLED=false
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_gmail_app_password
EMAIL_FROM=SmartPrice
```

Use your actual credentials locally. Never commit `.env` or expose API keys and passwords in your repository.

Start the application:

```bash
npm start
```

Open [http://localhost:5000](http://localhost:5000) and register an account.

*Note: Database creation and table initialization depend on the application's implemented startup logic.*

## API Routes

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register` | Register a user |
| POST | `/api/login` | Log in |
| POST | `/api/logout` | Log out |
| POST | `/api/search` | Compare product prices |
| POST | `/api/price_alert` | Create a price alert |
| GET | `/api/my_alerts` | View personal alerts |
| POST | `/api/check_alerts` | Trigger an alert check for testing |
| GET | `/api/cache_stats` | View price cache statistics |
| GET | `/api/test_email` | Test email delivery |

Protected routes require appropriate authentication. Administrative and testing endpoints should be secured before deployment.

## Project Structure

```text
smartprice/
├── server.js
├── db.js
├── schema.sql
├── useful_queries.sql
├── data/
│   └── products_seed.json
├── public/
│   ├── login.html
│   └── dashboard.html
├── services/
│   ├── live.js
│   ├── pricing.js
│   ├── history.js
│   ├── alerts.js
│   ├── matcher.js
│   ├── forecast.js
│   └── mailer.js
├── .env.example
├── .gitignore
└── package.json
```

## Future Improvements

- Integrate official retailer APIs for more reliable pricing.
- Improve product variant matching.
- Train and evaluate a forecasting model using saved price history.
- Add automated tests with Jest and Supertest.
- Implement rate limiting and security headers.
- Deploy the application using Render or Railway with a cloud database.

## Author

**V. Ramya**


