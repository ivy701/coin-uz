const { Pool } = require('pg');
const https = require('https');
const crypto = require('crypto');

let pool;
function getPool() {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error("DATABASE_URL muhit o'zgaruvchisi sozlanmagan!");
    }
    pool = new Pool({
      connectionString,
      ssl: { rejectUnauthorized: false },
      max: 5,
    });
  }
  return pool;
}

// In-memory rate limiter: max 5 requests per 60 seconds per user
const rateLimitMap = new Map();
function checkRateLimit(userId, maxRequests = 5, windowMs = 60000) {
  const now = Date.now();
  const windowStart = now - windowMs;
  const userTimestamps = (rateLimitMap.get(userId) || []).filter(t => t > windowStart);
  if (userTimestamps.length >= maxRequests) {
    rateLimitMap.set(userId, userTimestamps);
    return false;
  }
  userTimestamps.push(now);
  rateLimitMap.set(userId, userTimestamps);
  return true;
}

function validateTelegramInitData(initData, botToken) {
  if (!initData || !botToken) return null;
  try {
    const urlParams = new URLSearchParams(initData);
    const hash = urlParams.get('hash');
    if (!hash) return null;
    urlParams.delete('hash');

    const dataCheckArr = [];
    for (const [key, val] of Array.from(urlParams.entries()).sort(([a], [b]) => a.localeCompare(b))) {
      dataCheckArr.push(`${key}=${val}`);
    }
    const dataCheckString = dataCheckArr.join('\n');

    const secretKey = crypto.createHmac('sha256', 'WebAppData').update(botToken).digest();
    const calculatedHash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');

    if (calculatedHash !== hash) return null;

    const userRaw = urlParams.get('user');
    if (userRaw) {
      try {
        return { user: JSON.parse(userRaw) };
      } catch (e) {}
    }
    return {};
  } catch (e) {
    return null;
  }
}

