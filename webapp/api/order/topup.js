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

function sendTelegramMessage(botToken, chatId, text, inlineKeyboard) {
  return new Promise((resolve) => {
    const payload = JSON.stringify({
      chat_id: chatId,
      text: text,
      parse_mode: 'HTML',
      reply_markup: inlineKeyboard ? { inline_keyboard: inlineKeyboard } : undefined,
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

  const body = req.body || {};
  let userId = body.telegram_id || body.user_id;
  const amount = parseInt(body.amount, 10);
  const paymentMethod = body.payment_method || 'card';

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

  if (!userId || isNaN(amount) || amount < 1000) {
    return res.status(400).json({ ok: false, error: 'Invalid parameters' });
  }

  const orderId = 'TOP_' + Date.now();
  const botToken = process.env.BOT_TOKEN || '8540635645:AAE3c-NEqdR4F05X_7Vyiq7kP3XD5PmzX7Y';
  const adminId = 8202423244;

  try {
    const db = getPool();
    await db.query(
      `INSERT INTO orders (telegram_id, product_type, amount, status, external_id, created_at)
       VALUES ($1, 'topup', $2, 'pending', $3, NOW())`,
      [userId, amount, orderId]
    ).catch(e => console.error('Error recording order:', e));

    const adminText = 
      `💳 <b>YANGI BALANS TO'LDIRISH SO'ROVI!</b>\n\n` +
      `👤 Foydalanuvchi ID: <code>${userId}</code>\n` +
      `💰 Summa: <b>${amount.toLocaleString('uz-UZ')} so'm</b>\n` +
      `📌 To'lov usuli: <b>${paymentMethod.toUpperCase()}</b>\n` +
      `🆔 Buyurtma ID: <code>${orderId}</code>\n\n` +
      `<i>Foydalanuvchi kartaga pul o'tkazganini tasdiqlagan bo'lsa, quyidagi tugma orqali tasdiqlang:</i>`;

    const keyboard = [
      [
        { text: '✅ Tasdiqlash (+ pul qo\'shish)', callback_data: `approve_topup_${orderId}_${userId}_${amount}` },
      ],
      [
        { text: '❌ Bekor qilish (Rad etish)', callback_data: `reject_topup_${orderId}_${userId}` },
      ],
    ];

    await sendTelegramMessage(botToken, adminId, adminText, keyboard);

    return res.status(200).json({
      ok: true,
      order_id: orderId,
      amount: amount,
      status: 'pending',
    });
  } catch (err) {
    console.error('Topup request error:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
