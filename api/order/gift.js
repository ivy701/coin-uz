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

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  return res.status(503).json({
    ok: false,
    error: "🔧 Hozirda Telegram Sovg'alari (Gift) bo'limida texnik ishlar olib borilmoqda. Xizmat tez orada qayta ishga tushadi!"
  });

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

  if (!userId || !username || isNaN(price) || price <= 0) {
    return res.status(400).json({ ok: false, error: 'Ma\'lumotlar to\'liq emas' });
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

    // Deduct balance
    const newBal = balance - price;
    await db.query('UPDATE users SET balance = $1 WHERE telegram_id = $2', [newBal, userId]);

    // Record order
    const orderRes = await db.query(
      `INSERT INTO orders (telegram_id, product_type, target_username, quantity, amount, status, external_id, created_at)
       VALUES ($1, 'gift', $2, 1, $3, 'completed', $4, NOW()) RETURNING id`,
      [userId, username, price, 'GIFT_' + Date.now()]
    );

    // Send confirmation message in Telegram Bot
    const targetStr = `@${username.replace(/^@/, '')}`;
    const channelId = process.env.CHANNEL_ORDERS || '@coinstatuz_org';

    const userMsg = 
      `🎁 <b>SOVG'A XARID QILINDI!</b>\n\n` +
      `🎁 Sovg'a: <b>${giftName}</b>\n` +
      `👤 Qabul qiluvchi: <b>${targetStr}</b>\n` +
      `💰 To'langan: <b>${price.toLocaleString('uz-UZ')} so'm</b>\n` +
      `👛 Qolgan balans: <b>${newBal.toLocaleString('uz-UZ')} so'm</b>\n\n` +
      `<i>Sovg'a tez orada foydalanuvchi profiliga yetkaziladi!</i>`;

    const channelMsg = 
      `🎁 <b>CoinStat UZ — Telegram Gift Yuborildi!</b>\n\n` +
      `🎯 <b>Qabul qiluvchi:</b> ${targetStr}\n` +
      `💫 <b>Gift:</b> ${giftName} 🎁\n` +
      `💰 <b>Summa:</b> ${price.toLocaleString('uz-UZ')} so'm\n\n` +
      `🚀 Gift sovg'asi muvaffaqiyatli yetkazildi!\n` +
      `🌐 <b>Kanal:</b> @coinstatuz_org | 🤖 <b>Bot:</b> @CoinStatuz_bot`;

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
    console.error('Gift order error:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
