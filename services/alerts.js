// services/alerts.js - background job that emails users when a price reaches their target.
const cron = require("node-cron");
const { q } = require("../db");
const { getPriceData } = require("./pricing");
const mailer = require("./mailer");

let running = false;

async function checkAlerts() {
  if (running) return { skipped: true };
  running = true;
  const summary = { checked: 0, sent: 0 };
  try {
    const pending = await q.pendingAlerts();
    const groups = new Map();                       // one price lookup per product, not per alert
    for (const a of pending) (groups.get(a.search_query) || groups.set(a.search_query, []).get(a.search_query)).push(a);

    for (const [query, alerts] of groups) {
      const data = await getPriceData(query);
      const entries = Object.entries(data.platforms);
      if (!entries.length) continue;
      const [bestPlatform, best] = entries.reduce((a, b) => (b[1].typical < a[1].typical ? b : a));
      for (const a of alerts) {
        summary.checked++;
        if (best.typical <= a.target_price) {
          const ok = await mailer.sendPriceDropNotification(a.email, a.product_name, a.target_price, best.typical, bestPlatform);
          if (ok) { await q.markAlertDone(a.id); summary.sent++; }
        }
      }
    }
  } catch (e) {
    console.error("[ALERTS] check failed:", e.message);
  } finally { running = false; }
  console.log(`[ALERTS] checked ${summary.checked}, notified ${summary.sent}`);
  return summary;
}

function startAlertJob() {
  const expr = process.env.ALERT_CRON || "0 */6 * * *";   // default: every 6 hours
  if (!cron.validate(expr)) { console.warn(`[ALERTS] invalid ALERT_CRON "${expr}", job not started`); return; }
  cron.schedule(expr, checkAlerts);
  console.log(`[ALERTS] background checker scheduled (${expr})`);
}

module.exports = { checkAlerts, startAlertJob };
