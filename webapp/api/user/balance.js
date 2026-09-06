const { Pool } = require('pg');

let pool;
function getPool() {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL || 'postgresql://neondb_owner:npg_gbusDUvG1z8M@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require';
    pool = new Pool({
      connectionString,
      ssl: { rejectUnauthorized: false },
      max: 5,
      idleTimeoutMillis: 30000,
    });
  }
  return pool;
}

function parseUserId(req) {
  let uid = null;
  if (req.query) {
    uid = req.query.telegram_id || req.query.user_id || req.query.id;
  }
  if (!uid && req.body) {
    uid = req.body.telegram_id || req.body.user_id || req.body.id;
    if (!uid && req.body.initData) {
      try {
        const params = new URLSearchParams(req.body.initData);
        const userStr = params.get('user');
        if (userStr) {
          const u = JSON.parse(userStr);
          uid = u.id;
        }
      } catch (e) {}
    }
  }
  const initHeader = req.headers['x-telegram-init-data'];
  if (!uid && initHeader) {
    try {
      const params = new URLSearchParams(initHeader);
      const userStr = params.get('user');
      if (userStr) {
        const u = JSON.parse(userStr);
        uid = u.id;
      }
    } catch (e) {}
  }
  return uid ? parseInt(uid, 10) : null;
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
    console.error('Database query error:', err);
    return res.status(500).json({ ok: false, error: err.message, balance: 0 });
  }
};
