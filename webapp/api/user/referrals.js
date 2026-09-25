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
      idleTimeoutMillis: 30000,
    });
  }
  return pool;
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

function parseUserId(req) {
  const botToken = (process.env.BOT_TOKEN || '').trim();
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch(e) {}
  }

  const initData = (req.headers ? (req.headers['x-telegram-init-data'] || req.headers['X-Telegram-Init-Data']) : null)
    || (body && body.initData)
    || (req.query && req.query.initData);

  if (botToken && initData) {
    const validated = validateTelegramInitData(initData, botToken);
    if (validated && validated.user && validated.user.id) {
      return parseInt(validated.user.id, 10);
    }
  }

  if (process.env.ALLOW_UNSAFE_DEV_AUTH === 'true') {
    let uid = null;
    if (req.query) uid = req.query.telegram_id || req.query.user_id || req.query.id;
    if (!uid && body) uid = body.telegram_id || body.user_id || body.id;
    if (uid) return parseInt(uid, 10);
  }

  return null;
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const userId = parseUserId(req);
  if (!userId || isNaN(userId)) {
    return res.status(400).json({ ok: false, error: 'telegram_id is required' });
  }

  try {
    const db = getPool();
    const userRes = await db.query('SELECT referrals FROM users WHERE telegram_id = $1', [userId]);
    const referralsCount = userRes.rows.length > 0 ? Number(userRes.rows[0].referrals || 0) : 0;

    const referredRes = await db.query(
      'SELECT telegram_id, username, full_name, created_at FROM users WHERE referred_by = $1 ORDER BY created_at DESC LIMIT 50',
      [userId]
    );

    return res.status(200).json({
      ok: true,
      referrals_count: referralsCount,
      bonus_per_referral: 300,
      total_bonus: referralsCount * 300,
      referred: referredRes.rows,
    });
  } catch (err) {
    console.error('Referrals query error:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
