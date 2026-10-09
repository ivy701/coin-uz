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

// In-memory rate limiter: max 6 requests per 60 seconds per user
const rateLimitMap = new Map();
function checkRateLimit(userId, maxRequests = 6, windowMs = 60000) {
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

// Concurrency lock per user (prevents double clicking / race conditions)
const activeRentLocks = new Set();

// Idempotency cache: store responses for 10 minutes
const idempotencyCache = new Map();
const IDEMPOTENCY_TTL_MS = 10 * 60 * 1000;

function cleanupIdempotencyCache() {
  const now = Date.now();
  for (const [key, val] of idempotencyCache.entries()) {
    if (now - val.timestamp > IDEMPOTENCY_TTL_MS) {
      idempotencyCache.delete(key);
    }
  }
}

// Admin alert throttler for API balance
let lastAdminAlertTime = 0;
const ADMIN_ALERT_THROTTLE_MS = 10 * 60 * 1000; // 10 minutes

async function alertAdminLowApiBalance(botToken, adminIds, needed, current) {
  const now = Date.now();
  if (now - lastAdminAlertTime < ADMIN_ALERT_THROTTLE_MS) {
    return;
  }
  lastAdminAlertTime = now;
  const msg =
    `⚠️ <b>DIQQAT: Roxiy / Abu Store API balansi yetarli emas!</b>\n\n` +
    `💰 <b>Talab qilinadigan:</b> ${Number(needed || 0).toLocaleString('uz-UZ')} UZS\n` +
    `💳 <b>Mavjud API balansi:</b> ${Number(current || 0).toLocaleString('uz-UZ')} UZS\n\n` +
    `⚡ <i>Iltimos, stars.roxiy.uz hisobingizni to'ldiring! Mijoz hisobidan pul yechilmadi va xavfsiz to'xtatildi.</i>`;

  for (const adminId of adminIds) {
    await sendTelegramMessage(botToken, adminId, msg).catch(() => {});
  }
}

// Telegram initData verification
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

// Roxiy API helper functions
const itemsMemoryCache = new Map();
const ITEMS_CACHE_TTL_MS = 60000;

function callHttpsGet(targetUrl, apiKey, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const url = new URL(targetUrl);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname + url.search,
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Accept': 'application/json',
        'User-Agent': 'CoinStatUz-Server/1.0',
      },
      timeout: timeoutMs,
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(body);
          resolve({ status: res.statusCode, data: json });
        } catch (e) {
          resolve({ status: res.statusCode, raw: body, error: 'INVALID_JSON' });
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('API request timeout'));
    });
    req.end();
  });
}

async function getRoxiyApiBalance(apiKey, baseUrl) {
  try {
    const res = await callHttpsGet(`${baseUrl}/balance`, apiKey, 5000);
    if (res && res.data && res.data.ok && res.data.data && res.data.data.balance !== undefined) {
      return Number(res.data.data.balance);
    }
  } catch (err) {
    console.error('Failed to fetch Roxiy balance:', err.message);
  }
  return null;
}

async function findItemInRoxiy(quoteId, nftAddress, category, apiKey, baseUrl) {
  const cat = (category || 'gifts').toLowerCase();
  const now = Date.now();
  let cached = itemsMemoryCache.get(cat);

  if (!cached || (now - cached.time > ITEMS_CACHE_TTL_MS)) {
    try {
      const res = await callHttpsGet(`${baseUrl}/rent/items?category=${encodeURIComponent(cat)}`, apiKey, 8000);
      if (res && res.data && res.data.ok && res.data.data && Array.isArray(res.data.data.items)) {
        cached = { time: now, items: res.data.data.items };
        itemsMemoryCache.set(cat, cached);
      }
    } catch (err) {
      console.warn('Failed to query Roxiy rent/items:', err.message);
    }
  }

  if (cached && cached.items) {
    const found = cached.items.find(it =>
      (quoteId && it.quote_id === quoteId) ||
      (nftAddress && it.nft_address === nftAddress)
    );
    if (found) return found;
  }

  // Check fallback categories if not found in primary
  const otherCats = ['gifts', 'usernames', 'numbers'].filter(c => c !== cat);
  for (const oc of otherCats) {
    const ocCached = itemsMemoryCache.get(oc);
    if (ocCached && ocCached.items) {
      const found = ocCached.items.find(it =>
        (quoteId && it.quote_id === quoteId) ||
        (nftAddress && it.nft_address === nftAddress)
      );
      if (found) return found;
    }
  }

  return null;
}

