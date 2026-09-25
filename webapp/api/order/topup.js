const { Pool } = require('pg');
const https = require('https');

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

const crypto = require('crypto');

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

function checkTelegramMembership(botToken, channel, userId) {
  return new Promise((resolve) => {
    const cleanChannel = channel.startsWith('@') ? channel : `@${channel}`;
    const url = `https://api.telegram.org/bot${botToken}/getChatMember?chat_id=${encodeURIComponent(cleanChannel)}&user_id=${encodeURIComponent(userId)}`;

    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (json.ok && json.result) {
            const status = json.result.status;
            const isMember = ['creator', 'administrator', 'member'].includes(status) || 
                             (status === 'restricted' && Boolean(json.result.is_member));
            return resolve(Boolean(isMember));
          }
          resolve(false);
        } catch (e) {
          resolve(false);
        }
      });
    }).on('error', () => resolve(true));
  });
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const botToken = process.env.BOT_TOKEN;
  if (!botToken) {
    console.error('BOT_TOKEN environment variable is not defined');
    return res.status(500).json({ ok: false, error: 'Server sozlamalari to\'liq emas (BOT_TOKEN yo\'q)' });
  }

  const body = req.body || {};
  const initData = req.headers['x-telegram-init-data'] || body.initData || '';
  
  // 1. Validate initData HMAC signature
  const validated = validateTelegramInitData(initData, botToken);
  let authUserId = validated?.user?.id;

  if (!authUserId) {
    if (process.env.ALLOW_UNSAFE_DEV_AUTH === 'true') {
      authUserId = body.telegram_id || body.user_id;
    }
  }

  if (!authUserId) {
    return res.status(401).json({ ok: false, error: 'Telegram initData yaroqsiz yoki muddati o\'tgan (Unauthorized)' });
  }

  // 2. Channel Subscription Check
  const channel = (process.env.REQUIRED_CHANNEL || '@CoinStatUz').trim();
  const isSub = await checkTelegramMembership(botToken, channel, authUserId);
  if (!isSub) {
    return res.status(403).json({
      ok: false,
      error: `Xizmatdan foydalanish uchun avval ${channel} kanaliga a'zo bo'ling!`,
      requires_subscription: true,
      channel: channel,
      channel_url: `https://t.me/${channel.replace(/^@/, '')}`
    });
  }

  // 4. User ID mismatch verification
  const claimedId = body.telegram_id || body.user_id;
  if (claimedId && parseInt(claimedId, 10) !== parseInt(authUserId, 10)) {
    return res.status(403).json({ ok: false, error: 'Foydalanuvchi identifikatori mos kelmadi (Forbidden)' });
  }

  // 3. Rate limiting (max 5 req/min)
  if (!checkRateLimit(authUserId, 5, 60000)) {
    return res.status(429).json({ ok: false, error: 'Juda ko\'p so\'rov yuborildi. Iltimos, 1 daqiqadan so\'ng qayta urinib ko\'ring.' });
  }

  const amount = parseInt(body.amount, 10);
  const paymentMethod = body.payment_method || 'card';

  // 6. Topup Limit Validation: 1,000 UZS <= amount <= 10,000,000 UZS
  const MIN_TOPUP = parseInt(process.env.MIN_TOPUP_AMOUNT, 10) || 1000;
  const MAX_TOPUP = parseInt(process.env.MAX_TOPUP_AMOUNT, 10) || 10000000;

  if (isNaN(amount) || amount < MIN_TOPUP || amount > MAX_TOPUP) {
    return res.status(400).json({
      ok: false,
      error: `To'lov summasi ${MIN_TOPUP.toLocaleString('uz-UZ')} va ${MAX_TOPUP.toLocaleString('uz-UZ')} so'm oralig'ida bo'lishi kerak.`
    });
  }

  const orderId = 'TOP_' + Date.now();
  const adminId = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID, 10) : 8202423244;

  try {
    const db = getPool();
    const tgUser = validated?.user || {};
    const username = (body.username || (tgUser.username ? `@${tgUser.username.replace('@', '')}` : '') || '').trim();
    const fullName = (body.name || body.first_name || [tgUser.first_name, tgUser.last_name].filter(Boolean).join(' ') || '').trim();

    let userDisplay = `<code>${authUserId}</code>`;
    if (username && fullName) {
      userDisplay = `<b>${fullName}</b> (${username}) | <code>${authUserId}</code>`;
    } else if (username) {
      userDisplay = `${username} | <code>${authUserId}</code>`;
    } else if (fullName) {
      userDisplay = `<b>${fullName}</b> | <code>${authUserId}</code>`;
    }

    // Save/update user profile info in database
    if (username || fullName) {
      await db.query(
        `INSERT INTO users (telegram_id, username, full_name, created_at)
         VALUES ($1, $2, $3, NOW())
         ON CONFLICT (telegram_id) DO UPDATE 
         SET username = COALESCE(NULLIF(EXCLUDED.username, ''), users.username),
             full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), users.full_name)`,
        [authUserId, username.replace('@', ''), fullName]
      ).catch(() => {});
    }

    const adminText = 
      `💳 <b>YANGI BALANS TO'LDIRISH SO'ROVI!</b>\n\n` +
      `👤 <b>Foydalanuvchi:</b> ${userDisplay}\n` +
      `💰 <b>Summa:</b> <b>${amount.toLocaleString('uz-UZ')} so'm</b>\n` +
      `📌 <b>To'lov usuli:</b> <b>${paymentMethod.toUpperCase()}</b>\n` +
      `🆔 <b>Buyurtma ID:</b> <code>${orderId}</code>\n\n` +
      `<i>Foydalanuvchi kartaga pul o'tkazganini tasdiqlagan bo'lsa, quyidagi tugma orqali tasdiqlang:</i>`;

    const keyboard = [
      [
        { text: '✅ Tasdiqlash (+ pul qo\'shish)', callback_data: `approve_topup_${orderId}_${authUserId}_${amount}` },
      ],
      [
        { text: '❌ Bekor qilish (Rad etish)', callback_data: `reject_topup_${orderId}_${authUserId}` },
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
    return res.status(500).json({ ok: false, error: 'Server xatoligi yuz berdi' });
  }
};
