"""
SmartPrice Comparator — v5.0 LIVE PRICES
  • Real web scraping via scraper.py (Amazon, Flipkart, Blinkit, Zepto,
    BigBasket, JioMart, Croma, Meesho) — parallel threads, 60-min cache
  • Graceful fallback: if scrape fails, uses PRODUCT_DB hardcoded price
  • price_source field tells frontend whether price is live or db
  • /api/cache_stats endpoint for debugging
"""

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, make_response
from flask_cors import CORS
import json, re, time, random, urllib.parse, math, smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from functools import wraps

# ── Email configuration — set these via environment variables or edit directly ──
EMAIL_HOST     = os.environ.get("EMAIL_HOST",  "smtp.gmail.com")
EMAIL_PORT     = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USER     = os.environ.get("EMAIL_USER",  "your_email@gmail.com")   # ← change
EMAIL_PASS     = os.environ.get("EMAIL_PASS",  "qtpv qubo orgf xwyh") # ← change
EMAIL_FROM     = os.environ.get("EMAIL_FROM",  "SmartPrice <your_email@gmail.com>")
EMAIL_ENABLED  = os.environ.get("EMAIL_ENABLED", "true").lower() == "true"

# Live scraper — graceful import so app still works if scraper.py is missing
try:
    from scraper import scrape_all_platforms, get_cache_stats
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False
    def scrape_all_platforms(q, platforms=None): return {}
    def get_cache_stats(): return {}

app = Flask(__name__)
app.secret_key = "smartprice_v3_2024"
app.config["SESSION_PERMANENT"]          = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # stay logged in 30 days
CORS(app, supports_credentials=True)

USERS = {
    "admin@smartprice.in":{"password": "Admin@999", "name": "Admin User"},
}

def build_urls(name):
    """Fallback search URLs — used only when no direct_url is set in PRODUCT_DB."""
    q = urllib.parse.quote_plus(name)
    return {
        "Amazon":     f"https://www.amazon.in/s?k={q}",
        "Flipkart":   f"https://www.flipkart.com/search?q={q}",
        "BigBasket":  f"https://www.bigbasket.com/ps/?q={q}",
        "Blinkit":    f"https://blinkit.com/s/?q={q}",
        "Instamart":  f"https://www.swiggy.com/instamart/search?query={q}",
        "JioMart":    f"https://www.jiomart.com/search/{q}",
        "Croma":      f"https://www.croma.com/searchB?q={q}",
        "Meesho":     f"https://www.meesho.com/search?q={q}",
        "Myntra":     f"https://www.myntra.com/{q}",
        "Reliance":   f"https://www.reliancedigital.in/search?q={q}",
        "Apple Store":f"https://www.apple.com/in/shop/buy-iphone",
        "Zepto":      f"https://www.zeptonow.com/search?query={q}",
    }

def generate_price_history_and_forecast(base_price, category, platforms_data, days_back=30, days_forward=30):
    """Generate per-platform history + forecast with exact sale date annotations."""
    random.seed(int(base_price) % 1000)
    today = datetime.now()

    trends = {
        "Smartphones": -0.003, "Electronics": -0.002,
        "Dairy": 0.001, "Grocery": 0.0005,
        "Fashion": -0.001, "General": -0.001,
    }
    trend = trends.get(category, -0.001)

    # Per-platform history (each platform gets its own price line)
    platform_colors = {
        "Amazon": "#ff9900", "Flipkart": "#2874f0", "BigBasket": "#84cc16",
        "Blinkit": "#facc15", "Zepto": "#a855f7", "Instamart": "#f97316",
        "JioMart": "#ef4444", "Croma": "#6366f1", "Meesho": "#ec4899",
        "Myntra": "#d946ef", "Reliance": "#3b82f6", "Apple Store": "#94a3b8",
    }

    all_platform_histories = {}
    for pname, pinfo in platforms_data.items():
        p_history = []
        p_seed = sum(ord(c) for c in pname) % 20
        for i in range(days_back, -1, -1):
            d = today - timedelta(days=i)
            day_num = days_back - i
            dow = d.weekday()
            trend_f = 1 + (trend * day_num)
            seasonal = 1 - 0.04 * math.sin(2 * math.pi * day_num / 7)
            sale_f = 0.91 if (day_num % 14 < 2) else 1.0
            weekend_f = 1.02 if dow >= 5 else 1.0
            noise = 1 + (((day_num * p_seed * 7) % 100) / 100 - 0.5) * 0.03
            price = max(pinfo["min"], min(pinfo["max"],
                round(pinfo["typical"] * trend_f * seasonal * sale_f * weekend_f * noise)))
            p_history.append({
                "date": d.strftime("%d %b"),
                "price": price,
                "is_sale": sale_f < 1.0,
            })
        all_platform_histories[pname] = p_history

    # Best platform forecast with EXACT date annotations
    best_pname = min(platforms_data.keys(), key=lambda p: platforms_data[p]["typical"])
    best_info = platforms_data[best_pname]
    last_price = all_platform_histories[best_pname][-1]["price"]

    upcoming_sale_day = random.randint(5, 12)
    forecast = []
    sale_date_annotations = []  # exact dates when price drops

    for i in range(1, days_forward + 1):
        d = today + timedelta(days=i)
        dow = d.weekday()
        trend_f = 1 + (trend * i * 0.5)
        seasonal = 1 - 0.04 * math.sin(2 * math.pi * i / 7)
        is_sale = upcoming_sale_day <= i <= upcoming_sale_day + 2
        sale_f = 0.88 if is_sale else 1.0
        weekend_f = 1.015 if dow >= 5 else 1.0
        noise = 1 + (((i * 13) % 100) / 100 - 0.5) * 0.01
        price = max(best_info["min"], round(last_price * trend_f * seasonal * sale_f * weekend_f * noise))
        date_str = d.strftime("%d %b")
        forecast.append({
            "date": date_str,
            "price": price,
            "is_predicted_sale": is_sale,
        })
        if i == upcoming_sale_day:
            sale_date_annotations.append({
                "date": date_str,
                "price": price,
                "label": f"Sale ~{date_str}: ~{round((1 - sale_f) * 100)}% drop"
            })

    min_forecast = min(f["price"] for f in forecast)
    current_price = all_platform_histories[best_pname][-1]["price"]
    sale_day_name = (today + timedelta(days=upcoming_sale_day)).strftime("%d %b")

    if min_forecast < current_price * 0.93:
        timing = {
            "recommendation": "WAIT — Sale Coming Soon",
            "label": f"Price expected to drop ~{round((1 - min_forecast/current_price)*100)}% around {sale_day_name} on {best_pname}",
            "color": "orange", "icon": "⏳",
            "confidence": random.randint(72, 88)
        }
    elif current_price <= min(h["price"] for h in all_platform_histories[best_pname][-7:]):
        timing = {
            "recommendation": "BUY NOW — At 7-Day Low",
            "label": f"{best_pname} is currently at its lowest price in 7 days. Good time to buy.",
            "color": "green", "icon": "🟢",
            "confidence": random.randint(78, 92)
        }
    else:
        timing = {
            "recommendation": "NEUTRAL — Price Stable",
            "label": f"No big drop predicted immediately. Next possible sale around {sale_day_name}.",
            "color": "blue", "icon": "🔵",
            "confidence": random.randint(60, 75)
        }

    return {
        "platform_histories": all_platform_histories,
        "platform_colors": platform_colors,
        "best_platform_for_chart": best_pname,
        "forecast": forecast,
        "sale_date_annotations": sale_date_annotations,
        "upcoming_sale_day": sale_day_name,
        "min_forecast_price": min_forecast,
        "timing": timing,
        # legacy keys kept for compatibility
        "history": all_platform_histories[best_pname],
        "price_forecast": forecast,
    }

def compute_buy_score(price, min_price, max_price, rating, delivery_str, in_stock, delivery_fee_free):
    price_range = max_price - min_price or 1
    price_score = (1 - (price - min_price) / price_range) * 40
    rating_score = ((rating - 1) / 4) * 25
    dmap = {
        "10 Mins":10,"8-12 Mins":11,"10 Min":10,"15-20 Mins":17,"30-45 Mins":37,
        "2 Hours":120,"Same Day":480,"Next Day":1440,"2-3 Days":3000,"3-5 Days":5000,"4-7 Days":7000
    }
    mins = dmap.get(delivery_str, 480)
    delivery_score = max(0, (1 - mins / 2000)) * 20
    stock_score = 10 if in_stock else 0
    free_score = 5 if delivery_fee_free else 0
    return min(100, max(0, round(price_score + rating_score + delivery_score + stock_score + free_score)))

# ── In-memory alert store (replace with SQLite/DB for production) ─────────────
PRICE_ALERTS = []  # list of {email, product_name, target_price, current_best, set_at}

# ── Email helpers ──────────────────────────────────────────────────────────────

def _send_email(to_addr: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """Send an email. Returns True on success, False on failure."""
    if not EMAIL_ENABLED:
        print(f"[EMAIL DISABLED] Would send to {to_addr}: {subject}")
        return True
    if EMAIL_USER in ("your_email@gmail.com", "") or EMAIL_PASS in ("your_app_password_here", ""):
        print("[EMAIL ERROR] EMAIL_USER / EMAIL_PASS not configured in .env or app.py")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_FROM
        msg["To"]      = to_addr
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        print(f"[EMAIL] Connecting to {EMAIL_HOST}:{EMAIL_PORT} as {EMAIL_USER}...")
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=15) as srv:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            srv.login(EMAIL_USER, EMAIL_PASS)
            srv.sendmail(EMAIL_USER, to_addr, msg.as_string())
        print(f"[EMAIL] SUCCESS - Sent to {to_addr}: {subject}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"[EMAIL ERROR] Auth failed - wrong password or App Password not set. {e}")
        return False
    except smtplib.SMTPException as e:
        print(f"[EMAIL ERROR] SMTP error: {e}")
        return False
    except Exception as e:
        print(f"[EMAIL ERROR] Unexpected: {e}")
        return False


def send_alert_confirmation(to_addr: str, product_name: str, target_price: int, best_price: int, best_platform: str) -> bool:
    """Confirmation email sent immediately when user sets an alert."""
    formatted_target = f"₹{int(target_price):,}"
    formatted_best   = f"₹{int(best_price):,}"
    subject = f"✅ Price alert set — {product_name}"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0f1e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0f1e;padding:32px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#0d1526;border-radius:16px;overflow:hidden;border:1px solid rgba(99,102,241,.25);">
  <tr><td style="background:linear-gradient(135deg,#6366f1,#22d3ee);padding:28px 36px;">
    <p style="margin:0;font-size:22px;font-weight:800;color:#fff;letter-spacing:-.3px;">Smart<span style="color:#a5f3fc;">Price</span></p>
    <p style="margin:4px 0 0;font-size:13px;color:rgba(255,255,255,.75);">AI Price Intelligence</p>
  </td></tr>
  <tr><td style="padding:36px;">
    <p style="font-size:28px;margin:0 0 8px;">✅</p>
    <h1 style="margin:0 0 8px;font-size:22px;font-weight:800;color:#f1f5f9;">Price alert confirmed!</h1>
    <p style="margin:0 0 28px;font-size:14px;color:#64748b;line-height:1.7;">
      We'll notify you at <strong style="color:#a5b4fc;">{to_addr}</strong> the moment the price drops to your target.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.2);border-radius:12px;margin-bottom:28px;">
      <tr><td style="padding:24px;">
        <p style="margin:0 0 6px;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.08em;">Product</p>
        <p style="margin:0 0 20px;font-size:17px;font-weight:700;color:#f1f5f9;">{product_name}</p>
        <table width="100%"><tr>
          <td width="50%" style="padding-right:12px;">
            <p style="margin:0 0 4px;font-size:11px;color:#64748b;">Current best price</p>
            <p style="margin:0;font-size:24px;font-weight:800;color:#f1f5f9;">{formatted_best}</p>
            <p style="margin:2px 0 0;font-size:12px;color:#64748b;">on {best_platform}</p>
          </td>
          <td width="50%">
            <p style="margin:0 0 4px;font-size:11px;color:#64748b;">Your alert target</p>
            <p style="margin:0;font-size:24px;font-weight:800;color:#10b981;">{formatted_target}</p>
            <p style="margin:2px 0 0;font-size:12px;color:#10b981;">We alert you at or below this</p>
          </td>
        </tr></table>
      </td></tr>
    </table>
    <p style="font-size:13px;color:#475569;line-height:1.7;margin:0;">
      SmartPrice monitors prices across Blinkit, Zepto, BigBasket, Amazon, Flipkart and more. You will receive another email the moment the price hits your target.
    </p>
  </td></tr>
  <tr><td style="background:rgba(255,255,255,.02);border-top:1px solid rgba(255,255,255,.06);padding:18px 36px;">
    <p style="margin:0;font-size:12px;color:#334155;">This alert was set for <strong>{to_addr}</strong>. You can set a new alert anytime from the SmartPrice dashboard.</p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""
    text = f"Hi,\n\nPrice alert confirmed for: {product_name}\nCurrent best price: {formatted_best} (on {best_platform})\nYour target: {formatted_target}\n\nWe will email you as soon as the price drops to {formatted_target} or below.\n\n— SmartPrice Team"
    return _send_email(to_addr, subject, html, text)


def send_price_drop_notification(to_addr: str, product_name: str, target_price: int, new_price: int, platform: str) -> bool:
    """Email sent when a price drop actually triggers the alert."""
    formatted_target = f"₹{int(target_price):,}"
    formatted_new    = f"₹{int(new_price):,}"
    saving           = f"₹{int(target_price - new_price):,}" if target_price > new_price else ""
    subject = f"🔔 Price dropped! {product_name} is now {formatted_new}"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0f1e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0f1e;padding:32px 16px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#0d1526;border-radius:16px;overflow:hidden;border:1px solid rgba(16,185,129,.3);">
  <tr><td style="background:linear-gradient(135deg,#059669,#10b981);padding:28px 36px;">
    <p style="margin:0;font-size:22px;font-weight:800;color:#fff;letter-spacing:-.3px;">Smart<span style="color:#a7f3d0;">Price</span> 🔔</p>
    <p style="margin:4px 0 0;font-size:13px;color:rgba(255,255,255,.8);">Price drop alert triggered!</p>
  </td></tr>
  <tr><td style="padding:36px;">
    <h1 style="margin:0 0 8px;font-size:22px;font-weight:800;color:#f1f5f9;">The price dropped!</h1>
    <p style="margin:0 0 28px;font-size:14px;color:#64748b;line-height:1.7;">
      Great news — <strong style="color:#a5b4fc;">{product_name}</strong> has reached your target price on <strong style="color:#10b981;">{platform}</strong>.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);border-radius:12px;margin-bottom:28px;">
      <tr><td style="padding:24px;">
        <table width="100%"><tr>
          <td width="33%" style="text-align:center;padding:8px;">
            <p style="margin:0 0 4px;font-size:11px;color:#64748b;">Your target</p>
            <p style="margin:0;font-size:20px;font-weight:800;color:#94a3b8;">{formatted_target}</p>
          </td>
          <td width="33%" style="text-align:center;padding:8px;background:rgba(16,185,129,.12);border-radius:8px;">
            <p style="margin:0 0 4px;font-size:11px;color:#10b981;">Current price</p>
            <p style="margin:0;font-size:28px;font-weight:900;color:#10b981;">{formatted_new}</p>
          </td>
          <td width="33%" style="text-align:center;padding:8px;">
            <p style="margin:0 0 4px;font-size:11px;color:#64748b;">Below target by</p>
            <p style="margin:0;font-size:20px;font-weight:800;color:#f59e0b;">{saving}</p>
          </td>
        </tr></table>
      </td></tr>
    </table>
    <p style="font-size:12px;color:#475569;margin:0;line-height:1.6;">⚡ Prices can change quickly — visit SmartPrice now to compare and buy.</p>
  </td></tr>
  <tr><td style="background:rgba(255,255,255,.02);border-top:1px solid rgba(255,255,255,.06);padding:18px 36px;">
    <p style="margin:0;font-size:12px;color:#334155;">This alert was set for <strong>{to_addr}</strong>. This alert has been fulfilled.</p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""
    text = f"Great news!\n\n{product_name} has dropped to {formatted_new} on {platform} — below your target of {formatted_target}.\n\nVisit SmartPrice to compare and buy now.\n\n— SmartPrice Team"
    return _send_email(to_addr, subject, html, text)


