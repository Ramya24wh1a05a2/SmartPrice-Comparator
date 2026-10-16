// services/forecast.js - 30-day price history + 30-day forecast (ported from app.py)
// NOTE: this is a mathematical SIMULATION (trend + weekly sine wave + sale dips), not a trained ML model.

// Small seeded random generator so results stay stable for the same product (like Python's random.seed)
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmt = (d) => `${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]}`;
const addDays = (d, n) => new Date(d.getTime() + n * 86400000);
// Python weekday(): Monday=0 ... Sunday=6
const weekday = (d) => (d.getDay() + 6) % 7;

const TRENDS = { Smartphones: -0.003, Electronics: -0.002, Dairy: 0.001, Grocery: 0.0005, Fashion: -0.001, General: -0.001 };
const PLATFORM_COLORS = {
  Amazon: "#ff9900", Flipkart: "#2874f0", BigBasket: "#84cc16", Blinkit: "#facc15", Zepto: "#a855f7",
  Instamart: "#f97316", JioMart: "#ef4444", Croma: "#6366f1", Meesho: "#ec4899", Myntra: "#d946ef",
  Reliance: "#3b82f6", "Apple Store": "#94a3b8",
};

function generatePriceHistoryAndForecast(basePrice, category, platforms, daysBack = 30, daysForward = 30) {
  const rnd = mulberry32(Math.trunc(basePrice) % 1000);
  const randint = (a, b) => a + Math.floor(rnd() * (b - a + 1));
  const today = new Date();
  const trend = TRENDS[category] ?? -0.001;

  const histories = {};
  for (const [pname, info] of Object.entries(platforms)) {
    const pSeed = [...pname].reduce((s, c) => s + c.charCodeAt(0), 0) % 20;
    const hist = [];
    for (let i = daysBack; i >= 0; i--) {
      const d = addDays(today, -i);
      const dayNum = daysBack - i;
      const trendF = 1 + trend * dayNum;
      const seasonal = 1 - 0.04 * Math.sin((2 * Math.PI * dayNum) / 7);
      const saleF = dayNum % 14 < 2 ? 0.91 : 1.0;
      const weekendF = weekday(d) >= 5 ? 1.02 : 1.0;
      const noise = 1 + (((dayNum * pSeed * 7) % 100) / 100 - 0.5) * 0.03;
      const price = Math.max(info.min, Math.min(info.max,
        Math.round(info.typical * trendF * seasonal * saleF * weekendF * noise)));
      hist.push({ date: fmt(d), price, is_sale: saleF < 1.0 });
    }
    histories[pname] = hist;
  }

  const bestName = Object.keys(platforms).reduce((a, b) => (platforms[a].typical <= platforms[b].typical ? a : b));
  const bestInfo = platforms[bestName];
  const lastPrice = histories[bestName][histories[bestName].length - 1].price;

  const upcomingSaleDay = randint(5, 12);
  const forecast = [];
  const saleAnnotations = [];
  for (let i = 1; i <= daysForward; i++) {
    const d = addDays(today, i);
    const trendF = 1 + trend * i * 0.5;
    const seasonal = 1 - 0.04 * Math.sin((2 * Math.PI * i) / 7);
    const isSale = i >= upcomingSaleDay && i <= upcomingSaleDay + 2;
    const saleF = isSale ? 0.88 : 1.0;
    const weekendF = weekday(d) >= 5 ? 1.015 : 1.0;
    const noise = 1 + (((i * 13) % 100) / 100 - 0.5) * 0.01;
    const price = Math.max(bestInfo.min, Math.round(lastPrice * trendF * seasonal * saleF * weekendF * noise));
    forecast.push({ date: fmt(d), price, is_predicted_sale: isSale });
    if (i === upcomingSaleDay) {
      saleAnnotations.push({ date: fmt(d), price, label: `Sale ~${fmt(d)}: ~${Math.round((1 - saleF) * 100)}% drop` });
    }
  }

  const minForecast = Math.min(...forecast.map((f) => f.price));
  const currentPrice = histories[bestName][histories[bestName].length - 1].price;
  const saleDayName = fmt(addDays(today, upcomingSaleDay));
  const last7Min = Math.min(...histories[bestName].slice(-7).map((h) => h.price));

  let timing;
  if (minForecast < currentPrice * 0.93) {
    timing = {
      recommendation: "WAIT — Sale Coming Soon",
      label: `Price expected to drop ~${Math.round((1 - minForecast / currentPrice) * 100)}% around ${saleDayName} on ${bestName}`,
      color: "orange", icon: "⏳", confidence: randint(72, 88),
    };
  } else if (currentPrice <= last7Min) {
    timing = {
      recommendation: "BUY NOW — At 7-Day Low",
      label: `${bestName} is currently at its lowest price in 7 days. Good time to buy.`,
      color: "green", icon: "🟢", confidence: randint(78, 92),
    };
  } else {
    timing = {
      recommendation: "NEUTRAL — Price Stable",
      label: `No big drop predicted immediately. Next possible sale around ${saleDayName}.`,
      color: "blue", icon: "🔵", confidence: randint(60, 75),
    };
  }

  return {
    platform_histories: histories, platform_colors: PLATFORM_COLORS, best_platform_for_chart: bestName,
    forecast, sale_date_annotations: saleAnnotations, upcoming_sale_day: saleDayName,
    min_forecast_price: minForecast, timing,
    history: histories[bestName], price_forecast: forecast, // legacy keys the frontend still reads
  };
}

module.exports = { generatePriceHistoryAndForecast };