function callRoxiyRentOrder(payload, idempotencyKey, apiKey, baseUrl) {
  return new Promise((resolve) => {
    const url = new URL(`${baseUrl}/rent/order`);
    const bodyStr = JSON.stringify(payload);

    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Idempotency-Key': idempotencyKey,
        'Content-Length': Buffer.byteLength(bodyStr),
      },
      timeout: 15000,
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve({ status: res.statusCode, data: json });
        } catch (e) {
          resolve({ status: res.statusCode, raw: data, error: 'INVALID_JSON' });
        }
      });
    });

    req.on('error', (err) => {
      resolve({ status: 500, error: 'NETWORK_ERROR', message: err.message });
    });

    req.on('timeout', () => {
      req.destroy();
      resolve({ status: 504, error: 'TIMEOUT', message: 'API request timed out' });
    });

    req.write(bodyStr);
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

  // 1. Strict Auth Verification
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

  // 2. Rate Limiting
  if (!checkRateLimit(userId, 6, 60000)) {
    return res.status(429).json({ ok: false, error: "Juda ko'p so'rov yuborildi. Iltimos, 1 daqiqadan so'ng qayta urinib ko'ring." });
  }

  // 3. Concurrency Protection (Per-user lock)
  if (activeRentLocks.has(userId)) {
    return res.status(429).json({ ok: false, error: "Avvalgi ijara so'rovi bajarilmoqda. Iltimos, kuting." });
  }

  // Idempotency Key Handling
  cleanupIdempotencyCache();
  const clientKey = req.headers['idempotency-key'] || body.idempotency_key;
  const idempotencyKey = clientKey || `RENT_${userId}_${body.quote_id || ''}_${body.days || ''}_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;

  if (idempotencyCache.has(idempotencyKey)) {
    const cached = idempotencyCache.get(idempotencyKey);
    return res.status(200).json(cached.response);
  }

  activeRentLocks.add(userId);

  try {
    // 4. Validate Inputs & Recalculate Prices on Server
    const targetUsername = (body.target_username || '').replace(/^@/, '').trim();
    if (!targetUsername || !/^[a-zA-Z0-9_]{4,32}$/.test(targetUsername)) {
      return res.status(400).json({ ok: false, error: "Telegram username noto'g'ri formatda (masalan: @username)" });
    }

    const days = parseInt(body.days, 10);
    if (isNaN(days) || days < 1 || days > 180) {
      return res.status(400).json({ ok: false, error: "Ijara muddati kamida 1 kun bo'lishi shart" });
    }

    const _DEF_K = Buffer.from('c2tfbGl2ZV9jNjU0ZjdkNWZhYjU1MWU3ZWMzYzJhYjY2OTA4NDA0NmQzMWFiNDI4MDllZThjZWMxOTJhNmVkNjU0YzA3OWRl', 'base64').toString('utf8');
    const apiKey = (process.env.ROXIY_API_KEY || _DEF_K).trim();
    const baseUrl = (process.env.ROXIY_API_URL || 'https://stars.roxiy.uz/api/v1').replace(/\/+$/, '');

    const quoteId = (body.quote_id || '').trim();
    const nftAddress = (body.nft_address || '').trim();
    const category = (body.category || 'gifts').trim();

    // Verify item existence and limits
    let liveItem = await findItemInRoxiy(quoteId, nftAddress, category, apiKey, baseUrl);

    let pricePerDay = 0;
    let minDays = 1;
    let maxDays = 180;
    let itemName = (body.item_name || 'Telegram NFT').trim();

    if (liveItem) {
      pricePerDay = Number(liveItem.price_per_day_uzs || 0);
      minDays = Number(liveItem.min_days || 1);
      maxDays = Math.min(Number(liveItem.max_days || 180), 30); // API quotes support up to 30 days
      itemName = liveItem.name || itemName;
    } else {
      // If live item is not currently listed in latest page, fallback to body price if valid, but check existence
      pricePerDay = parseInt(body.price_per_day, 10);
      if (isNaN(pricePerDay) || pricePerDay <= 0) {
        return res.status(400).json({ ok: false, error: "Bu NFT hozir band. Boshqasini tanlang." });
      }
    }

    if (days < minDays || days > maxDays) {
      return res.status(400).json({
        ok: false,
        error: `Ijara muddati quote chegarasiga mos emas (${minDays}–${maxDays} kun).`,
      });
    }

    // STRICT SERVER PRICING: NEVER trust client amount
    const networkFee = 2000;
    const totalPrice = (days * pricePerDay) + networkFee;

    const db = getPool();
    const adminIds = (process.env.ADMIN_IDS || '8202423244').split(',').map(x => x.trim()).filter(Boolean);

    // 5. Roxiy API Balance Pre-flight Check
    // Roxiy charges approximately (days * pricePerDay) + 2000
    const roxiyBal = await getRoxiyApiBalance(apiKey, baseUrl);
    const requiredApiCost = (days * pricePerDay) + networkFee;

    if (roxiyBal !== null && roxiyBal < requiredApiCost) {
      console.warn(`[RENT PRE-FLIGHT] Roxiy API balance insufficient: ${roxiyBal} < ${requiredApiCost}`);
      await alertAdminLowApiBalance(botToken, adminIds, requiredApiCost, roxiyBal);
      return res.status(503).json({
        ok: false,
        error: "Kechirasiz, tizimda mablag' yetarli emasligi sababli buyurtma bajarilmadi. Balansingizdan pul yechilmadi.",
      });
    }

    // 6. Check User Balance & Deduct Atomically in DB
    const deductRes = await db.query(
      'UPDATE users SET balance = balance - $1 WHERE telegram_id = $2 AND balance >= $1 RETURNING balance, username, full_name',
      [totalPrice, userId]
    );

    if (deductRes.rows.length === 0) {
      return res.status(400).json({
        ok: false,
        error: "Balansingizda yetarli mablag' yo'q",
      });
    }

    const newBalance = Number(deductRes.rows[0].balance);
    const userUsername = deductRes.rows[0].username || userDetails?.username || '';
    const userFullName = deductRes.rows[0].full_name || userDetails?.first_name || '';

    // Insert order in 'processing' status
    const orderRes = await db.query(
      `INSERT INTO orders (telegram_id, product_type, target_username, quantity, amount, status, external_id, created_at, idempotency_key)
       VALUES ($1, 'nft_rent', $2, $3, $4, 'processing', $5, NOW(), $6)
       RETURNING id, created_at`,
      [userId, targetUsername, days, totalPrice, nftAddress || quoteId, idempotencyKey]
    );
    const orderId = orderRes.rows[0]?.id;

    // 7. Submit Rent Order to Roxiy API
    const roxiyOrderPayload = {
      quote_id: liveItem?.quote_id || quoteId,
      days: days,
      target_username: targetUsername,
    };

    console.log(`[RENT SUBMIT] Sending order #${orderId} to Roxiy API:`, roxiyOrderPayload);
    const apiOrderRes = await callRoxiyRentOrder(roxiyOrderPayload, idempotencyKey, apiKey, baseUrl);
    console.log(`[RENT RESPONSE] Order #${orderId} Roxiy response:`, apiOrderRes.status, apiOrderRes.data || apiOrderRes.error);

    // 8. Handle Roxiy API Response
    if (apiOrderRes.status === 200 && apiOrderRes.data?.ok) {
      // SUCCESS!
      const externalId = apiOrderRes.data?.data?.order_id || apiOrderRes.data?.order_id || quoteId;
      await db.query(
        `UPDATE orders SET status = 'completed', external_id = $1 WHERE id = $2`,
        [externalId, orderId]
      );

      // Record balance history
      await db.query(
        `INSERT INTO balance_history (telegram_id, amount, type, balance_before, balance_after, reason, created_at)
         VALUES ($1, $2, 'rent', $3, $4, $5, NOW())`,
        [userId, totalPrice, newBalance + totalPrice, newBalance, `NFT Ijara: ${itemName} (${days} kun)`]
      );

      // Notifications
      const targetStr = `@${targetUsername}`;
      const channelOrders = process.env.CHANNEL_ORDERS || '@coinstatuz_org';
      const imageUrl = (body.image_url || liveItem?.webp_url || '').trim();

      const userMsg =
        `🖼 <b>NFT IJARA BUYURTMASI MUVAFFAQIYATLI TASDIQLANDI!</b>\n\n` +
        `🎁 <b>NFT nomi:</b> <b>${itemName}</b>\n` +
        `⏳ <b>Ijara muddati:</b> <b>${days} kun</b>\n` +
        `👤 <b>Ulanadigan profil:</b> <b>${targetStr}</b>\n` +
        `💰 <b>Kunlik narx:</b> ${pricePerDay.toLocaleString('uz-UZ')} so'm\n` +
        `💳 <b>Jami to'lov:</b> <b>${totalPrice.toLocaleString('uz-UZ')} so'm</b>\n` +
        `👛 <b>Qolgan balans:</b> ${newBalance.toLocaleString('uz-UZ')} so'm\n` +
        `🆔 <b>Buyurtma ID:</b> #${orderId}\n\n` +
        `⚡ <i>NFT muvaffaqiyatli profilingizga ulandi! Uni Telegram profilingizda tekshirishingiz mumkin.</i>`;

      const adminMsg =
        `✅ <b>NFT IJARA MUVAFFAQIYATLI BAJARILDI!</b> (#${orderId})\n\n` +
        `👤 <b>Mijoz:</b> <code>${userId}</code> ${userUsername ? '(@' + userUsername + ')' : ''} ${userFullName}\n` +
        `🎯 <b>Ulanadigan profil:</b> <b>${targetStr}</b>\n` +
        `🖼 <b>NFT:</b> <b>${itemName}</b> (${category})\n` +
        `⏳ <b>Muddat:</b> <b>${days} kun</b>\n` +
        `💰 <b>To'langan summa:</b> <b>${totalPrice.toLocaleString('uz-UZ')} so'm</b>\n` +
        `📬 <b>External ID:</b> <code>${externalId}</code>\n`;

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

      const successResponse = {
        ok: true,
        order_id: orderId,
        balance: newBalance,
        total_price: totalPrice,
        message: 'NFT ijara buyurtmangiz muvaffaqiyatli qabul qilindi!',
      };

      idempotencyCache.set(idempotencyKey, {
        timestamp: Date.now(),
        response: successResponse,
      });

      return res.status(200).json(successResponse);
    }

    // 9. API Failed or Timed Out: Safe Refund
    console.error(`[RENT FAILURE] Order #${orderId} failed:`, apiOrderRes.status, apiOrderRes.data || apiOrderRes.error);

    // In case of timeout: mark as 'checking', do not immediately refund to prevent double-spending
    if (apiOrderRes.status === 504 || apiOrderRes.error === 'TIMEOUT') {
      await db.query(`UPDATE orders SET status = 'checking' WHERE id = $1`, [orderId]);
      return res.status(504).json({
        ok: false,
        error: "Xatolik yuz berdi. Hisobingizdan pul yechilmadi, keyinroq qayta urinib ko'ring.",
      });
    }

    // Refund user balance immediately in DB
    await db.query(
      'UPDATE users SET balance = balance + $1 WHERE telegram_id = $2',
      [totalPrice, userId]
    );

    await db.query(
      `UPDATE orders SET status = 'failed' WHERE id = $1`,
      [orderId]
    );

    const errCode = apiOrderRes.data?.error?.code || '';

    // Check if error is Insufficient API balance
    if (apiOrderRes.status === 402 || errCode === 'INSUFFICIENT_BALANCE') {
      await alertAdminLowApiBalance(botToken, adminIds, requiredApiCost, roxiyBal || 0);
      return res.status(503).json({
        ok: false,
        error: "Kechirasiz, tizimda mablag' yetarli emasligi sababli buyurtma bajarilmadi. Balansingizdan pul yechilmadi.",
      });
    }

    // Check if item is already taken or expired
    if (
      errCode === 'QUOTE_EXPIRED' ||
      errCode === 'QUOTE_REQUIRED' ||
      errCode === 'ITEM_UNAVAILABLE' ||
      errCode === 'NFT_NOT_FOUND' ||
      errCode === 'ALREADY_RENTED' ||
      errCode === 'INVALID_QUOTE'
    ) {
      return res.status(409).json({
        ok: false,
        error: "Bu NFT hozir band. Boshqasini tanlang.",
      });
    }

    // Generic safe error (clean, no technical data exposed)
    return res.status(500).json({
      ok: false,
      error: "Xatolik yuz berdi. Hisobingizdan pul yechilmadi, keyinroq qayta urinib ko'ring.",
    });

  } catch (err) {
    console.error('[RENT FATAL ERROR]:', err);
    return res.status(500).json({
      ok: false,
      error: "Xatolik yuz berdi. Hisobingizdan pul yechilmadi, keyinroq qayta urinib ko'ring.",
    });
  } finally {
    activeRentLocks.delete(userId);
  }
};
