const { Pool } = require('pg');
const https = require('https');

let pool;
function getPool() {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL || 'postgresql://neondb_owner:npg_FOH4kIY9gEte@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require';
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
  return new Promise((resolve) => {
    const apiKey = (process.env.FRAGMENT_API_KEY || 'b66c0e21a8b6a2d76c9861550e7c0349c1ece0b2').trim();
    const payload = JSON.stringify(body);

    const options = {
      hostname: 'fragment-api.uz',
      port: 443,
      path: `/api/v1/${endpoint.replace(/^\//, '')}`,
      method: 'POST',
      headers: {
        'X-API-Key': apiKey,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
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
          const isSuccess = res.statusCode < 400 && json.ok !== false;
          resolve({ status: res.statusCode, ok: isSuccess, data: json });
        } catch (e) {
          resolve({ status: res.statusCode, ok: false, error: 'Fragment API javobida xatolik', raw: data });
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
  const productType = body.product_type || 'stars';
  const months = parseInt(body.months, 10);

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

  if (!userId) {
    return res.status(400).json({ ok: false, error: "Telegram ID aniqlanmadi" });
  }

  // Determine actual Price & Quantity
  let quantity = 0;
  let price = 0;

  if (productType.toLowerCase().includes('premium')) {
    price = parseInt(body.amount, 10);
    if (!price || isNaN(price)) {
      if (months === 12) price = 390000;
      else if (months === 6) price = 225000;
      else price = 160000;
    }
    quantity = months || 3;
  } else if (productType.toLowerCase().includes('nomer')) {
    price = parseInt(body.amount, 10) || 18000;
    quantity = 1;
  } else {
    quantity = parseInt(body.quantity, 10) || 50;
    price = parseInt(body.amount, 10);
    
    if (!price || isNaN(price)) {
      price = quantity * 198;
    }
  }

  if (price <= 0) {
    return res.status(400).json({ ok: false, error: "Noto'g'ri summa" });
  }

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

    // Call Fragment API if relevant (Stars or Premium)
    let fragRes = null;
    if (productType.toLowerCase().includes('premium')) {
      fragRes = await callFragmentApi('premium/buy', { username: username, months: quantity });
    } else if (!productType.toLowerCase().includes('nomer')) {
      fragRes = await callFragmentApi('stars/buy', { username: username, amount: quantity });
    }

    // STRICT VALIDATION: If Fragment API failed (e.g. insufficient funds in Fragment wallet), reject order and DO NOT deduct balance!
    if (fragRes && !fragRes.ok) {
      const errMsg = fragRes.data?.message || fragRes.error || "Hamyonda to'lov uchun yetarli mablag' yo'q.";
      return res.status(400).json({
        ok: false,
        error: `⚠️ Xarid amalga oshmadi: ${errMsg}`,
      });
    }

    // Deduct balance only after successful API call
    const newBal = balance - price;
    await db.query('UPDATE users SET balance = $1 WHERE telegram_id = $2', [newBal, userId]);

    // Record completed order
    const orderRes = await db.query(
      `INSERT INTO orders (telegram_id, product_type, target_username, quantity, amount, status, external_id, created_at)
       VALUES ($1, $2, $3, $4, $5, 'completed', $6, NOW()) RETURNING id`,
      [userId, productType, username, quantity, price, fragRes?.data?.result?.id ? String(fragRes.data.result.id) : null]
    );

    // Send confirmation message in Telegram Bot
    let userMsg = '';
    let channelMsg = '';
    const channelId = process.env.CHANNEL_ORDERS || '@coinstatuz_org';
    const targetStr = username ? `@${username.replace(/^@/, '')}` : `ID: ${userId}`;

    if (productType.toLowerCase().includes('premium')) {
      userMsg = 
        `👑 <b>TELEGRAM PREMIUM XARID QILINDI!</b>\n\n` +
        `👤 Qabul qiluvchi: <b>${targetStr}</b>\n` +
        `⏳ Muddat: <b>${quantity} Oylik</b>\n` +
        `💰 To'langan: <b>${price.toLocaleString('uz-UZ')} so'm</b>\n` +
        `👛 Qolgan balans: <b>${newBal.toLocaleString('uz-UZ')} so'm</b>\n\n` +
        `<i>Premium faollashtirildi!</i>`;

      channelMsg = 
        `💎 <b>CoinStat UZ — Premium Muvaffaqiyatli Yuborildi!</b>\n\n` +
        `🎯 <b>Qabul qiluvchi:</b> ${targetStr}\n` +
        `📅 <b>Muddat:</b> ${quantity} oy\n` +
        `💰 <b>Summa:</b> ${price.toLocaleString('uz-UZ')} so'm\n\n` +
        `🚀 Premium obuna muvaffaqiyatli faollashtirildi!\n` +
        `🌐 <b>Kanal:</b> @coinstatuz_org | 🤖 <b>Bot:</b> @CoinStatuz_bot`;
    } else {
      userMsg = 
        `⭐️ <b>STARS XARID QILINDI!</b>\n\n` +
        `👤 Qabul qiluvchi: <b>${targetStr}</b>\n` +
        `💫 Miqdor: <b>${quantity.toLocaleString('uz-UZ')} Stars</b>\n` +
        `💰 To'langan: <b>${price.toLocaleString('uz-UZ')} so'm</b>\n` +
        `👛 Qolgan balans: <b>${newBal.toLocaleString('uz-UZ')} so'm</b>\n\n` +
        `<i>Xaridingiz uchun rahmat! Stars hisobingizga tushdi.</i>`;

      channelMsg = 
        `⭐️ <b>CoinStat UZ — Stars Muvaffaqiyatli Yuborildi!</b>\n\n` +
        `🎯 <b>Qabul qiluvchi:</b> ${targetStr}\n` +
        `💫 <b>Miqdor:</b> ${quantity.toLocaleString('uz-UZ')} Stars\n` +
        `💰 <b>Summa:</b> ${price.toLocaleString('uz-UZ')} so'm\n\n` +
        `🚀 Stars hisobga muvaffaqiyatli o'tkazildi!\n` +
        `🌐 <b>Kanal:</b> @coinstatuz_org | 🤖 <b>Bot:</b> @CoinStatuz_bot`;
    }

    await Promise.allSettled([
      sendTelegramMessage(botToken, userId, userMsg),
      sendTelegramMessage(botToken, channelId, channelMsg),
    ]);

    return res.status(200).json({
      ok: true,
      balance: newBal,
      order_id: orderRes.rows[0]?.id,
    });
  } catch (err) {
    console.error('Order processing error:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
