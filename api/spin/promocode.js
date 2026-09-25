const { Pool } = require('pg');
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

// In-memory rate limiter: max 5 promo code attempts per 60 seconds per user
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

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'Method not allowed' });
  }

  try {
    const botToken = (process.env.BOT_TOKEN || '').trim();
    let body = req.body || {};
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body);
      } catch (e) {}
    }

    const initData = req.headers['x-telegram-init-data'] || body.initData || '';
    let authUserId = null;
    if (botToken && initData) {
      const validated = validateTelegramInitData(initData, botToken);
      authUserId = validated?.user?.id;
    }

    if (!authUserId && process.env.ALLOW_UNSAFE_DEV_AUTH === 'true') {
      authUserId = body.telegram_id || body.user_id;
    }

    if (!authUserId) {
      return res.status(401).json({ ok: false, error: 'Telegram initData yaroqsiz yoki muddati o\'tgan (Unauthorized)' });
    }

    const claimedId = body.telegram_id || body.user_id;
    if (claimedId && parseInt(claimedId, 10) !== parseInt(authUserId, 10)) {
      return res.status(403).json({ ok: false, error: 'Foydalanuvchi identifikatori mos kelmadi (Forbidden)' });
    }

    const userId = parseInt(authUserId, 10);

    // Rate limiting to block brute force attacks
    if (!checkRateLimit(userId, 5, 60000)) {
      return res.status(429).json({ ok: false, error: 'Juda ko\'p urinish. Iltimos, 1 daqiqadan so\'ng qayta urinib ko\'ring.' });
    }

    const code = (body.code || '').trim().toUpperCase();

    if (!userId) {
      return res.status(200).json({ ok: false, error: 'Foydalanuvchi aniqlanmadi. Iltimos qayta kiring!' });
    }
    if (!code) {
      return res.status(200).json({ ok: false, error: 'Iltimos, promo kodni kiriting!' });
    }

    const db = getPool();

    // Ensure lucky_promocodes and user_bonus_spins tables exist
    await db.query(`
      CREATE TABLE IF NOT EXISTS lucky_promocodes (
        id SERIAL PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        is_used BOOLEAN NOT NULL DEFAULT FALSE,
        used_by_id BIGINT,
        used_by_username TEXT,
        used_by_name TEXT,
        used_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);

    await db.query(`
      CREATE TABLE IF NOT EXISTS user_bonus_spins (
        telegram_id BIGINT PRIMARY KEY,
        spins_left INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);

    // 1. 2-soatlik cheklov (G'olib bo'lgan foydalanuvchi 2 soat ichida yana promo-kod ishlata olmaydi)
    const lastUsedRes = await db.query(`
      SELECT used_at FROM lucky_promocodes 
      WHERE used_by_id = $1 AND is_used = TRUE AND used_at IS NOT NULL 
      ORDER BY used_at DESC LIMIT 1
    `, [parseInt(userId, 10)]);

    if (lastUsedRes.rows.length > 0 && lastUsedRes.rows[0].used_at) {
      const lastUsedAt = new Date(lastUsedRes.rows[0].used_at).getTime();
      const now = Date.now();
      const diffMs = now - lastUsedAt;
      const twoHoursMs = 2 * 60 * 60 * 1000;
      if (diffMs < twoHoursMs) {
        const remMs = twoHoursMs - diffMs;
        const remHours = Math.floor(remMs / (60 * 60 * 1000));
        const remMins = Math.floor((remMs % (60 * 60 * 1000)) / (60 * 1000));
        const timeMsg = remHours > 0 ? `${remHours} soat ${remMins} daqiqadan` : `${remMins} daqiqadan`;
        return res.status(200).json({
          ok: false,
          error: `⏳ Siz so'nggi 2 soat ichida allaqachon promo-kod orqali g'olib bo'lgansiz! Yangi promo-kodni ${timeMsg} so'ng ishlatishingiz mumkin.`
        });
      }
    }

    // 2. Check if code exists
    let promoRes = await db.query('SELECT * FROM lucky_promocodes WHERE UPPER(code) = UPPER($1)', [code]);
    
    // Auto-seed default promo codes
    const defaultCodes = [
      'CS-7711', 'CS-781', 'BEAR-99', 'TEDDY2026', 'BEAR777',
      'CS-8822', 'CS-892', 'GOLD-77', 'VINO2026',
      'CS-3399', 'CS-345', 'RUBY-44', 'ROSE2026',
      'CS-9900', 'CS-911', 'DIAMOND-7', 'PREMIUM2026',
      'CS-5544', 'CS-567', 'TURBO-88', 'ROCKET2026',
      'CS-1122', 'CS-123', 'MEGA-50', 'STARS2026',
      'CS-4433', 'CS-456', 'CASH-20', 'MONEY2026',
      'CS-2026', 'WIN-777', 'SPIN777', 'LUCKY-VIP', 'LUCKY2026',
      'COINSTATVIP', 'GIFT2026', 'VIP2026', 'TOP1', 'TOP2', 'TOP3'
    ];
    if (promoRes.rows.length === 0 && defaultCodes.includes(code)) {
      await db.query('INSERT INTO lucky_promocodes (code) VALUES ($1) ON CONFLICT DO NOTHING', [code]);
      promoRes = await db.query('SELECT * FROM lucky_promocodes WHERE UPPER(code) = UPPER($1)', [code]);
    }

    if (promoRes.rows.length === 0) {
      return res.status(200).json({ ok: false, error: `❌ '${code}' nomli promo-kod topilmadi yoki muddati tugagan!` });
    }

    const promo = promoRes.rows[0];

    // 3. Single-use check (Bitta odam ishlatdi - boshqa hech kim ishlata olmaydi)
    if (promo.is_used) {
      let who = promo.used_by_username ? `@${String(promo.used_by_username).replace('@','')}` : (promo.used_by_name || (promo.used_by_id ? `ID:${promo.used_by_id}` : 'boshqa foydalanuvchi'));
      return res.status(200).json({
        ok: false,
        already_used: true,
        used_by: who,
        error: `❌ Ushbu promo-kod allaqachon ${who} tomonidan ishlatilgan!`
      });
    }

    // Get user info if available
    let uname = (req.body?.username || '').replace('@', '').trim();
    let fname = (req.body?.full_name || '').trim();
    if (!uname && !fname) {
      const userRes = await db.query('SELECT username, full_name FROM users WHERE telegram_id = $1', [parseInt(userId, 10)]);
      if (userRes.rows.length > 0) {
        uname = userRes.rows[0].username || '';
        fname = userRes.rows[0].full_name || '';
      }
    }

    // Mark as used atomically
    const updateRes = await db.query(`
      UPDATE lucky_promocodes 
      SET is_used = TRUE, used_by_id = $1, used_by_username = $2, used_by_name = $3, used_at = NOW() 
      WHERE UPPER(code) = UPPER($4) AND is_used = FALSE
      RETURNING id
    `, [parseInt(userId, 10), uname, fname, code]);

    if (updateRes.rows.length === 0) {
      return res.status(200).json({
        ok: false,
        error: '❌ Ushbu promo-kod boshqa foydalanuvchi tomonidan hozirgina ishlatildi!'
      });
    }

    // Add +1 bonus spin with server-enforced forced_prize
    const prizeToGrant = promo.prize_type || 'bear';
    try {
      await db.query(`ALTER TABLE user_bonus_spins ADD COLUMN IF NOT EXISTS forced_prize TEXT;`);
    } catch (e) {}

    await db.query(`
      INSERT INTO user_bonus_spins (telegram_id, spins_left, forced_prize, updated_at)
      VALUES ($1, 1, $2, NOW())
      ON CONFLICT (telegram_id)
      DO UPDATE SET spins_left = user_bonus_spins.spins_left + 1, forced_prize = $2, updated_at = NOW();
    `, [parseInt(userId, 10), prizeToGrant]);

    return res.status(200).json({
      ok: true,
      forced_prize: promo.prize_type || 'bear',
      message: 'Promo kod muvaffaqiyatli faollashtirildi! Sizga +1 ta bepul aylantirish berildi 🎉'
    });

  } catch (err) {
    console.error('Error in promocode endpoint:', err);
    return res.status(500).json({ ok: false, error: 'Server xatoligi: ' + err.message });
  }
};