PRODUCT_DB = {
    "amul taaza milk": {
        "name": "Amul Taaza Toned Fresh Milk 1L", "brand": "Amul", "category": "Dairy",
        "description": "Pasteurised toned milk, 3% fat, 8.5% SNF. India's most trusted dairy brand since 1946.",
        "platforms": {
            "Blinkit":   {"min":58,"max":67,"typical":62,"mrp":68,"delivery":"8-12 Mins","delivery_fee":"Free","offer":"Free delivery above Rs.199","in_stock":True,"rating":4.5,"reviews":14230,"direct_url":"https://blinkit.com/s/?q=amul+taaza+milk"},
            "Zepto":     {"min":57,"max":65,"typical":61,"mrp":68,"delivery":"10 Min",   "delivery_fee":"Free","offer":"10% Off first order",      "in_stock":True,"rating":4.4,"reviews":8920, "direct_url":"https://www.zeptonow.com/search?query=amul+taaza+milk"},
            "Instamart": {"min":61,"max":70,"typical":65,"mrp":68,"delivery":"15-20 Mins","delivery_fee":"Free","offer":"SAVE10 Coupon 10% Off",    "in_stock":True,"rating":4.3,"reviews":11234,"direct_url":"https://www.swiggy.com/instamart/search?query=amul+taaza+milk"},
            "BigBasket": {"min":56,"max":64,"typical":60,"mrp":68,"delivery":"30-45 Mins","delivery_fee":"Rs.20","offer":"Buy 2 Save Rs.15",        "in_stock":True,"rating":4.6,"reviews":32410,"direct_url":"https://www.bigbasket.com/ps/?q=amul+taaza+milk"},
            "JioMart":   {"min":60,"max":66,"typical":63,"mrp":68,"delivery":"2 Hours",  "delivery_fee":"Free","offer":"Flat Rs.20 Off on Rs.200+", "in_stock":True,"rating":4.0,"reviews":9870, "direct_url":"https://www.jiomart.com/search/amul+taaza+milk"},
            "Amazon":    {"min":62,"max":72,"typical":67,"mrp":70,"delivery":"Same Day", "delivery_fee":"Free","offer":"Subscribe & Save 5%",       "in_stock":True,"rating":4.2,"reviews":18920,"direct_url":"https://www.amazon.in/s?k=amul+taaza+milk"},
        }
    },
    "samsung galaxy s24": {
        "name": "Samsung Galaxy S24 (256GB, Cobalt Violet)", "brand": "Samsung", "category": "Smartphones",
        "description": "Snapdragon 8 Gen 3 | 6.2-inch FHD+ Dynamic AMOLED 2X 120Hz | 50MP triple camera | 4000mAh 25W | IP68 | Galaxy AI | Android 14",
        "platforms": {
            "Flipkart":  {"min":71499,"max":74999,"typical":72999,"mrp":79999,"delivery":"Next Day","delivery_fee":"Free","offer":"Exchange Rs.15000 Old Phone","in_stock":True,"rating":4.5,"reviews":52341,"direct_url":"https://www.flipkart.com/samsung-galaxy-s24-5g-cobalt-violet-256-gb/p/itm5e74a8c7a8f12"},
            "Reliance":  {"min":72499,"max":75499,"typical":73999,"mrp":79999,"delivery":"Same Day","delivery_fee":"Free","offer":"No Cost EMI 12 Months",    "in_stock":True,"rating":4.3,"reviews":18760,"direct_url":"https://www.reliancedigital.in/search?q=samsung+galaxy+s24"},
            "Amazon":    {"min":73499,"max":76999,"typical":74999,"mrp":79999,"delivery":"Same Day","delivery_fee":"Free","offer":"Rs.5000 Off with SBI Card", "in_stock":True,"rating":4.6,"reviews":41230,"direct_url":"https://www.amazon.in/s?k=samsung+galaxy+s24+256gb"},
            "Croma":     {"min":74999,"max":77999,"typical":75999,"mrp":79999,"delivery":"2-3 Days","delivery_fee":"Free","offer":"Free Galaxy Buds FE",       "in_stock":True,"rating":4.4,"reviews":12340,"direct_url":"https://www.croma.com/searchB?q=samsung+galaxy+s24"},
            "JioMart":   {"min":73999,"max":76499,"typical":75499,"mrp":79999,"delivery":"3-5 Days","delivery_fee":"Free","offer":"10% Cashback JioCoin",      "in_stock":False,"rating":4.2,"reviews":4321,"direct_url":"https://www.jiomart.com/search/samsung+galaxy+s24"},
        }
    },
    "iphone 15": {
        "name": "Apple iPhone 15 (128GB) - Midnight Black", "brand": "Apple", "category": "Smartphones",
        "description": "A16 Bionic chip | 6.1-inch Super Retina XDR OLED | 48MP main camera | USB-C | Dynamic Island | 5G | iOS 17",
        "platforms": {
            "Flipkart":    {"min":66999,"max":70499,"typical":68999,"mrp":79900,"delivery":"Next Day","delivery_fee":"Free","offer":"Exchange up to Rs.55000",       "in_stock":True,"rating":4.7,"reviews":89430,"direct_url":"https://www.flipkart.com/apple-iphone-15-black-128-gb/p/itm6ac6485515ae4"},
            "Amazon":      {"min":67999,"max":71999,"typical":69900,"mrp":79900,"delivery":"Same Day","delivery_fee":"Free","offer":"Rs.5000 HDFC Bank Discount",     "in_stock":True,"rating":4.8,"reviews":73210,"direct_url":"https://www.amazon.in/s?k=apple+iphone+15+128gb"},
            "Reliance":    {"min":68999,"max":72499,"typical":70999,"mrp":79900,"delivery":"Same Day","delivery_fee":"Free","offer":"No Cost EMI 24 Months",           "in_stock":True,"rating":4.5,"reviews":29870,"direct_url":"https://www.reliancedigital.in/search?q=iphone+15"},
            "Croma":       {"min":69999,"max":73499,"typical":71900,"mrp":79900,"delivery":"2-3 Days","delivery_fee":"Free","offer":"Free AirPods Case Rs.3500",       "in_stock":True,"rating":4.6,"reviews":18760,"direct_url":"https://www.croma.com/searchB?q=apple+iphone+15"},
            "Apple Store": {"min":79900,"max":79900,"typical":79900,"mrp":79900,"delivery":"3-5 Days","delivery_fee":"Free","offer":"Trade-In & 0% EMI available",     "in_stock":True,"rating":4.9,"reviews":112300,"direct_url":"https://www.apple.com/in/shop/buy-iphone/iphone-15"},
        }
    },
    "maggi noodles": {
        "name": "Maggi 2-Minute Noodles Masala 70g", "brand": "Nestle", "category": "Grocery",
        "description": "India's #1 instant noodles. Enriched wheat flour with signature tastemaker masala. Ready in 2 minutes. No added MSG.",
        "platforms": {
            "Zepto":     {"min":13,"max":15,"typical":14,"mrp":15,"delivery":"10 Min",   "delivery_fee":"Free","offer":"Free delivery on first order","in_stock":True,"rating":4.5,"reviews":42130,"direct_url":"https://www.zeptonow.com/search?query=maggi+noodles"},
            "BigBasket": {"min":13,"max":14,"typical":13,"mrp":15,"delivery":"30-45 Mins","delivery_fee":"Rs.20","offer":"Buy 5 Save Rs.10",          "in_stock":True,"rating":4.7,"reviews":89320,"direct_url":"https://www.bigbasket.com/ps/?q=maggi+noodles"},
            "Blinkit":   {"min":14,"max":16,"typical":15,"mrp":15,"delivery":"8-12 Mins","delivery_fee":"Free","offer":"Free delivery above Rs.199",  "in_stock":True,"rating":4.6,"reviews":67840,"direct_url":"https://blinkit.com/s/?q=maggi+noodles"},
            "Instamart": {"min":14,"max":16,"typical":15,"mrp":15,"delivery":"15-20 Mins","delivery_fee":"Free","offer":"SAVE10 Coupon",              "in_stock":True,"rating":4.5,"reviews":38920,"direct_url":"https://www.swiggy.com/instamart/search?query=maggi+noodles"},
            "JioMart":   {"min":14,"max":15,"typical":14,"mrp":15,"delivery":"2 Hours",  "delivery_fee":"Free","offer":"Flat Rs.20 Off on Rs.200+",   "in_stock":True,"rating":4.3,"reviews":52340,"direct_url":"https://www.jiomart.com/search/maggi+noodles"},
            "Amazon":    {"min":15,"max":18,"typical":16,"mrp":15,"delivery":"Same Day", "delivery_fee":"Free","offer":"Pack of 12 deal",             "in_stock":True,"rating":4.4,"reviews":29870,"direct_url":"https://www.amazon.in/s?k=maggi+noodles+masala"},
        }
    },
    "boat rockerz 450": {
        "name": "boAt Rockerz 450 Pro Bluetooth Headphone", "brand": "boAt", "category": "Electronics",
        "description": "70 hours playback | 40mm HD drivers | ASAP Charge | ENx mic | Foldable | Bluetooth 5.0 | IPX5",
        "platforms": {
            "Meesho":   {"min":899, "max":1199,"typical":999, "mrp":2990,"delivery":"3-5 Days","delivery_fee":"Free","offer":"Buy 2 Save Rs.200",      "in_stock":True,"rating":3.9,"reviews":32410,"direct_url":"https://www.meesho.com/search?q=boat+rockerz+450"},
            "Flipkart": {"min":1099,"max":1399,"typical":1199,"mrp":2990,"delivery":"Next Day","delivery_fee":"Free","offer":"Extra 5% Off Coupon",    "in_stock":True,"rating":4.2,"reviews":128430,"direct_url":"https://www.flipkart.com/search?q=boat+rockerz+450+pro"},
            "Amazon":   {"min":1199,"max":1499,"typical":1299,"mrp":2990,"delivery":"Same Day","delivery_fee":"Free","offer":"10% Cashback HDFC Card", "in_stock":True,"rating":4.3,"reviews":98320,"direct_url":"https://www.amazon.in/s?k=boat+rockerz+450+pro"},
            "Croma":    {"min":1299,"max":1599,"typical":1499,"mrp":2990,"delivery":"Same Day","delivery_fee":"Free","offer":"No Cost EMI 3 Months",   "in_stock":True,"rating":4.0,"reviews":18760,"direct_url":"https://www.croma.com/searchB?q=boat+rockerz+450"},
            "Myntra":   {"min":1349,"max":1649,"typical":1449,"mrp":2990,"delivery":"2-3 Days","delivery_fee":"Rs.49","offer":"Free Delivery on Rs.999","in_stock":True,"rating":4.1,"reviews":23890,"direct_url":"https://www.myntra.com/boat-rockerz-450"},
        }
    },
    "surf excel": {
        "name": "Surf Excel Easy Wash Detergent Powder 1kg", "brand": "HUL", "category": "Grocery",
        "description": "Dirt lock technology removes 100 tough stains in 1 wash. Machine and hand wash. Fresh floral fragrance.",
        "platforms": {
            "BigBasket": {"min":120,"max":135,"typical":127,"mrp":145,"delivery":"30-45 Mins","delivery_fee":"Rs.20","offer":"Buy 2 Save Rs.25",          "in_stock":True,"rating":4.6,"reviews":43210,"direct_url":"https://www.bigbasket.com/ps/?q=surf+excel+easy+wash"},
            "Blinkit":   {"min":125,"max":138,"typical":129,"mrp":145,"delivery":"8-12 Mins","delivery_fee":"Free","offer":"Free delivery above Rs.199",  "in_stock":True,"rating":4.5,"reviews":28930,"direct_url":"https://blinkit.com/s/?q=surf+excel"},
            "Zepto":     {"min":122,"max":136,"typical":127,"mrp":145,"delivery":"10 Min",  "delivery_fee":"Free","offer":"10% Off first order",          "in_stock":True,"rating":4.4,"reviews":18760,"direct_url":"https://www.zeptonow.com/search?query=surf+excel"},
            "Instamart": {"min":128,"max":140,"typical":131,"mrp":145,"delivery":"15-20 Mins","delivery_fee":"Free","offer":"SAVE10 Coupon",              "in_stock":True,"rating":4.3,"reviews":12340,"direct_url":"https://www.swiggy.com/instamart/search?query=surf+excel"},
            "JioMart":   {"min":124,"max":137,"typical":128,"mrp":145,"delivery":"2 Hours", "delivery_fee":"Free","offer":"Flat Rs.30 Off Rs.299+",       "in_stock":True,"rating":4.2,"reviews":23870,"direct_url":"https://www.jiomart.com/search/surf+excel"},
            "Amazon":    {"min":130,"max":142,"typical":133,"mrp":145,"delivery":"Same Day","delivery_fee":"Free","offer":"Subscribe & Save 10%",         "in_stock":True,"rating":4.4,"reviews":67890,"direct_url":"https://www.amazon.in/s?k=surf+excel+easy+wash+1kg"},
            "Flipkart":  {"min":132,"max":145,"typical":135,"mrp":145,"delivery":"Next Day","delivery_fee":"Rs.40","offer":"10% Cashback Axis Card",      "in_stock":True,"rating":4.3,"reviews":38920,"direct_url":"https://www.flipkart.com/search?q=surf+excel+easy+wash+1kg"},
        }
    },
    "oneplus 12": {
        "name": "OnePlus 12 (256GB, Flowy Emerald)", "brand": "OnePlus", "category": "Smartphones",
        "description": "Snapdragon 8 Gen 3 | 6.82-inch LTPO AMOLED 120Hz | Hasselblad 50MP triple camera | 5400mAh | 100W SUPERVOOC | Android 14",
        "platforms": {
            "Flipkart":  {"min":63999,"max":67499,"typical":65999,"mrp":74999,"delivery":"Next Day","delivery_fee":"Free","offer":"Exchange up to Rs.40000",    "in_stock":True,"rating":4.6,"reviews":34210,"direct_url":"https://www.flipkart.com/search?q=oneplus+12+256gb"},
            "Amazon":    {"min":64999,"max":68499,"typical":64999,"mrp":74999,"delivery":"Same Day","delivery_fee":"Free","offer":"Rs.4000 ICICI Bank Discount", "in_stock":True,"rating":4.7,"reviews":28760,"direct_url":"https://www.amazon.in/s?k=oneplus+12+256gb"},
            "Croma":     {"min":66999,"max":70499,"typical":67999,"mrp":74999,"delivery":"2-3 Days","delivery_fee":"Free","offer":"Free OnePlus Buds",           "in_stock":True,"rating":4.5,"reviews":12340,"direct_url":"https://www.croma.com/searchB?q=oneplus+12"},
            "Reliance":  {"min":65499,"max":68999,"typical":66499,"mrp":74999,"delivery":"Same Day","delivery_fee":"Free","offer":"No Cost EMI 12 Months",       "in_stock":True,"rating":4.4,"reviews":9870,"direct_url":"https://www.reliancedigital.in/search?q=oneplus+12"},
        }
    },
    "dettol soap": {
        "name": "Dettol Original Germ Protection Soap 75g", "brand": "Reckitt", "category": "Grocery",
        "description": "10x better germ protection with PCMX antibacterial ingredient. Clinically tested. Fresh pine fragrance.",
        "platforms": {
            "BigBasket": {"min":35,"max":42,"typical":38,"mrp":47,"delivery":"30-45 Mins","delivery_fee":"Rs.20","offer":"Buy 4 Save Rs.20",          "in_stock":True,"rating":4.7,"reviews":78430,"direct_url":"https://www.bigbasket.com/ps/?q=dettol+soap"},
            "Blinkit":   {"min":38,"max":44,"typical":40,"mrp":47,"delivery":"8-12 Mins","delivery_fee":"Free","offer":"Free delivery above Rs.199",  "in_stock":True,"rating":4.6,"reviews":52130,"direct_url":"https://blinkit.com/s/?q=dettol+soap"},
            "Zepto":     {"min":36,"max":43,"typical":39,"mrp":47,"delivery":"10 Min",  "delivery_fee":"Free","offer":"10% Off combo packs",          "in_stock":True,"rating":4.5,"reviews":34870,"direct_url":"https://www.zeptonow.com/search?query=dettol+soap"},
            "Instamart": {"min":39,"max":45,"typical":41,"mrp":47,"delivery":"15-20 Mins","delivery_fee":"Free","offer":"SAVE10 Coupon",              "in_stock":True,"rating":4.4,"reviews":28930,"direct_url":"https://www.swiggy.com/instamart/search?query=dettol+soap"},
            "JioMart":   {"min":37,"max":43,"typical":39,"mrp":47,"delivery":"2 Hours", "delivery_fee":"Free","offer":"Flat Rs.15 Off Rs.150+",       "in_stock":True,"rating":4.3,"reviews":41230,"direct_url":"https://www.jiomart.com/search/dettol+soap"},
            "Amazon":    {"min":40,"max":46,"typical":42,"mrp":47,"delivery":"Same Day","delivery_fee":"Free","offer":"Subscribe & Save 5%",          "in_stock":True,"rating":4.5,"reviews":98430,"direct_url":"https://www.amazon.in/s?k=dettol+original+soap+75g"},
        }
    },
    "dell i7 laptop": {
        "name": "Dell Inspiron 15 3520 (Core i7-1255U, 16GB, 512GB SSD)", "brand": "Dell", "category": "Electronics",
        "description": "12th Gen Intel Core i7-1255U | 15.6-inch FHD | 16GB DDR4 | 512GB SSD | Windows 11 | 1 Year Warranty",
        "platforms": {
            "Amazon":   {"min":72990,"max":79990,"typical":74990,"mrp":89990,"delivery":"Same Day","delivery_fee":"Free","offer":"Rs.3000 Off with HDFC Card",    "in_stock":True,"rating":4.3,"reviews":8430, "direct_url":"https://www.amazon.in/s?k=dell+inspiron+i7+laptop"},
            "Flipkart": {"min":71990,"max":78990,"typical":73990,"mrp":89990,"delivery":"Next Day","delivery_fee":"Free","offer":"Exchange up to Rs.20000",        "in_stock":True,"rating":4.2,"reviews":12340,"direct_url":"https://www.flipkart.com/search?q=dell+inspiron+i7+laptop"},
            "Croma":    {"min":74990,"max":81990,"typical":76990,"mrp":89990,"delivery":"Same Day","delivery_fee":"Free","offer":"No Cost EMI 12 Months",           "in_stock":True,"rating":4.1,"reviews":3210, "direct_url":"https://www.croma.com/searchB?q=dell+i7+laptop"},
            "Reliance": {"min":73990,"max":80990,"typical":75990,"mrp":89990,"delivery":"2-3 Days","delivery_fee":"Free","offer":"Free Dell Bag worth Rs.1999",     "in_stock":True,"rating":4.0,"reviews":2870, "direct_url":"https://www.reliancedigital.in/search?q=dell+i7+laptop"},
        }
    },
    "dell laptop": {
        "name": "Dell Inspiron 15 3520 (Core i7-1255U, 16GB, 512GB SSD)", "brand": "Dell", "category": "Electronics",
        "description": "12th Gen Intel Core i7-1255U | 15.6-inch FHD | 16GB DDR4 | 512GB SSD | Windows 11 | 1 Year Warranty",
        "platforms": {
            "Amazon":   {"min":72990,"max":79990,"typical":74990,"mrp":89990,"delivery":"Same Day","delivery_fee":"Free","offer":"Rs.3000 Off with HDFC Card",    "in_stock":True,"rating":4.3,"reviews":8430, "direct_url":"https://www.amazon.in/s?k=dell+inspiron+i7+laptop"},
            "Flipkart": {"min":71990,"max":78990,"typical":73990,"mrp":89990,"delivery":"Next Day","delivery_fee":"Free","offer":"Exchange up to Rs.20000",        "in_stock":True,"rating":4.2,"reviews":12340,"direct_url":"https://www.flipkart.com/search?q=dell+inspiron+i7+laptop"},
            "Croma":    {"min":74990,"max":81990,"typical":76990,"mrp":89990,"delivery":"Same Day","delivery_fee":"Free","offer":"No Cost EMI 12 Months",           "in_stock":True,"rating":4.1,"reviews":3210, "direct_url":"https://www.croma.com/searchB?q=dell+i7+laptop"},
            "Reliance": {"min":73990,"max":80990,"typical":75990,"mrp":89990,"delivery":"2-3 Days","delivery_fee":"Free","offer":"Free Dell Bag worth Rs.1999",     "in_stock":True,"rating":4.0,"reviews":2870, "direct_url":"https://www.reliancedigital.in/search?q=dell+i7+laptop"},
        }
    },
}

