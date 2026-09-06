const { Pool } = require('pg');
const https = require('https');

let pool;
function getPool() {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL || 'postgresql://neondb_owner:npg_gbusDUvG1z8M@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require';
    pool = new Pool({
      connectionString,
      ssl: { rejectUnauthorized: false },
      max: 5,
    });
  }
  return pool;
}

function sendTelegramMessage(botToken, chatId, text) {
  return new Promise((resolve) => {
    const payload = JSON.stringify({
      chat_id: chatId,
      text: text,
      parse_mode: 'HTML',
    });

    const options = {
      hostname: 'api.telegram.org',
      port: 443,
      path: `/bot${botToken}/sendMessage`,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(true));
    });

    req.on('error', () => resolve(false));
    req.write(payload);
    req.end();
  });
}

function callFragmentApi(endpoint, body) {
  return new Promise((resolve, reject) => {
    const apiKey = process.env.FRAGMENT_API_KEY || 'b66c0e21a8b6a2d76c9861550e7c0349c1ece0b2';
    const payload = JSON.stringify(body);

    const options = {
      hostname: 'fragment-api.uz',
      port: 443,
      path: `/api/v1/${endpoint.replace(/^\//, '')}`,
      method: 'POST',
      headers: {
        'X-API-Key': apiKey,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
      timeout: 15000,
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve(json);
        } catch (e) {
          resolve({ ok: res.statusCode < 400, raw: data });
        }
      });
    });

    req.on('error', (err) => resolve({ ok: false, error: err.message }));
    req.on('timeout', () => {
      req.destroy();
      resolve({ ok: false, error: 'Fragment API timeout' });
    });
    req.write(payload);
    req.end();
  });
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const body = req.body || {};
  let userId = body.telegram_id || body.user_id;
  const username = (body.username || '').replace(/^@/, '').trim();
  const quantity = parseInt(body.quantity || body.amount, 10);

  if (!userId && body.initData) {
    try {
      const params = new URLSearchParams(body.initData);
      const userStr = params.get('user');
      if (userStr) {
        const u = JSON.parse(userStr);
        userId = u.id;
      }
    } catch (e) {}
  }

  if (!userId || !username || isNaN(quantity) || quantity < 50 || quantity > 1000000) {
    return res.status(400).json({ ok: false, error: "Ma'lumotlar noto'g'ri (min: 50, max: 1 000 000)" });
  }

  const price = quantity * 200; // 200 so'm per star
  const botToken = process.env.BOT_TOKEN || '8540635645:AAE3c-NEqdR4F05X_7Vyiq7kP3XD5PmzX7Y';

  try {
    const db = getPool();
    const userRes = await db.query('SELECT balance FROM users WHERE telegram_id = $1', [userId]);
    const balance = userRes.rows.length > 0 ? Number(userRes.rows[0].balance || 0) : 0;

    if (balance < price) {
      return res.status(400).json({
        ok: false,
        error: `Balansingiz yetarli emas!\nKerak: ${price.toLocaleString('uz-UZ')} so'm\nSizda: ${balance.toLocaleString('uz-UZ')} so'm`,
      });
    }

    // Call Fragment API to send stars
    const fragRes = await callFragmentApi('stars/buy', { username: username, amount: quantity });

    // Deduct balance
    const newBal = balance - price;
    await db.query('UPDATE users SET balance = $1 WHERE telegram_id = $2', [newBal, userId]);

    // Record order
    const orderRes = await db.query(
      `INSERT INTO orders (telegram_id, product_type, target_username, quantity, amount, status, external_id, created_at)
       VALUES ($1, 'stars', $2, $3, $4, 'completed', $5, NOW()) RETURNING id`,
      [userId, username, quantity, price, fragRes?.id ? String(fragRes.id) : null]
    );

    // Send confirmation message in Telegram Bot
    const userMsg = 
      `⭐️ <b>STARS XARID QILINDI!</b>\n\n` +
      `👤 Qabul qiluvchi: <b>@${username}</b>\n` +
      `💫 Miqdor: <b>${quantity.toLocaleString('uz-UZ')} Stars</b>\n` +
      `💰 To'langan: <b>${price.toLocaleString('uz-UZ')} so'm</b>\n` +
      `👛 Qolgan balans: <b>${newBal.toLocaleString('uz-UZ')} so'm</b>\n\n` +
      `<i>Xaridingiz uchun rahmat! Stars tez orada hisobingizga tushadi.</i>`;

    await sendTelegramMessage(botToken, userId, userMsg);

    return res.status(200).json({
      ok: true,
      balance: newBal,
      order_id: orderRes.rows[0]?.id,
    });
  } catch (err) {
    console.error('Order stars error:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
