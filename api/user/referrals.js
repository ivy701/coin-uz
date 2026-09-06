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