def match_product(query):
    q = query.lower().strip()
    q_words = [w for w in q.split() if len(w) > 1]
    best_key, best_score = None, 0

    for key in PRODUCT_DB:
        key_words = key.split()
        # Count how many query words appear in the key AND how many key words appear in query
        forward  = sum(1 for w in key_words if w in q_words)
        backward = sum(1 for w in q_words  if w in key_words)
        # Weighted: both directions matter; bonus if key is substring of query
        score = forward * 2 + backward + (1 if key in q else 0)
        if score > best_score:
            best_score, best_key = score, key

    if best_score > 0:
        return PRODUCT_DB[best_key]

    # ── Fallback: unknown product — use realistic placeholder prices ──
    # (prices are fixed, not random, so they stay consistent)
    base = 1999
    return {
        "name": query.title(), "brand": "Various", "category": "General",
        "description": f"Price comparison for '{query.title()}' across major Indian platforms. Add this product to the database for exact prices.",
        "platforms": {
            "Amazon":   {"min":int(base*.92),"max":int(base*1.08),"typical":base,           "mrp":int(base*1.18),"delivery":"Same Day","delivery_fee":"Free","offer":"10% Cashback","in_stock":True,"rating":4.2,"reviews":1200,"direct_url":f"https://www.amazon.in/s?k={urllib.parse.quote_plus(query)}"},
            "Flipkart": {"min":int(base*.88),"max":int(base*1.04),"typical":int(base*.96),  "mrp":int(base*1.18),"delivery":"Next Day","delivery_fee":"Free","offer":"5% Extra Off","in_stock":True,"rating":4.1,"reviews":980,"direct_url":f"https://www.flipkart.com/search?q={urllib.parse.quote_plus(query)}"},
            "Meesho":   {"min":int(base*.82),"max":int(base*.98), "typical":int(base*.88),  "mrp":int(base*1.18),"delivery":"3-5 Days","delivery_fee":"Free","offer":"Free Delivery","in_stock":True,"rating":3.9,"reviews":750,"direct_url":f"https://www.meesho.com/search?q={urllib.parse.quote_plus(query)}"},
            "JioMart":  {"min":int(base*.90),"max":int(base*1.05),"typical":int(base*.93),  "mrp":int(base*1.18),"delivery":"2 Hours","delivery_fee":"Free","offer":"Rs.50 Off Rs.499","in_stock":True,"rating":4.0,"reviews":640,"direct_url":f"https://www.jiomart.com/search/{urllib.parse.quote_plus(query)}"},
        }
    }

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# =============================================================================
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>SmartPrice - Login</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Cabinet+Grotesk:wght@400;700;800;900&display=swap" rel="stylesheet"/>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root{--bg:#06080f;--card:rgba(12,16,28,.92);--b:rgba(255,255,255,.08);--ac:#6366f1;--ac2:#22d3ee;--gr:#10b981;--re:#f43f5e;--tx:#f1f5f9;--mu:#64748b;--go:#f59e0b;}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);min-height:100vh;display:flex;align-items:center;justify-content:center;overflow:hidden;}
.bg{position:fixed;inset:0;}
.mesh{position:absolute;inset:0;background:radial-gradient(ellipse 80% 60% at 20% 20%,rgba(99,102,241,.18),transparent),radial-gradient(ellipse 60% 80% at 80% 80%,rgba(34,211,238,.12),transparent);}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgba(99,102,241,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,.06) 1px,transparent 1px);background-size:40px 40px;}
.wrap{position:relative;z-index:10;width:100%;max-width:440px;padding:16px;}
.card{background:var(--card);border:1px solid var(--b);border-radius:20px;padding:44px 40px;backdrop-filter:blur(32px);box-shadow:0 32px 64px rgba(0,0,0,.7);animation:up .5s ease both;}
@keyframes up{from{opacity:0;transform:translateY(28px);}to{opacity:1;transform:none;}}
.logo{display:flex;align-items:center;gap:10px;margin-bottom:28px;}
.li{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,var(--ac),var(--ac2));display:flex;align-items:center;justify-content:center;font-size:19px;}
.lt{font-family:'Cabinet Grotesk',sans-serif;font-size:19px;font-weight:800;color:var(--tx);}
.lt span{color:var(--ac2);}
h1{font-family:'Cabinet Grotesk',sans-serif;font-size:24px;font-weight:800;color:var(--tx);margin-bottom:4px;}
.sub{color:var(--mu);font-size:13px;margin-bottom:28px;}
.tabs{display:flex;background:rgba(255,255,255,.04);border-radius:10px;padding:3px;margin-bottom:24px;border:1px solid var(--b);}
.tab{flex:1;padding:9px;border:none;border-radius:8px;background:transparent;color:var(--mu);font-family:'Space Grotesk',sans-serif;font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;}
.tab.active{background:linear-gradient(135deg,var(--ac),var(--ac2));color:#fff;}
.fg{margin-bottom:14px;}
label{display:block;font-size:11px;font-weight:600;color:var(--mu);text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px;}
input[type=text],input[type=email],input[type=password]{width:100%;padding:12px 14px;background:rgba(255,255,255,.05);border:1px solid var(--b);border-radius:10px;color:var(--tx);font-family:'Space Grotesk',sans-serif;font-size:14px;outline:none;transition:all .2s;}
input:focus{border-color:var(--ac);box-shadow:0 0 0 3px rgba(99,102,241,.15);}
.iw{position:relative;}
.eb{position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;color:var(--mu);cursor:pointer;font-size:14px;}
.btn{width:100%;padding:13px;margin-top:6px;background:linear-gradient(135deg,var(--ac),var(--ac2));border:none;border-radius:10px;color:#fff;font-family:'Cabinet Grotesk',sans-serif;font-size:15px;font-weight:700;cursor:pointer;transition:all .2s;}
.btn:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(99,102,241,.4);}
.btn:disabled{opacity:.6;cursor:not-allowed;transform:none;}
.sp{width:18px;height:18px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:none;margin:0 auto;}
@keyframes spin{to{transform:rotate(360deg);}}
.or{display:flex;align-items:center;gap:10px;margin:16px 0;color:var(--mu);font-size:12px;}
.or::before,.or::after{content:'';flex:1;height:1px;background:var(--b);}
.toast{position:fixed;top:20px;right:20px;z-index:9999;padding:12px 18px;border-radius:10px;font-size:13px;font-weight:600;transform:translateX(110%);transition:transform .3s ease;min-width:200px;}
.toast.show{transform:translateX(0);}
.toast-s{background:#064e3b;border:1px solid #10b981;color:#6ee7b7;}
.toast-e{background:#4c0519;border:1px solid #f43f5e;color:#fda4af;}
</style></head>
<body>
<div class="bg"><div class="mesh"></div><div class="grid"></div></div>
<div class="wrap"><div class="card">
  <div class="logo"><div class="li">&#128722;</div><div class="lt">Smart<span>Price</span></div></div>
  <h1 id="fT">Welcome back</h1>
  <p class="sub" id="fS">Sign in to compare prices and predict future deals</p>
  <div class="tabs">
    <button class="tab active" onclick="sw('l')">Login</button>
    <button class="tab" onclick="sw('r')">Register</button>
  </div>
  <div id="lF">
    <div class="fg"><label>Email</label><div class="iw"><input type="email" id="lE" placeholder="you@example.com"/></div></div>
    <div class="fg"><label>Password</label><div class="iw"><input type="password" id="lP" placeholder="Your password"/><button class="eb" onclick="tp('lP',this)" type="button">&#128065;</button></div></div>
    <button class="btn" id="lB" onclick="doL()"><span id="lBT">Sign In &rarr;</span><div class="sp" id="lS"></div></button>
  </div>
  <div id="rF" style="display:none;">
    <div class="fg"><label>Full Name</label><div class="iw"><input type="text" id="rN" placeholder="Rahul Sharma"/></div></div>
    <div class="fg"><label>Email</label><div class="iw"><input type="email" id="rE" placeholder="you@example.com"/></div></div>
    <div class="fg"><label>Password</label><div class="iw"><input type="password" id="rP" placeholder="Min 8 characters"/><button class="eb" onclick="tp('rP',this)" type="button">&#128065;</button></div></div>
    <button class="btn" id="rB" onclick="doR()"><span id="rBT">Create Account &rarr;</span><div class="sp" id="rS"></div></button>
  </div>
</div></div>
<div class="toast" id="toast"></div>
<script>
var at = 'l';
function sw(t) {
  at = t;
  var tabs = document.querySelectorAll('.tab');
  tabs[0].classList.toggle('active', t === 'l');
  tabs[1].classList.toggle('active', t === 'r');
  document.getElementById('lF').style.display = t === 'l' ? 'block' : 'none';
  document.getElementById('rF').style.display = t === 'r' ? 'block' : 'none';
  document.getElementById('fT').textContent = t === 'l' ? 'Welcome back' : 'Create account';
  document.getElementById('fS').textContent = t === 'l' ? 'Sign in to compare prices and predict deals' : 'Join SmartPrice and start saving today';
}
function tp(id, b) {
  var el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
  b.textContent = el.type === 'password' ? String.fromCodePoint(128065) : String.fromCodePoint(128584);
}
function sl(btnId, spId, loading) {
  var btn = document.getElementById(btnId);
  var sp = document.getElementById(spId);
  var txt = document.getElementById(btnId === 'lB' ? 'lBT' : 'rBT');
  btn.disabled = loading;
  txt.style.display = loading ? 'none' : 'inline';
  sp.style.display = loading ? 'block' : 'none';
}
function showToast(msg, type) {
  var t = document.getElementById('toast');
  t.textContent = (type === 's' ? 'OK ' : 'Error ') + msg;
  t.className = 'toast show toast-' + type;
  setTimeout(function() { t.classList.remove('show'); }, 4000);
}
async function doL() {
  var e = document.getElementById('lE').value.trim();
  var p = document.getElementById('lP').value;
  if (!e || !p) { showToast('Enter email and password', 'e'); return; }
  sl('lB', 'lS', true);
  try {
    var r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, password: p }) });
    var d = await r.json();
    if (d.success) { showToast('Welcome ' + d.name, 's'); setTimeout(function() { location.href = d.redirect; }, 700); }
    else { showToast(d.message, 'e'); sl('lB', 'lS', false); }
  } catch(err) { showToast('Connection error', 'e'); sl('lB', 'lS', false); }
}
async function doR() {
  var n = document.getElementById('rN').value.trim();
  var e = document.getElementById('rE').value.trim();
  var p = document.getElementById('rP').value;
  if (!n || !e || !p) { showToast('All fields required', 'e'); return; }
  if (p.length < 8) { showToast('Password must be 8+ chars', 'e'); return; }
  sl('rB', 'rS', true);
  try {
    var r = await fetch('/api/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: n, email: e, password: p }) });
    var d = await r.json();
    if (d.success) { showToast('Welcome ' + d.name, 's'); setTimeout(function() { location.href = d.redirect; }, 700); }
    else { showToast(d.message, 'e'); sl('rB', 'rS', false); }
  } catch(err) { showToast('Connection error', 'e'); sl('rB', 'rS', false); }
}
document.addEventListener('keydown', function(e) { if (e.key === 'Enter') { at === 'l' ? doL() : doR(); } });
</script></body></html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>SmartPrice - AI Price Intelligence</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Cabinet+Grotesk:wght@400;700;800;900&display=swap" rel="stylesheet"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root{--bg:#06080f;--card:rgba(12,16,28,.85);--b:rgba(255,255,255,.07);--ac:#6366f1;--ac2:#22d3ee;--gr:#10b981;--re:#f43f5e;--go:#f59e0b;--or:#f97316;--tx:#f1f5f9;--mu:#64748b;--mu2:#94a3b8;}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh;overflow-x:hidden;}
.bgw{position:fixed;inset:0;z-index:0;pointer-events:none;}
.mesh{position:absolute;inset:0;background:radial-gradient(ellipse 60% 50% at 10% 10%,rgba(99,102,241,.12),transparent),radial-gradient(ellipse 50% 60% at 90% 90%,rgba(34,211,238,.08),transparent);}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgba(99,102,241,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,.04) 1px,transparent 1px);background-size:40px 40px;}
.pg{position:relative;z-index:10;}
nav{display:flex;align-items:center;justify-content:space-between;padding:14px 36px;background:rgba(6,8,15,.85);border-bottom:1px solid var(--b);backdrop-filter:blur(24px);position:sticky;top:0;z-index:100;}
.nl{display:flex;align-items:center;gap:10px;}
.li{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,var(--ac),var(--ac2));display:flex;align-items:center;justify-content:center;font-size:16px;}
.ln{font-family:'Cabinet Grotesk',sans-serif;font-size:17px;font-weight:800;}
.ln span{color:var(--ac2);}
.nr{display:flex;align-items:center;gap:12px;}
.up{display:flex;align-items:center;gap:8px;padding:7px 14px;background:rgba(255,255,255,.04);border:1px solid var(--b);border-radius:100px;}
.ua{width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,var(--ac),var(--ac2));display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;}
.lb{padding:7px 14px;background:rgba(244,63,94,.1);border:1px solid rgba(244,63,94,.2);border-radius:100px;color:#fda4af;font-size:12px;font-weight:600;cursor:pointer;}
.hero{padding:52px 36px 36px;text-align:center;}
.badge{display:inline-flex;align-items:center;gap:7px;padding:5px 14px;background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.2);border-radius:100px;font-size:11px;font-weight:600;color:var(--ac);margin-bottom:18px;text-transform:uppercase;letter-spacing:.1em;}
.dot{width:5px;height:5px;background:var(--ac);border-radius:50%;animation:pu 2s infinite;}
@keyframes pu{0%,100%{opacity:1;}50%{opacity:.3;}}
h1{font-family:'Cabinet Grotesk',sans-serif;font-size:clamp(26px,4.5vw,48px);font-weight:900;line-height:1.1;margin-bottom:10px;}
.grad{background:linear-gradient(135deg,var(--ac2),var(--ac),var(--go));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.hs{font-size:15px;color:var(--mu2);max-width:500px;margin:0 auto 32px;}
.sw{max-width:680px;margin:0 auto;}
.sb{display:flex;align-items:center;background:rgba(12,16,28,.95);border:1px solid rgba(99,102,241,.3);border-radius:14px;padding:5px 5px 5px 18px;gap:10px;}
.sb input{flex:1;background:transparent;border:none;color:var(--tx);font-family:'Space Grotesk',sans-serif;font-size:14px;outline:none;padding:8px 0;}
.sb input::placeholder{color:var(--mu);}
.sbtn{padding:11px 24px;background:linear-gradient(135deg,var(--ac),var(--ac2));border:none;border-radius:10px;color:#fff;font-family:'Cabinet Grotesk',sans-serif;font-size:14px;font-weight:700;cursor:pointer;transition:all .2s;white-space:nowrap;}
.sbtn:hover{box-shadow:0 6px 20px rgba(99,102,241,.4);transform:translateY(-1px);}
.sbtn:disabled{opacity:.6;cursor:not-allowed;transform:none;}
.qs{display:flex;flex-wrap:wrap;justify-content:center;gap:7px;margin-top:14px;}
.chip{padding:5px 13px;background:rgba(255,255,255,.04);border:1px solid var(--b);border-radius:100px;font-size:12px;color:var(--mu2);cursor:pointer;transition:all .18s;}
.chip:hover{border-color:var(--ac);color:var(--ac);}
.stats{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;padding:28px 36px 0;}
.sc{padding:16px 24px;background:var(--card);border:1px solid var(--b);border-radius:12px;text-align:center;min-width:130px;}
.sn{font-family:'Cabinet Grotesk',sans-serif;font-size:22px;font-weight:800;color:var(--ac2);}
.sl2{font-size:11px;color:var(--mu);margin-top:1px;}
#ld{display:none;padding:52px 36px;text-align:center;}
.lds{display:flex;justify-content:center;gap:7px;margin-bottom:16px;}
.lds span{width:10px;height:10px;border-radius:50%;animation:bn 1.2s ease-in-out infinite;}
.lds span:nth-child(1){background:var(--ac);}
.lds span:nth-child(2){background:var(--ac2);animation-delay:.2s;}
.lds span:nth-child(3){background:var(--go);animation-delay:.4s;}
@keyframes bn{0%,80%,100%{transform:scale(0);}40%{transform:scale(1);}}
.lst{font-size:12px;color:var(--mu);opacity:0;animation:fi .5s forwards;margin-top:5px;}
@keyframes fi{to{opacity:1;}}
#res{padding:32px 36px;display:none;}
.ri{max-width:1080px;margin:0 auto;}
.ph{display:flex;align-items:flex-start;gap:20px;background:var(--card);border:1px solid var(--b);border-radius:16px;padding:24px;margin-bottom:20px;}
.pif h2{font-family:'Cabinet Grotesk',sans-serif;font-size:19px;font-weight:800;margin-bottom:6px;}
.pm{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:6px;}
.badge2{padding:3px 10px;border-radius:100px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;}
.bb{background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.3);color:#a5b4fc;}
.bc{background:rgba(34,211,238,.08);border:1px solid rgba(34,211,238,.2);color:var(--ac2);}
.pd{font-size:12px;color:var(--mu2);line-height:1.6;max-width:540px;}
.timing-banner{display:flex;align-items:center;gap:16px;border-radius:14px;padding:18px 22px;margin-bottom:20px;flex-wrap:wrap;}
.tb-green{background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);}
.tb-orange{background:rgba(249,115,22,.08);border:1px solid rgba(249,115,22,.25);}
.tb-blue{background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.25);}
.tb-info h3{font-family:'Cabinet Grotesk',sans-serif;font-size:17px;font-weight:800;}
.tb-info p{font-size:12px;color:var(--mu2);margin-top:2px;}
.confidence{margin-left:auto;text-align:right;}
.conf-num{font-family:'Cabinet Grotesk',sans-serif;font-size:22px;font-weight:800;color:var(--ac2);}
.conf-lbl{font-size:11px;color:var(--mu);}
.bd{background:linear-gradient(135deg,rgba(16,185,129,.1),rgba(34,211,238,.06));border:1px solid rgba(16,185,129,.25);border-radius:14px;padding:18px 22px;display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:14px;}
.bdl{display:flex;align-items:center;gap:14px;}
.bdih h3{font-family:'Cabinet Grotesk',sans-serif;font-size:17px;font-weight:800;color:var(--gr);}
.bdih p{font-size:12px;color:var(--mu2);}
.bdp .pr{font-family:'Cabinet Grotesk',sans-serif;font-size:28px;font-weight:900;color:var(--gr);}
.bdp .sv{font-size:12px;color:var(--mu2);}
.bdp .sv span{color:var(--go);font-weight:700;}
.vb{padding:11px 22px;background:linear-gradient(135deg,var(--gr),#059669);border:none;border-radius:10px;color:#fff;font-family:'Cabinet Grotesk',sans-serif;font-size:13px;font-weight:700;cursor:pointer;transition:all .2s;}
.vb:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(16,185,129,.3);}
.ai-tip{background:rgba(245,158,11,.06);border:1px solid rgba(245,158,11,.18);border-radius:12px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:flex-start;gap:10px;font-size:13px;color:#fcd34d;}
.sec{font-family:'Cabinet Grotesk',sans-serif;font-size:15px;font-weight:800;margin-bottom:14px;display:flex;align-items:center;gap:8px;}
.sec::after{content:'';flex:1;height:1px;background:var(--b);}
.pg2{display:grid;gap:10px;margin-bottom:28px;}
.pr-row{background:var(--card);border:1px solid var(--b);border-radius:14px;padding:0;display:block;text-decoration:none;color:inherit;transition:all .22s;cursor:pointer;overflow:hidden;}
.pr-row:hover{border-color:rgba(99,102,241,.3);transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.4);}
.pr-row.best{border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.04);}
.pr-inner{display:grid;grid-template-columns:50px 1fr auto auto;align-items:center;gap:14px;padding:18px 20px;position:relative;}
.pl{width:44px;height:44px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;}
.pn{font-weight:700;font-size:13px;}
.pde{font-size:11px;color:var(--mu);margin-top:1px;}
.score-bar{height:3px;background:rgba(255,255,255,.06);border-radius:2px;margin-top:5px;width:70px;}
.score-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--ac),var(--gr));}
.score-val{font-size:10px;font-weight:700;color:var(--ac2);}
.pr-mid{display:flex;flex-direction:column;gap:4px;align-items:flex-end;}
.po{font-size:11px;font-weight:600;padding:3px 10px;background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.18);border-radius:100px;color:var(--go);}
.pra{font-size:11px;color:var(--mu);}
.pr-right{text-align:right;min-width:100px;}
.pp{font-family:'Cabinet Grotesk',sans-serif;font-size:19px;font-weight:800;}
.pp.lo{color:var(--gr);}
.pp.hi{color:var(--re);}
.disc{font-size:10px;color:var(--go);margin-top:1px;}
.stk{font-size:10px;font-weight:700;padding:2px 8px;border-radius:100px;margin-top:3px;display:inline-block;}
.is{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.2);color:var(--gr);}
.os{background:rgba(244,63,94,.08);border:1px solid rgba(244,63,94,.2);color:var(--re);}
.arrow{font-size:11px;color:var(--ac);opacity:0;transition:opacity .18s;position:absolute;right:14px;top:12px;}
.pr-row:hover .arrow{opacity:1;}
.charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px;}
.chart-card{background:var(--card);border:1px solid var(--b);border-radius:14px;padding:20px;}
.chart-card.full{grid-column:1/-1;}
.chart-title{font-family:'Cabinet Grotesk',sans-serif;font-size:14px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px;flex-wrap:wrap;}
.chart-note{font-size:11px;color:var(--mu);margin-bottom:12px;padding:6px 10px;background:rgba(255,255,255,.03);border-radius:6px;border-left:2px solid var(--ac);}
.leg-row{display:flex;gap:12px;font-size:10px;color:var(--mu);margin-bottom:10px;flex-wrap:wrap;}
.leg-item{display:flex;align-items:center;gap:4px;}
.leg-dot{width:8px;height:8px;border-radius:50%;}
.als{background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.18);border-radius:14px;padding:20px 22px;margin-bottom:28px;}
.alr{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.ali{flex:1;padding:11px 14px;min-width:140px;background:rgba(255,255,255,.04);border:1px solid var(--b);border-radius:10px;color:var(--tx);font-family:'Space Grotesk',sans-serif;font-size:14px;outline:none;}
.ali:focus{border-color:var(--ac);}
.alb{padding:11px 20px;background:linear-gradient(135deg,var(--ac),#4f46e5);border:none;border-radius:10px;color:#fff;font-family:'Cabinet Grotesk',sans-serif;font-size:13px;font-weight:700;cursor:pointer;transition:all .2s;white-space:nowrap;}
.alb:hover{box-shadow:0 5px 16px rgba(99,102,241,.4);}
.uf-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:28px;}
.uf-card{background:var(--card);border:1px solid var(--b);border-radius:12px;padding:14px;text-align:center;}
.uf-icon{font-size:22px;margin-bottom:6px;}
.uf-title{font-family:'Cabinet Grotesk',sans-serif;font-size:12px;font-weight:700;margin-bottom:3px;}
.uf-desc{font-size:10px;color:var(--mu);line-height:1.4;}
.p-blinkit{background:rgba(255,220,0,.1);color:#fbbf24;}.p-instamart{background:rgba(249,115,22,.1);color:#fb923c;}.p-bigbasket{background:rgba(16,185,129,.08);color:#34d399;}.p-amazon{background:rgba(255,153,0,.1);color:#fb923c;}.p-flipkart{background:rgba(37,99,235,.1);color:#60a5fa;}.p-jiomart{background:rgba(244,63,94,.08);color:#f87171;}.p-croma{background:rgba(99,102,241,.1);color:#a5b4fc;}.p-meesho{background:rgba(236,72,153,.1);color:#f472b6;}.p-myntra{background:rgba(217,70,239,.1);color:#e879f9;}.p-reliance{background:rgba(59,130,246,.1);color:#93c5fd;}.p-apple{background:rgba(156,163,175,.1);color:#d1d5db;}.p-zepto{background:rgba(139,92,246,.1);color:#c4b5fd;}.p-default{background:rgba(255,255,255,.04);color:var(--mu);}
.toast{position:fixed;bottom:24px;right:24px;z-index:9999;padding:12px 18px;border-radius:10px;font-size:13px;font-weight:600;transform:translateY(80px);transition:transform .3s ease;min-width:200px;box-shadow:0 8px 24px rgba(0,0,0,.5);}
.toast.show{transform:translateY(0);}
.toast-s{background:#064e3b;border:1px solid #10b981;color:#6ee7b7;}
.toast-e{background:#4c0519;border:1px solid #f43f5e;color:#fda4af;}
.toast-i{background:#1e1b4b;border:1px solid var(--ac);color:#a5b4fc;}
@media(max-width:900px){.charts-grid{grid-template-columns:1fr;}.uf-row{grid-template-columns:repeat(2,1fr);}}
@media(max-width:640px){nav{padding:12px 18px;}#res{padding:20px;}.hero{padding:36px 18px 28px;}.pr-inner{grid-template-columns:44px 1fr;gap:10px;}.pr-mid,.pr-right{display:none;}.bd{flex-direction:column;}.ph{flex-direction:column;}}
</style></head>
<body>
<div class="bgw"><div class="mesh"></div><div class="grid"></div></div>
<div class="pg">
<nav>
  <div class="nl"><div class="li">&#128722;</div><div class="ln">Smart<span>Price</span></div></div>
  <div class="nr">
    <div class="up"><div class="ua" id="uAv">R</div><span style="font-size:12px;font-weight:600;" id="uNm">User</span></div>
    <button class="lb" onclick="logout()">Logout</button>
  </div>
</nav>
<section class="hero">
  <div class="badge"><span class="dot"></span> AI Price Intelligence Engine</div>
  <h1>Compare <span class="grad">Exact Prices</span><br>&amp; Predict Future Deals</h1>
  <p class="hs">Accurate platform prices &middot; 30-day history per platform &middot; Future price fall dates &middot; Buy Score</p>
  <div class="sw">
    <div class="sb">
      <span style="font-size:17px;">&#128269;</span>
      <input type="text" id="si" placeholder="e.g. Amul Taaza Milk, iPhone 15, boAt Rockerz 450..."/>
      <button class="sbtn" id="sBtn" onclick="doSearch()">Compare Now</button>
    </div>
    <div class="qs">
      <span class="chip" onclick="qs('Amul Taaza Milk 1L')">&#127965; Amul Milk</span>
      <span class="chip" onclick="qs('Samsung Galaxy S24')">&#128241; Samsung S24</span>
      <span class="chip" onclick="qs('boAt Rockerz 450')">&#127911; boAt Rockerz</span>
      <span class="chip" onclick="qs('Maggi Noodles')">&#127836; Maggi</span>
      <span class="chip" onclick="qs('iPhone 15')">&#128241; iPhone 15</span>
      <span class="chip" onclick="qs('Surf Excel 1kg')">&#129529; Surf Excel</span>
      <span class="chip" onclick="qs('OnePlus 12')">&#128241; OnePlus 12</span>
      <span class="chip" onclick="qs('Dettol Soap 75g')">&#129521; Dettol Soap</span>
      <span class="chip" onclick="qs('Dell i7 laptop')">&#128187; Dell i7 Laptop</span>
    </div>
  </div>
</section>
<div class="stats">
  <div class="sc"><div class="sn">9+</div><div class="sl2">Platforms</div></div>
  <div class="sc"><div class="sn">AI</div><div class="sl2">Predictions</div></div>
  <div class="sc"><div class="sn">30d</div><div class="sl2">Forecast</div></div>
  <div class="sc"><div class="sn" id="lc">--</div><div class="sl2">Searches Today</div></div>
</div>
<div id="ld">
  <div class="lds"><span></span><span></span><span></span></div>
  <div style="color:var(--mu);font-size:14px;margin-bottom:10px;">Analysing prices &amp; generating forecast...</div>
  <div id="ldS"></div>
</div>
<div id="res"><div class="ri">
  <div class="uf-row" id="ufRow" style="display:none;">
    <div class="uf-card"><div class="uf-icon">&#128202;</div><div class="uf-title">Exact Prices</div><div class="uf-desc">Accurate current price per platform, not estimates</div></div>
    <div class="uf-card"><div class="uf-icon">&#128302;</div><div class="uf-title">30-Day Forecast</div><div class="uf-desc">AI predicts when price will drop next with exact dates</div></div>
    <div class="uf-card"><div class="uf-icon">&#127942;</div><div class="uf-title">Buy Score</div><div class="uf-desc">Weighted: price + speed + stock + rating</div></div>
    <div class="uf-card"><div class="uf-icon">&#9200;</div><div class="uf-title">Buy Timing</div><div class="uf-desc">AI says: Buy Now / Wait / Neutral</div></div>
  </div>
  <div class="ph">
    <div class="pif" style="flex:1;">
      <div class="pm"><span class="badge2 bb" id="pBr"></span><span class="badge2 bc" id="pCa"></span></div>
      <h2 id="pN"></h2>
      <div class="pd" id="pDe"></div>
    </div>
    <div style="font-size:11px;color:var(--mu);text-align:right;flex-shrink:0;">&#128336; <strong id="pTi"></strong></div>
  </div>
  <div class="timing-banner" id="timingBanner">
    <div style="font-size:28px;" id="tbIcon"></div>
    <div class="tb-info"><h3 id="tbTitle"></h3><p id="tbDesc"></p></div>
    <div class="confidence"><div class="conf-num" id="confNum"></div><div class="conf-lbl">AI Confidence</div></div>
  </div>
  <div class="bd">
    <div class="bdl"><div style="font-size:28px;">&#127942;</div><div class="bdih"><h3 id="dPl"></h3><p>Lowest price across all platforms</p></div></div>
    <div class="bdp"><div class="pr" id="dPr"></div><div class="sv">Save <span id="dSv"></span> vs highest</div></div>
    <button class="vb" id="vBtn">Open Platform &rarr;</button>
  </div>
  <div class="ai-tip"><span style="font-size:18px;">&#129302;</span><div id="aiT"></div></div>
  <div id="srcBanner" style="display:none;align-items:center;gap:8px;padding:12px 18px;background:rgba(16,185,129,.05);border:1px solid rgba(16,185,129,.15);border-radius:12px;margin-bottom:16px;font-size:12px;flex-wrap:wrap;"></div>
  <div class="sec">&#128202; Platform Prices — Live Comparison</div>
  <div class="pg2" id="prG"></div>
  <div class="charts-grid">
    <div class="chart-card">
      <div class="chart-title">&#128200; 30-Day Price History</div>
      <div class="chart-note" id="histNote">Shows price history for all platforms over the last 30 days.</div>
      <div class="leg-row" id="histLeg"></div>
      <canvas id="histChart" height="200"></canvas>
    </div>
    <div class="chart-card" style="display:flex;flex-direction:column;gap:0;">
      <div class="chart-title">&#9201; What Should You Do? — AI Recommendation</div>
      <div id="recPanel" style="flex:1;display:flex;flex-direction:column;gap:12px;justify-content:center;padding:8px 0;"></div>
    </div>
  </div>
  <div class="chart-card full" style="margin-bottom:20px;">
    <div class="chart-title">&#128302; Price Forecast — Next 30 Days
      <span style="font-size:11px;font-weight:400;color:var(--mu);margin-left:8px;" id="fcPlatLabel"></span>
    </div>
    <div class="chart-note" id="fcNote"></div>
    <div style="display:flex;gap:18px;flex-wrap:wrap;margin-bottom:14px;align-items:center;">
      <div style="display:flex;align-items:center;gap:6px;font-size:12px;"><div style="width:28px;height:3px;background:#6366f1;border-radius:2px;"></div><span>Last 10 days (actual)</span></div>
      <div style="display:flex;align-items:center;gap:6px;font-size:12px;"><div style="width:28px;height:3px;background:#f97316;border-radius:2px;border-top:2px dashed #f97316;"></div><span>Forecast (predicted)</span></div>
      <div style="display:flex;align-items:center;gap:6px;font-size:12px;"><div style="width:12px;height:12px;border-radius:50%;background:#10b981;border:2px solid #fff;"></div><span>Predicted Sale Drop ↓</span></div>
      <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--mu);" id="fcSaleHint"></div>
    </div>
    <canvas id="fcChart" height="120"></canvas>
  </div>
  <div class="chart-card full" style="margin-bottom:20px;">
    <div class="chart-title">&#128202; Current Price by Platform</div>
    <div class="chart-note">
      <b style="color:#10b981;">Green</b> = cheapest &nbsp;|&nbsp;
      <b style="color:#f43f5e;">Red</b> = most expensive &nbsp;|&nbsp;
      <b style="color:#6366f1;">Blue</b> = mid-range &nbsp;· Hover a bar to see exact price
    </div>
    <canvas id="barChart" height="110"></canvas>
  </div>
  <div class="als">
    <div class="sec" style="margin-bottom:10px;">&#128276; Price Drop Alert</div>
    <p style="color:var(--mu);font-size:12px;margin-bottom:14px;">Set a target price — we will email you the moment the price drops below it</p>
    <div class="alr">
      <span style="font-size:13px;font-weight:600;white-space:nowrap;">Target ₹</span>
      <input type="number" class="ali" id="alP" placeholder="Enter target price"/>
      <button class="alb" onclick="openAlertModal()">&#128276; Set Alert</button>
    </div>
  </div>
</div></div>
</div>

<!-- Alert email modal -->
<div id="alertModalBg" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:1000;align-items:center;justify-content:center;padding:16px;">
  <div style="background:#0d1526;border:1px solid rgba(99,102,241,.35);border-radius:20px;width:100%;max-width:460px;overflow:hidden;animation:modalIn .28s cubic-bezier(.16,1,.3,1);">
    <div style="background:linear-gradient(135deg,#6366f1,#22d3ee);padding:24px 28px;">
      <div style="font-size:22px;font-weight:800;color:#fff;">Smart<span style="color:#a5f3fc;">Price</span></div>
      <div style="font-size:13px;color:rgba(255,255,255,.8);margin-top:3px;">Price drop alert</div>
    </div>
    <div style="padding:28px;">
      <div id="modalStep1">
        <div style="font-size:18px;font-weight:800;color:#f1f5f9;margin-bottom:6px;">Where should we notify you?</div>
        <div id="modalProductLine" style="font-size:13px;color:#64748b;margin-bottom:20px;line-height:1.6;"></div>
        <label style="font-size:12px;color:#94a3b8;display:block;margin-bottom:6px;">Your email address</label>
        <input type="email" id="modalEmail" placeholder="you@example.com"
          style="width:100%;height:44px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:10px;color:#f1f5f9;font-size:14px;padding:0 14px;outline:none;margin-bottom:16px;"
          onfocus="this.style.borderColor='#6366f1'" onblur="this.style.borderColor='rgba(255,255,255,.12)'"/>
        <div style="display:flex;gap:10px;">
          <button onclick="closeAlertModal()" style="flex:1;height:44px;border-radius:10px;border:1px solid rgba(255,255,255,.12);background:transparent;color:#94a3b8;font-size:14px;cursor:pointer;">Cancel</button>
          <button id="confirmBtn" onclick="confirmAlert()" style="flex:2;height:44px;border-radius:10px;border:none;background:linear-gradient(135deg,#6366f1,#22d3ee);color:#fff;font-size:14px;font-weight:700;cursor:pointer;">&#128276; Confirm alert</button>
        </div>
      </div>
      <div id="modalStep2" style="display:none;text-align:center;padding:8px 0;">
        <div style="font-size:48px;margin-bottom:12px;">&#10004;&#65039;</div>
        <div style="font-size:20px;font-weight:800;color:#10b981;margin-bottom:8px;">Alert set successfully!</div>
        <div id="modalSuccessMsg" style="font-size:13px;color:#64748b;line-height:1.7;margin-bottom:20px;"></div>
        <button onclick="closeAlertModal()" style="height:40px;padding:0 28px;border-radius:10px;border:1px solid rgba(16,185,129,.35);background:rgba(16,185,129,.1);color:#10b981;font-size:14px;font-weight:600;cursor:pointer;">Done</button>
      </div>
    </div>
  </div>
</div>
<style>@keyframes modalIn{from{opacity:0;transform:scale(.94) translateY(16px)}to{opacity:1;transform:none}}</style>

<div class="toast" id="toast"></div>
<script>
var PM = {
  Blinkit:{c:'p-blinkit',i:'&#9889;'},Instamart:{c:'p-instamart',i:'&#128717;'},
  BigBasket:{c:'p-bigbasket',i:'&#129530;'},Amazon:{c:'p-amazon',i:'&#128230;'},
  Flipkart:{c:'p-flipkart',i:'&#128722;'},JioMart:{c:'p-jiomart',i:'&#127978;'},
  Croma:{c:'p-croma',i:'&#128187;'},Meesho:{c:'p-meesho',i:'&#128509;'},
  Myntra:{c:'p-myntra',i:'&#128084;'},Reliance:{c:'p-reliance',i:'&#127978;'},
  'Apple Store':{c:'p-apple',i:'&#127822;'},Zepto:{c:'p-zepto',i:'&#128993;'}
};
function gm(n){return PM[n]||{c:'p-default',i:'&#127978;'};}
var cnt = Math.floor(Math.random()*500)+1200;
var histCI=null, fcCI=null, barCI=null;

document.addEventListener('DOMContentLoaded', function() {
  var u = {{ user|tojson }};
  document.getElementById('uNm').textContent = u.name;
  document.getElementById('uAv').textContent = u.name.charAt(0).toUpperCase();
  document.getElementById('lc').textContent = cnt.toLocaleString();
  setInterval(function(){cnt+=Math.floor(Math.random()*3);document.getElementById('lc').textContent=cnt.toLocaleString();},4000);
});
document.getElementById('si').addEventListener('keydown',function(e){if(e.key==='Enter')doSearch();});
function qs(q){document.getElementById('si').value=q;doSearch();}

async function doSearch() {
  var q = document.getElementById('si').value.trim();
  if(!q){showToast('Enter a product name','e');return;}
  document.getElementById('res').style.display='none';
  document.getElementById('ld').style.display='block';
  document.getElementById('sBtn').disabled=true;
  var steps=['Scraping Amazon & Flipkart for live prices...','Checking Blinkit, Zepto & BigBasket...','Running AI price prediction model...','Generating 30-day forecast...','Building comparison view...'];
  var sc=document.getElementById('ldS');sc.innerHTML='';
  steps.forEach(function(s,i){var d=document.createElement('div');d.className='lst';d.textContent=s;d.style.animationDelay=(i*0.55)+'s';sc.appendChild(d);});
  try {
    var r = await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});
    if(r.status===401){location.href='/';return;}
    var d = await r.json();
    document.getElementById('ld').style.display='none';
    document.getElementById('sBtn').disabled=false;
    if(d.success) renderResults(d);
    else showToast(d.message,'e');
  } catch(err) {
    document.getElementById('ld').style.display='none';
    document.getElementById('sBtn').disabled=false;
    showToast('Error: '+(err.message||'unknown'),'e');
  }
}

function renderResults(d) {
  document.getElementById('ufRow').style.display='grid';
  document.getElementById('pN').textContent=d.product;
  document.getElementById('pBr').textContent=d.brand;
  document.getElementById('pCa').textContent=d.category;
  document.getElementById('pTi').textContent=d.scraped_at;
  document.getElementById('pDe').textContent=d.description||'';
  document.getElementById('aiT').textContent=d.ai_tip;

  // ── Source summary banner ──────────────────────────────────────────────────
  var srcBanner = document.getElementById('srcBanner');
  if(srcBanner) {
    var lc = d.live_count || 0, dc = d.db_count || 0;
    if(lc > 0) {
      srcBanner.style.display='flex';
      srcBanner.innerHTML = '🟢 <b style="color:#34d399;">'+lc+' live price'+(lc>1?'s':'')+' scraped in real-time</b>'
        + (dc > 0 ? ' &nbsp;·&nbsp; <span style="color:var(--mu);">'+dc+' from database (platforms blocked scraping)</span>' : '')
        + ' &nbsp;·&nbsp; <span style="color:var(--mu);">Updated: '+d.scraped_at+'</span>';
    } else {
      srcBanner.style.display='none';
    }
  }

  var tb=document.getElementById('timingBanner');
  var cls={green:'tb-green',orange:'tb-orange',blue:'tb-blue'};
  tb.className='timing-banner '+(cls[d.timing.color]||'tb-blue');
  document.getElementById('tbIcon').textContent=d.timing.icon;
  document.getElementById('tbTitle').textContent=d.timing.recommendation;
  document.getElementById('tbDesc').textContent=d.timing.label;
  document.getElementById('confNum').textContent=d.timing.confidence+'%';

  document.getElementById('dPl').textContent='Best Deal: '+d.best_platform;
  document.getElementById('dPr').textContent='₹'+d.best_price.toLocaleString('en-IN');
  document.getElementById('dSv').textContent='₹'+d.savings.toLocaleString('en-IN');
  document.getElementById('alP').value=Math.floor(d.best_price*0.94);
  document.getElementById('vBtn').onclick=function(){window.open(d.prices[d.best_platform].url,'_blank');};
  // Store for use in setAlert()
  window._lastProductName  = d.product;
  window._lastBestPrice    = d.best_price;
  window._lastBestPlatform = d.best_platform;

  var grid=document.getElementById('prG'); grid.innerHTML='';
  var entries=Object.entries(d.prices);
  var currents=entries.map(function(e){return e[1].current;});
  var globalMin=Math.min.apply(null,currents), globalMax=Math.max.apply(null,currents);

  entries.forEach(function(entry, idx) {
    var nm=entry[0], info=entry[1];
    var m=gm(nm);
    var ib=nm===d.best_platform;
    var pc=info.current===globalMin?'lo':info.current===globalMax?'hi':'';
    var disc=info.mrp&&info.mrp>info.current?Math.round((info.mrp-info.current)/info.mrp*100):0;
    var savings=info.mrp&&info.mrp>info.current?(info.mrp-info.current):0;
    var isLive = info.price_source === 'live';
    var sourceBadge = isLive
      ? '<span style="font-size:9px;font-weight:700;padding:2px 7px;background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.3);border-radius:100px;color:#34d399;margin-left:6px;">🟢 LIVE</span>'
      : '<span style="font-size:9px;font-weight:700;padding:2px 7px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.25);border-radius:100px;color:#fbbf24;margin-left:6px;">📦 DB</span>';
    var row=document.createElement('a');
    row.className='pr-row'+(ib?' best':'');
    row.href=info.url; row.target='_blank'; row.rel='noopener noreferrer';
    row.style.cssText='position:relative;opacity:0;animation:ci .4s '+(idx*0.06)+'s cubic-bezier(.16,1,.3,1) forwards;';
    row.innerHTML='<div class="pr-inner">'
      +'<div class="pl '+m.c+'">'+m.i+'</div>'
      +'<div>'
        +'<div class="pn">'+nm+(ib?' <span style="font-size:10px;color:var(--gr);margin-left:4px;">✦ Best Price</span>':'')+sourceBadge+'</div>'
        +'<div class="pde">'+info.delivery+' &nbsp;·&nbsp; '+(info.delivery_fee==='Free'?'<span style="color:var(--gr);">Free delivery</span>':'Delivery: '+info.delivery_fee)+'</div>'
        +'<div style="margin-top:5px;display:flex;align-items:center;gap:6px;">'
          +'<div class="score-bar"><div class="score-fill" style="width:'+info.buy_score+'%;"></div></div>'
          +'<span class="score-val">Score '+info.buy_score+'/100</span>'
        +'</div>'
      +'</div>'
      +'<div class="pr-mid">'
        +'<div class="po">'+info.offer+'</div>'
        +'<div class="pra">'+info.rating+' ★ &nbsp;('+info.reviews.toLocaleString()+' reviews)</div>'
        +'<div class="'+(info.in_stock?'stk is':'stk os')+'">'+(info.in_stock?'✓ In Stock':'✗ Out of Stock')+'</div>'
      +'</div>'
      +'<div class="pr-right">'
        +'<div class="pp '+pc+'">₹'+info.current.toLocaleString('en-IN')+'</div>'
        +(info.mrp>info.current
          ? '<div class="disc" style="font-size:11px;">MRP ₹'+info.mrp.toLocaleString('en-IN')+' &nbsp;|&nbsp; Save ₹'+savings.toLocaleString('en-IN')+' ('+disc+'%)</div>'
          : '')
        +'<div style="font-size:10px;color:var(--ac);margin-top:4px;font-weight:600;">Tap to buy on '+nm+' ↗</div>'
      +'</div>'
      +'<div class="arrow">↗</div>'
      +'</div>';
    grid.appendChild(row);
  });

  buildCharts(d);
  document.getElementById('res').style.display='block';
  document.getElementById('res').scrollIntoView({behavior:'smooth',block:'start'});
}

function buildCharts(d) {
  if(histCI){histCI.destroy(); histCI=null;}
  if(fcCI){fcCI.destroy(); fcCI=null;}
  if(barCI){barCI.destroy(); barCI=null;}

  Chart.defaults.color='#64748b';
  Chart.defaults.borderColor='rgba(255,255,255,.06)';

  var platformColors = d.platform_colors || {};
  var defaultColors = ['#ff9900','#2874f0','#84cc16','#facc15','#a855f7','#f97316','#ef4444','#6366f1','#ec4899','#d946ef','#3b82f6','#94a3b8'];

  // ── HISTORY CHART: All platforms, separate colored lines ──────────────────
  var platforms = Object.keys(d.prices);
  var phist = d.platform_histories;

  document.getElementById('histNote').textContent =
    'Shows price history for ALL ' + platforms.length + ' platform(s) over the last 30 days. Each color = one platform.';

  // ── RECOMMENDATION PANEL (replaces cramped forecast card) ─────────────────
  var rec = d.timing;
  var recPanel = document.getElementById('recPanel');
  var iconMap = { green:'🟢', orange:'⏳', blue:'🔵' };
  var colMap  = { green:'var(--gr)', orange:'#f97316', blue:'var(--ac)' };
  recPanel.innerHTML =
    '<div style="font-size:36px;text-align:center;">'+rec.icon+'</div>'
    +'<div style="text-align:center;">'
      +'<div style="font-family:Cabinet Grotesk,sans-serif;font-size:20px;font-weight:800;color:'+colMap[rec.color]+';">'+rec.recommendation+'</div>'
      +'<div style="font-size:13px;color:var(--mu2);margin-top:8px;line-height:1.6;max-width:340px;margin-left:auto;margin-right:auto;">'+rec.label+'</div>'
    +'</div>'
    +'<div style="background:rgba(255,255,255,.04);border:1px solid var(--b);border-radius:10px;padding:14px;margin-top:4px;">'
      +'<div style="font-size:11px;color:var(--mu);margin-bottom:6px;text-transform:uppercase;letter-spacing:.08em;">AI Confidence</div>'
      +'<div style="height:8px;background:rgba(255,255,255,.06);border-radius:4px;">'
        +'<div style="height:100%;width:'+rec.confidence+'%;background:linear-gradient(90deg,var(--ac),var(--gr));border-radius:4px;transition:width .8s;"></div>'
      +'</div>'
      +'<div style="font-size:13px;font-weight:700;color:var(--ac2);margin-top:5px;">'+rec.confidence+'% confidence</div>'
    +'</div>'
    +'<div style="font-size:11px;color:var(--mu);text-align:center;padding-top:4px;">Next predicted sale: <b style="color:var(--go);">'+d.upcoming_sale+'</b></div>';

  // ── FORECAST CHART: Full width, clearly annotated ─────────────────────────
  var hist = d.price_history;
  var fc   = d.price_forecast;
  var saleAnnotations = d.sale_date_annotations || [];

  // Last 10 actual days + 30 forecast days
  var last10 = hist.slice(-10);
  var combinedLabels = last10.map(function(h){return h.date;}).concat(fc.map(function(f){return f.date;}));
  var histPrices = last10.map(function(h){return h.price;}).concat(new Array(fc.length).fill(null));
  var fcPrices   = new Array(10).fill(null).concat(fc.map(function(f){return f.price;}));
  var salePrices = new Array(10).fill(null).concat(fc.map(function(f){return f.is_predicted_sale?f.price:null;}));

  // Build sale hint text
  var saleLabels = {};
  saleAnnotations.forEach(function(s){ saleLabels[s.date] = s; });
  if(saleAnnotations.length > 0) {
    var sa = saleAnnotations[0];
    document.getElementById('fcSaleHint').innerHTML =
      '🟢 Sale predicted ~<b style="color:var(--gr);">' + sa.date + '</b> — price may drop to ₹' + sa.price.toLocaleString('en-IN');
  }

  var bestCol = platformColors[d.best_platform] || '#6366f1';

  // Platform label subtitle
  document.getElementById('fcPlatLabel').textContent = '(' + d.best_platform + ' — cheapest platform)';

  // Update fc note with plain English
  document.getElementById('fcNote').innerHTML =
    'The <b style="color:#6366f1;">solid line</b> shows the last 10 days of actual prices on <b>' + d.best_platform + '</b>. '
    + 'The <b style="color:#f97316;">dashed orange line</b> is the AI forecast for the next 30 days. '
    + '<b style="color:#10b981;">Green dots ●</b> mark days when the price is predicted to drop — good time to buy!';

  if(fcCI){fcCI.destroy(); fcCI=null;}
  fcCI = new Chart(document.getElementById('fcChart'), {
    type: 'line',
    data: {
      labels: combinedLabels,
      datasets: [
        {
          label: 'Actual Price (' + d.best_platform + ')',
          data: histPrices,
          borderColor: bestCol,
          backgroundColor: 'rgba(99,102,241,0.06)',
          borderWidth: 2.5,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
        },
        {
          label: 'Predicted Price',
          data: fcPrices,
          borderColor: '#f97316',
          borderDash: [6, 4],
          backgroundColor: 'rgba(249,115,22,0.07)',
          borderWidth: 2.5,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
        },
        {
          label: 'Predicted Sale Drop',
          data: salePrices,
          borderColor: 'transparent',
          backgroundColor: '#10b981',
          borderWidth: 0,
          pointRadius: salePrices.map(function(v){return v?10:0;}),
          pointBackgroundColor: '#10b981',
          pointBorderColor: '#fff',
          pointBorderWidth: 2.5,
          pointHoverRadius: 13,
          showLine: false,
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(12,16,28,0.96)',
          borderColor: 'rgba(99,102,241,0.3)',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            title: function(items) {
              var lbl = items[0].label;
              var idx = combinedLabels.indexOf(lbl);
              return lbl + (idx < 10 ? '  (actual)' : '  (forecast)');
            },
            label: function(ctx) {
              if(ctx.raw == null) return '';
              if(ctx.datasetIndex === 2) return '  🟢 Sale drop predicted — ₹' + ctx.raw.toLocaleString('en-IN');
              var prefix = ctx.datasetIndex === 0 ? '  Actual price: ' : '  Predicted price: ';
              return prefix + '₹' + ctx.raw.toLocaleString('en-IN');
            },
            afterLabel: function(ctx) {
              if(ctx.datasetIndex === 2 && saleLabels[ctx.label]) {
                return '  ' + saleLabels[ctx.label].label;
              }
              return '';
            }
          }
        },
        // Vertical divider between actual and forecast
        annotation: undefined,
      },
      scales: {
        y: {
          ticks: { callback: function(v){ return '₹'+Number(v).toLocaleString('en-IN'); }, font: { size: 11 } },
          grid: { color: 'rgba(255,255,255,.04)' },
          title: { display: true, text: 'Price (₹)', color: '#64748b', font: { size: 11 } }
        },
        x: {
          ticks: { maxTicksLimit: 10, font: { size: 11 } },
          grid: { display: false },
          // Mark the today divider
          afterDataLimits: function(scale) {
            scale._todayIdx = 9; // index of last actual point
          }
        }
      }
    }
  });

  // Draw a "TODAY" divider line on the canvas after render
  fcCI.options.animation = {
    onComplete: function() {
      var chart = fcCI;
      var ctx2 = chart.ctx;
      var meta = chart.getDatasetMeta(0);
      if(meta.data && meta.data[9]) {
        var x = meta.data[9].x;
        ctx2.save();
        ctx2.beginPath();
        ctx2.setLineDash([4,4]);
        ctx2.strokeStyle = 'rgba(255,255,255,0.2)';
        ctx2.lineWidth = 1.5;
        ctx2.moveTo(x, chart.chartArea.top);
        ctx2.lineTo(x, chart.chartArea.bottom);
        ctx2.stroke();
        ctx2.setLineDash([]);
        ctx2.fillStyle = 'rgba(255,255,255,0.35)';
        ctx2.font = '10px Space Grotesk, sans-serif';
        ctx2.textAlign = 'center';
        ctx2.fillText('TODAY', x, chart.chartArea.top - 4);
        ctx2.restore();
      }
    }
  };
  fcCI.update();

  // Build legend
  var legEl = document.getElementById('histLeg'); legEl.innerHTML='';
  var histDatasets = platforms.map(function(nm, i) {
    var col = platformColors[nm] || defaultColors[i % defaultColors.length];
    var histData = phist && phist[nm] ? phist[nm] : d.price_history;
    legEl.innerHTML += '<div class="leg-item"><div class="leg-dot" style="background:'+col+';"></div><span>'+nm+'</span></div>';
    return {
      label: nm,
      data: histData.map(function(h){return h.price;}),
      borderColor: col,
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      tension: 0.4,
      pointRadius: histData.map(function(h){return h.is_sale?4:0;}),
      pointBackgroundColor: col,
      pointBorderColor: '#fff',
      pointBorderWidth: 1,
    };
  });

  var histLabels = (phist && phist[platforms[0]]) ? phist[platforms[0]].map(function(h){return h.date;}) : d.price_history.map(function(h){return h.date;});

  histCI = new Chart(document.getElementById('histChart'), {
    type: 'line',
    data: { labels: histLabels, datasets: histDatasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: function(ctx){ return ctx.dataset.label+': ₹'+ctx.raw.toLocaleString('en-IN'); } } }
      },
      scales: {
        y: { ticks: { callback: function(v){ return '₹'+Number(v).toLocaleString('en-IN'); } }, grid: { color: 'rgba(255,255,255,.04)' } },
        x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } }
      }
    }
  });

  // ── BAR CHART: Current prices only — GREEN=cheapest, RED=most expensive, BLUE=rest ──
  var entries = Object.entries(d.prices);
  var labels   = entries.map(function(e){return e[0];});
  var currents = entries.map(function(e){return e[1].current;});
  var minVal = Math.min.apply(null, currents);
  var maxVal = Math.max.apply(null, currents);

  var barColors  = currents.map(function(v){ return v===minVal?'#10b981':v===maxVal?'#f43f5e':'#6366f1'; });
  var barBorders = currents.map(function(v){ return v===minVal?'#34d399':v===maxVal?'#fb7185':'#818cf8'; });

  barCI = new Chart(document.getElementById('barChart'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Current Price',
          data: currents,
          backgroundColor: barColors,
          borderColor: barBorders,
          borderWidth: 2,
          borderRadius: 8,
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          display: true,
          labels: {
            font: { size: 11 },
            color: '#94a3b8',
            generateLabels: function() {
              return [
                { text: 'Cheapest',       fillStyle: '#10b981', strokeStyle: '#34d399', lineWidth: 1 },
                { text: 'Most Expensive', fillStyle: '#f43f5e', strokeStyle: '#fb7185', lineWidth: 1 },
                { text: 'Mid-range',      fillStyle: '#6366f1', strokeStyle: '#818cf8', lineWidth: 1 },
              ];
            }
          }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              var suffix = ctx.raw===minVal?' ✦ CHEAPEST':ctx.raw===maxVal?' ✦ MOST EXPENSIVE':'';
              return 'Price: ₹'+ctx.raw.toLocaleString('en-IN')+suffix;
            }
          }
        }
      },
      scales: {
        y: { ticks: { callback: function(v){ return '₹'+Number(v).toLocaleString('en-IN'); } }, grid: { color: 'rgba(255,255,255,.04)' } },
        x: { grid: { display: false } }
      }
    }
  });
}

