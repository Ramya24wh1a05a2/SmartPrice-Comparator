// services/mailer.js - email via Nodemailer (replaces smtplib)
const nodemailer = require("nodemailer");

const cfg = () => ({
  enabled: (process.env.EMAIL_ENABLED || "true").toLowerCase() === "true",
  host: process.env.EMAIL_HOST || "smtp.gmail.com",
  port: parseInt(process.env.EMAIL_PORT || "587", 10),
  user: process.env.EMAIL_USER || "",
  pass: process.env.EMAIL_PASS || "",
  from: process.env.EMAIL_FROM || `SmartPrice <${process.env.EMAIL_USER || "no-reply@smartprice.local"}>`,
});

const inr = (n) => "₹" + Number(n).toLocaleString("en-IN");
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function sendEmail(to, subject, html, text = "") {
  const c = cfg();
  if (!c.enabled) { console.log(`[EMAIL DISABLED] Would send to ${to}: ${subject}`); return true; }
  if (!c.user || !c.pass || c.user === "your_email@gmail.com") {
    console.error("[EMAIL ERROR] EMAIL_USER / EMAIL_PASS not configured in .env");
    return false;
  }
  try {
    const transport = nodemailer.createTransport({
      host: c.host, port: c.port, secure: c.port === 465, auth: { user: c.user, pass: c.pass },
    });
    await transport.sendMail({ from: c.from, to, subject, text, html });
    console.log(`[EMAIL] Sent to ${to}: ${subject}`);
    return true;
  } catch (err) {
    console.error("[EMAIL ERROR]", err.message);
    return false;
  }
}

function sendAlertConfirmation(to, productName, targetPrice, bestPrice, bestPlatform) {
  const html = `<!DOCTYPE html><html><body style="margin:0;padding:24px;background:#0a0f1e;font-family:Segoe UI,Arial,sans-serif;">
<table width="560" align="center" style="background:#0d1526;border-radius:16px;overflow:hidden;border:1px solid rgba(99,102,241,.25);">
<tr><td style="background:linear-gradient(135deg,#6366f1,#22d3ee);padding:26px 32px;">
  <div style="font-size:22px;font-weight:800;color:#fff;">Smart<span style="color:#a5f3fc;">Price</span></div>
  <div style="font-size:13px;color:rgba(255,255,255,.8);">AI Price Intelligence</div></td></tr>
<tr><td style="padding:32px;">
  <h1 style="margin:0 0 8px;font-size:22px;color:#f1f5f9;">✅ Price alert confirmed!</h1>
  <p style="color:#64748b;font-size:14px;line-height:1.7;">We'll notify you at <b style="color:#a5b4fc;">${esc(to)}</b> the moment the price drops to your target.</p>
  <div style="background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.2);border-radius:12px;padding:20px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Product</div>
    <div style="font-size:17px;font-weight:700;color:#f1f5f9;margin-bottom:16px;">${esc(productName)}</div>
    <table width="100%"><tr>
      <td><div style="font-size:11px;color:#64748b;">Current best price</div><div style="font-size:24px;font-weight:800;color:#f1f5f9;">${inr(bestPrice)}</div><div style="font-size:12px;color:#64748b;">on ${esc(bestPlatform)}</div></td>
      <td><div style="font-size:11px;color:#64748b;">Your alert target</div><div style="font-size:24px;font-weight:800;color:#10b981;">${inr(targetPrice)}</div><div style="font-size:12px;color:#10b981;">We alert you at or below this</div></td>
    </tr></table></div>
</td></tr></table></body></html>`;
  const text = `Price alert confirmed for: ${productName}\nCurrent best price: ${inr(bestPrice)} (on ${bestPlatform})\nYour target: ${inr(targetPrice)}\n\n— SmartPrice Team`;
  return sendEmail(to, `✅ Price alert set — ${productName}`, html, text);
}

function sendPriceDropNotification(to, productName, targetPrice, newPrice, platform) {
  const html = `<div style="font-family:Segoe UI,Arial,sans-serif;background:#0d1526;color:#f1f5f9;padding:28px;border-radius:14px;">
<h2>🔔 The price dropped!</h2>
<p><b>${esc(productName)}</b> reached your target on <b style="color:#10b981;">${esc(platform)}</b>.</p>
<p>Your target: ${inr(targetPrice)}<br>Current price: <b style="color:#10b981;font-size:22px;">${inr(newPrice)}</b></p></div>`;
  return sendEmail(to, `🔔 Price dropped! ${productName} is now ${inr(newPrice)}`, html,
    `${productName} dropped to ${inr(newPrice)} on ${platform} (target ${inr(targetPrice)}).`);
}

module.exports = { sendEmail, sendAlertConfirmation, sendPriceDropNotification, cfg };
