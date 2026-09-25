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
    if (req.query) uid = req.query.telegram_id || req.query.user_id || req.query.id || req.query.uid;
    if (!uid && body) uid = body.telegram_id || body.user_id || body.id || body.uid;
    if (uid) return parseInt(uid, 10);
  }

  return null;
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const userId = parseUserId(req);
  if (!userId || isNaN(userId)) {
    return res.status(200).json({ ok: true, balance: 0, referrals: 0, language: 'uz' });
  }

  try {
    const db = getPool();
    const result = await db.query('SELECT balance, referrals, language FROM users WHERE telegram_id = $1', [userId]);

    if (result.rows.length > 0) {
      const user = result.rows[0];
      return res.status(200).json({
        ok: true,
        balance: Number(user.balance || 0),
        referrals: Number(user.referrals || 0),
        language: user.language || 'uz',
      });
    }

    // Auto-create user if not found
    await db.query(
      'INSERT INTO users (telegram_id, balance, referrals, language) VALUES ($1, 0, 0, $2) ON CONFLICT (telegram_id) DO NOTHING',
      [userId, 'uz']
    );

    return res.status(200).json({
      ok: true,
      balance: 0,
      referrals: 0,
      language: 'uz',
    });
  } catch (err) {
    console.error('Database balance query error:', err);
    return res.status(200).json({ ok: true, balance: 0, referrals: 0, language: 'uz' });
  }
};