function openAlertModal() {
  var tp = document.getElementById('alP').value;
  if(!tp){showToast('Enter a target price first','e');return;}
  var pname = window._lastProductName || 'this product';
  var bestP = window._lastBestPrice || 0;
  var bestPl = window._lastBestPlatform || '';
  document.getElementById('modalProductLine').innerHTML =
    'We will email you when <b style="color:#a5b4fc;">' + pname + '</b> drops below '
    + '<b style="color:#10b981;">₹' + parseInt(tp).toLocaleString('en-IN') + '</b>'
    + (bestP ? ' &nbsp;·&nbsp; Current best: <b>₹' + bestP.toLocaleString('en-IN') + '</b> on ' + bestPl : '');
  document.getElementById('modalEmail').value = window._userEmail || '';
  document.getElementById('modalStep1').style.display = 'block';
  document.getElementById('modalStep2').style.display = 'none';
  document.getElementById('alertModalBg').style.display = 'flex';
}
function closeAlertModal() {
  document.getElementById('alertModalBg').style.display = 'none';
}
async function confirmAlert() {
  var email = document.getElementById('modalEmail').value.trim();
  var tp = document.getElementById('alP').value;
  if(!email || !email.includes('@')){
    document.getElementById('modalEmail').style.borderColor='#f43f5e';
    document.getElementById('modalEmail').focus(); return;
  }
  document.getElementById('modalEmail').style.borderColor='rgba(255,255,255,.12)';
  var btn = document.getElementById('confirmBtn');
  btn.textContent='Sending...'; btn.disabled=true;
  var payload = {
    target_price:   parseInt(tp),
    product_name:   window._lastProductName  || 'this product',
    best_price:     window._lastBestPrice    || 0,
    best_platform:  window._lastBestPlatform || '',
    email_override: email,
  };
  try {
    var r = await fetch('/api/price_alert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    var d = await r.json();
    btn.textContent='🔔 Confirm alert'; btn.disabled=false;
    if(d.success){
      var pname = window._lastProductName || 'this product';
      document.getElementById('modalSuccessMsg').innerHTML =
        'Your alert has been set for <b style="color:#a5b4fc;">' + pname + '</b> at <b style="color:#10b981;">₹' + parseInt(tp).toLocaleString('en-IN') + '</b>.<br><br>'
        + 'A confirmation email has been sent to <b style="color:#f1f5f9;">' + email + '</b>.<br>'
        + 'We will notify you the moment the price drops to your target.';
      document.getElementById('modalStep1').style.display='none';
      document.getElementById('modalStep2').style.display='block';
      document.getElementById('alP').value='';
    } else {
      showToast(d.message,'e'); closeAlertModal();
    }
  } catch(err){ btn.textContent='🔔 Confirm alert'; btn.disabled=false; showToast('Connection error','e'); }
}
document.addEventListener('DOMContentLoaded',function(){
  var bg=document.getElementById('alertModalBg');
  if(bg) bg.addEventListener('click',function(e){if(e.target===this)closeAlertModal();});
});
async function logout(){await fetch('/api/logout',{method:'POST'});location.href='/';}
function showToast(msg, t) {
  if(!t) t='s';
  var el=document.getElementById('toast');
  el.textContent=(t==='s'?'OK: ':t==='e'?'Error: ':'Info: ')+msg;
  el.className='toast show toast-'+t;
  setTimeout(function(){el.classList.remove('show');},4000);
}
var ss=document.createElement('style');
ss.textContent='@keyframes ci{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}';
document.head.appendChild(ss);
</script></body></html>"""

# =============================================================================
#  ROUTES
# =============================================================================
@app.route("/")
def index():
    # Already logged in via session → go straight to dashboard
    if "user" in session:
        return redirect(url_for("dashboard"))
    # Check remember-me cookie → auto-login without showing login page
    remembered_email = request.cookies.get("sp_remember_me")
    if remembered_email and remembered_email in USERS:
        session.permanent = True
        session["user"] = {"email": remembered_email, "name": USERS[remembered_email]["name"]}
        return redirect(url_for("dashboard"))
    return render_template_string(LOGIN_HTML)

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("index"))
    return render_template_string(DASHBOARD_HTML, user=session["user"])

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email","").strip().lower()
    pwd   = data.get("password","").strip()
    if not email or not pwd:
        return jsonify({"success":False,"message":"Email and password required."})
    if email not in USERS:
        return jsonify({"success":False,"message":"No account found."})
    if USERS[email]["password"] != pwd:
        return jsonify({"success":False,"message":"Incorrect password."})
    # Mark session as permanent (survives browser restart for 30 days)
    session.permanent = True
    session["user"] = {"email": email, "name": USERS[email]["name"]}
    # Set a long-lived remember-me cookie (30 days) — survives server restarts
    resp = make_response(jsonify({"success":True,"name":USERS[email]["name"],"redirect":"/dashboard"}))
    resp.set_cookie(
        "sp_remember_me", email,
        max_age=60*60*24*30,   # 30 days in seconds
        httponly=True,
        samesite="Lax",
    )
    return resp

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    resp = make_response(jsonify({"success":True}))
    resp.delete_cookie("sp_remember_me")  # clear remember-me so they aren't auto-logged back in
    return resp

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    name  = data.get("name","").strip()
    email = data.get("email","").strip().lower()
    pwd   = data.get("password","").strip()
    if not name or not email or not pwd:
        return jsonify({"success":False,"message":"All fields required."})
    if email in USERS:
        return jsonify({"success":False,"message":"Account already exists."})
    if len(pwd) < 8:
        return jsonify({"success":False,"message":"Password must be 8+ characters."})
    USERS[email] = {"password":pwd,"name":name}
    session.permanent = True
    session["user"] = {"email":email,"name":name}
    resp = make_response(jsonify({"success":True,"name":name,"redirect":"/dashboard"}))
    resp.set_cookie(
        "sp_remember_me", email,
        max_age=60*60*24*30,
        httponly=True,
        samesite="Lax",
    )
    return resp

@app.route("/api/search", methods=["POST"])
@login_required
def search_product():
    data = request.get_json()
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"success": False, "message": "Please enter a product name."})

    product = match_product(query)
    platforms = product["platforms"]
    fallback_urls = build_urls(product["name"])

    # ── STEP 1: Fire live scrapers in parallel for all DB platforms ──────────
    platform_names = list(platforms.keys())
    live_results = {}
    if SCRAPER_AVAILABLE:
        try:
            live_results = scrape_all_platforms(query, platform_names)
        except Exception:
            live_results = {}

    # ── STEP 2: Build prices_out — prefer live price, fall back to DB ────────
    prices_out = {}
    for pname, pinfo in platforms.items():
        live = live_results.get(pname)

        if live and live.get("price") and live["price"] > 0:
            # ✅ Got a real scraped price
            current      = live["price"]
            price_source = "live"
            # Use the scraped product URL if we got one, else direct_url
            url = (live.get("url") or
                   pinfo.get("direct_url") or
                   fallback_urls.get(pname, ""))
        else:
            # ⚠️ Scrape failed / blocked — fall back to hardcoded DB price
            current      = pinfo["typical"]
            price_source = "db"
            url = (pinfo.get("direct_url") or
                   fallback_urls.get(pname) or
                   f"https://www.google.com/search?q={urllib.parse.quote_plus(product['name'] + ' ' + pname)}")

        score = compute_buy_score(
            current, pinfo["min"], pinfo["max"],
            pinfo["rating"], pinfo["delivery"],
            pinfo["in_stock"],
            pinfo["delivery_fee"] in ("Free", "free")
        )

        prices_out[pname] = {
            "min":          pinfo["min"],
            "max":          pinfo["max"],
            "current":      current,
            "mrp":          pinfo["mrp"],
            "delivery":     pinfo["delivery"],
            "delivery_fee": pinfo["delivery_fee"],
            "offer":        pinfo["offer"],
            "in_stock":     pinfo["in_stock"],
            "rating":       pinfo["rating"],
            "reviews":      pinfo["reviews"],
            "buy_score":    score,
            "url":          url,
            "price_source": price_source,   # "live" or "db"
        }

    # ── STEP 3: Sort by current price ────────────────────────────────────────
    prices_out = dict(sorted(prices_out.items(), key=lambda x: x[1]["current"]))
    best_platform = list(prices_out.keys())[0]
    best_price    = prices_out[best_platform]["current"]
    max_price     = max(v["current"] for v in prices_out.values())
    savings       = max_price - best_price

    # Count how many platforms returned live prices
    live_count = sum(1 for v in prices_out.values() if v["price_source"] == "live")
    db_count   = sum(1 for v in prices_out.values() if v["price_source"] == "db")

    pred = generate_price_history_and_forecast(best_price, product["category"], platforms)

    # Build AI tip with honest source info
    if live_count > 0:
        source_note = f"🟢 {live_count} live price(s) scraped in real-time. {db_count} from database."
    else:
        source_note = f"Best deal on {best_platform} at ₹{best_price:,}. MRP: ₹{prices_out[best_platform]['mrp']:,}."

    tips = [
        source_note,
        f"Best deal on {best_platform} at ₹{best_price:,}. MRP: ₹{prices_out[best_platform]['mrp']:,}.",
        f"Next predicted sale around {pred['upcoming_sale_day']}. AI confidence: {pred['timing']['confidence']}%.",
        f"Buy Score ranks platforms by price + delivery speed + rating + stock.",
    ]

    return jsonify({
        "success":           True,
        "product":           product["name"],
        "brand":             product["brand"],
        "category":          product["category"],
        "description":       product.get("description", ""),
        "prices":            prices_out,
        "best_platform":     best_platform,
        "best_price":        best_price,
        "max_price":         max_price,
        "savings":           savings,
        "live_count":        live_count,
        "db_count":          db_count,
        "price_history":     pred["history"],
        "price_forecast":    pred["forecast"],
        "platform_histories":pred["platform_histories"],
        "platform_colors":   pred["platform_colors"],
        "sale_date_annotations": pred["sale_date_annotations"],
        "timing":            pred["timing"],
        "upcoming_sale":     pred["upcoming_sale_day"],
        "scraped_at":        datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "ai_tip":            tips[int(datetime.now().second / 15) % len(tips)],
    })


@app.route("/api/cache_stats")
@login_required
def cache_stats():
    """Debug endpoint — shows what's cached and when it expires."""
    stats = get_cache_stats() if SCRAPER_AVAILABLE else {"error": "scraper not loaded"}
    stats["scraper_available"] = SCRAPER_AVAILABLE
    return jsonify(stats)

@app.route("/api/price_alert", methods=["POST"])
@login_required
def price_alert():
    data         = request.get_json()
    target_price = data.get("target_price")
    product_name = data.get("product_name", "this product")
    best_price   = data.get("best_price", 0)
    best_platform= data.get("best_platform", "")
    user_email   = data.get("email_override", "").strip() or session["user"]["email"]

    if not target_price:
        return jsonify({"success": False, "message": "Target price is required."})

    try:
        target_price = int(float(target_price))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid target price."})

    # Store alert in memory (swap for DB in production)
    PRICE_ALERTS.append({
        "email":         user_email,
        "product_name":  product_name,
        "target_price":  target_price,
        "current_best":  best_price,
        "best_platform": best_platform,
        "set_at":        datetime.now().isoformat(),
        "fulfilled":     False,
    })

    # Send confirmation email
    sent = send_alert_confirmation(
        to_addr       = user_email,
        product_name  = product_name,
        target_price  = target_price,
        best_price    = int(best_price) if best_price else target_price,
        best_platform = best_platform,
    )

    msg = (
        f"Alert set for ₹{target_price:,}! "
        f"Confirmation email sent to {user_email}."
        if sent else
        f"Alert saved for ₹{target_price:,}. (Email delivery failed — check server config.)"
    )
    return jsonify({"success": True, "message": msg})

@app.route("/api/test_email")
@login_required
def test_email():
    """Debug endpoint — sends a test email to the logged-in user to verify SMTP config."""
    user_email = session["user"]["email"]
    ok = _send_email(
        to_addr   = user_email,
        subject   = "SmartPrice — SMTP test",
        html_body = f"<p>SMTP is working! Sent to <b>{user_email}</b>.</p>",
        text_body = f"SMTP is working! Sent to {user_email}.",
    )
    config_status = {
        "EMAIL_ENABLED": EMAIL_ENABLED,
        "EMAIL_HOST": EMAIL_HOST,
        "EMAIL_PORT": EMAIL_PORT,
        "EMAIL_USER": EMAIL_USER,
        "EMAIL_PASS": "****" if EMAIL_PASS not in ("your_app_password_here","") else "NOT SET",
        "sent_to": user_email,
        "result": "SUCCESS" if ok else "FAILED — check server terminal for error",
    }
    return jsonify(config_status)

if __name__ == "__main__":
    app.run(debug=True, port=5000)