function sendTelegramMessage(botToken, chatId, text) {
  return new Promise((resolve) => {
    if (!botToken || !chatId) return resolve(false);
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

function sendTelegramPhoto(botToken, chatId, photoUrl, caption) {
  return new Promise((resolve) => {
    if (!botToken || !chatId) return resolve(false);
    if (!photoUrl || photoUrl.endsWith('.tgs')) {
      return sendTelegramMessage(botToken, chatId, caption).then(resolve);
    }
    const payload = JSON.stringify({
      chat_id: chatId,
      photo: photoUrl,
      caption: caption,
      parse_mode: 'HTML',
    });

    const options = {
      hostname: 'api.telegram.org',
      port: 443,
      path: `/bot${botToken}/sendPhoto`,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (json.ok) return resolve(true);
        } catch (e) {}
        sendTelegramMessage(botToken, chatId, caption).then(resolve);
      });
    });

    req.on('error', () => {
      sendTelegramMessage(botToken, chatId, caption).then(resolve);
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

  const botToken = (process.env.BOT_TOKEN || '').trim();
  const body = req.body || {};
  const initData = req.headers['x-telegram-init-data'] || body.initData || '';

  // 1. Auth verification
  let authUserId = null;
  let userDetails = null;
  if (botToken && initData) {
    const validated = validateTelegramInitData(initData, botToken);
    authUserId = validated?.user?.id;
    userDetails = validated?.user;
  }

  if (!authUserId && process.env.ALLOW_UNSAFE_DEV_AUTH === 'true') {
    authUserId = body.telegram_id || body.user_id;
  }

  if (!authUserId) {
    return res.status(401).json({ ok: false, error: 'Telegram orqali avtorizatsiya talab qilinadi' });
  }

  const userId = parseInt(authUserId, 10);

  // 2. Rate limiting
  if (!checkRateLimit(userId, 6, 60000)) {
    return res.status(429).json({ ok: false, error: 'Juda ko\'p so\'rov yuborildi. Iltimos, 1 daqiqadan so\'ng qayta urinib ko\'ring.' });
  }

  // 3. Extract order params
  const itemName = (body.item_name || 'NFT Gift').trim();
  const nftAddress = (body.nft_address || '').trim();
  const quoteId = (body.quote_id || '').trim();
  const category = (body.category || 'gifts').trim();
  const imageUrl = (body.image_url || '').trim();
  const days = parseInt(body.days, 10);
  const pricePerDay = parseInt(body.price_per_day, 10);
  const targetUsername = (body.target_username || '').replace(/^@/, '').trim();

  if (isNaN(days) || days < 1) {
    return res.status(400).json({ ok: false, error: 'Ijara muddati kamida 1 kun bo\'lishi shart' });
  }

  if (isNaN(pricePerDay) || pricePerDay <= 0) {
    return res.status(400).json({ ok: false, error: 'Kunlik narx noto\'g\'ri ko\'rsatilgan' });
  }

  if (!targetUsername) {
    return res.status(400).json({ ok: false, error: 'NFT ulanadigan Telegram username yoki manzilni kiriting' });
  }

  const totalPrice = days * pricePerDay;

  try {
    const db = getPool();
    const client = await db.connect();

    try {
      await client.query('BEGIN');

      const userRes = await client.query('SELECT balance, username, full_name FROM users WHERE telegram_id = $1 FOR UPDATE', [userId]);
      if (userRes.rows.length === 0) {
        await client.query('ROLLBACK');
        return res.status(404).json({ ok: false, error: 'Foydalanuvchi hisobi topilmadi' });
      }

      const currentBalance = Number(userRes.rows[0].balance || 0);
      const userUsername = userRes.rows[0].username || userDetails?.username || '';
      const userFullName = userRes.rows[0].full_name || userDetails?.first_name || '';

      if (currentBalance < totalPrice) {
        await client.query('ROLLBACK');
        return res.status(400).json({
          ok: false,
          error: `Balansingiz yetarli emas!\nKerak: ${totalPrice.toLocaleString('uz-UZ')} so'm\nSizda: ${currentBalance.toLocaleString('uz-UZ')} so'm`,
        });
      }

      // Deduct balance
      const newBalance = currentBalance - totalPrice;
      await client.query('UPDATE users SET balance = $1 WHERE telegram_id = $2', [newBalance, userId]);

      // Insert order
      const idempotencyKey = `RENT_${userId}_${Date.now()}_${crypto.randomBytes(3).toString('hex')}`;
      const orderRes = await client.query(
        `INSERT INTO orders (telegram_id, product_type, target_username, quantity, amount, status, external_id, created_at, idempotency_key)
         VALUES ($1, 'nft_rent', $2, $3, $4, 'pending', $5, NOW(), $6)
         RETURNING id, created_at`,
        [userId, targetUsername, days, totalPrice, nftAddress || quoteId, idempotencyKey]
      );
      const orderId = orderRes.rows[0]?.id;

      // Insert balance history
      await client.query(
        `INSERT INTO balance_history (telegram_id, amount, type, balance_before, balance_after, reason, created_at)
         VALUES ($1, $2, 'rent', $3, $4, $5, NOW())`,
        [userId, totalPrice, currentBalance, newBalance, `NFT Ijara: ${itemName} (${days} kun)`]
      );

      await client.query('COMMIT');

      // Send notifications asynchronously
      const targetStr = `@${targetUsername.replace(/^@/, '')}`;
      const channelOrders = process.env.CHANNEL_ORDERS || '@coinstatuz_org';
      const adminIds = (process.env.ADMIN_IDS || '8202423244').split(',').map(x => x.trim()).filter(Boolean);

      const userMsg =
        `🖼 <b>NFT IJARA BUYURTMASI QABUL QILINDI!</b>\n\n` +
        `🎁 <b>NFT nomi:</b> <b>${itemName}</b>\n` +
        `⏳ <b>Ijara muddati:</b> <b>${days} kun</b>\n` +
        `👤 <b>Ulanadigan profil:</b> <b>${targetStr}</b>\n` +
        `💰 <b>Kunlik narx:</b> ${pricePerDay.toLocaleString('uz-UZ')} so'm\n` +
        `💳 <b>Jami to'lov:</b> <b>${totalPrice.toLocaleString('uz-UZ')} so'm</b>\n` +
        `👛 <b>Qolgan balans:</b> ${newBalance.toLocaleString('uz-UZ')} so'm\n` +
        `🆔 <b>Buyurtma ID:</b> #${orderId}\n\n` +
        `⚡ <i>Buyurtmangiz ko'rib chiqishga olindi va tez orada admin tomonidan profilga ulanadi! Holatini «Buyurtmalar» sahifasida kuzatishingiz mumkin.</i>`;

      const adminMsg =
        `🚨 <b>YANGI NFT IJARA BUYURTMASI!</b> (#${orderId})\n\n` +
        `👤 <b>Mijoz:</b> <code>${userId}</code> ${userUsername ? '(@' + userUsername + ')' : ''} ${userFullName}\n` +
        `🎯 <b>Ulanadigan profil:</b> <b>${targetStr}</b>\n` +
        `🖼 <b>NFT:</b> <b>${itemName}</b> (${category})\n` +
        `⏳ <b>Muddat:</b> <b>${days} kun</b>\n` +
        `💰 <b>To'langan summa:</b> <b>${totalPrice.toLocaleString('uz-UZ')} so'm</b> (balansdan yechildi)\n` +
        `📬 <b>NFT Address:</b> <code>${nftAddress || 'N/A'}</code>\n` +
        `🔑 <b>Quote:</b> <code>${quoteId || 'N/A'}</code>\n\n` +
        `⚙️ <i>Iltimos, NFTni Marketapp yoki TON orqali ushbu foydalanuvchiga ulab bering!</i>`;

      const notifyPromises = [
        sendTelegramPhoto(botToken, userId, imageUrl, userMsg),
      ];

      for (const adminId of adminIds) {
        notifyPromises.push(sendTelegramPhoto(botToken, adminId, imageUrl, adminMsg));
      }

      if (channelOrders) {
        const publicCardMsg =
          `🖼 <b>CoinStat UZ — Yangi NFT Ijara!</b>\n\n` +
          `🎁 <b>NFT:</b> ${itemName}\n` +
          `👤 <b>Foydalanuvchi:</b> ${targetStr}\n` +
          `⏳ <b>Muddat:</b> ${days} kun\n` +
          `💰 <b>Summa:</b> ${totalPrice.toLocaleString('uz-UZ')} so'm\n\n` +
          `🚀 Ijara muvaffaqiyatli rasmiylashtirildi!\n` +
          `🌐 <b>Kanal:</b> @coinstatuz_org | 🤖 <b>Bot:</b> @CoinStatuz_bot`;
        notifyPromises.push(sendTelegramPhoto(botToken, channelOrders, imageUrl, publicCardMsg));
      }

      Promise.allSettled(notifyPromises).catch(() => {});

      return res.status(200).json({
        ok: true,
        order_id: orderId,
        balance: newBalance,
        total_price: totalPrice,
        message: 'NFT ijara buyurtmangiz muvaffaqiyatli qabul qilindi!',
      });
    } catch (txErr) {
      await client.query('ROLLBACK');
      throw txErr;
    } finally {
      client.release();
    }
  } catch (err) {
    console.error('Rent order error:', err);
    return res.status(500).json({ ok: false, error: err.message || 'Serverda xatolik yuz berdi' });
  }
};
