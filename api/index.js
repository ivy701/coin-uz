const { Pool } = require('pg');

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

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  let userId = req.query?.telegram_id || req.query?.user_id;
  if (!userId && req.body) {
    userId = req.body.telegram_id || req.body.user_id;
  }

  if (userId) {
    try {
      const db = getPool();
      const result = await db.query('SELECT balance, referrals, language FROM users WHERE telegram_id = $1', [parseInt(userId, 10)]);
      if (result.rows.length > 0) {
        return res.status(200).json({
          ok: true,
          balance: Number(result.rows[0].balance || 0),
          referrals: Number(result.rows[0].referrals || 0),
        });
      }
      return res.status(200).json({ ok: true, balance: 0, referrals: 0 });
    } catch (e) {
      return res.status(500).json({ ok: false, error: e.message });
    }
  }

  return res.status(200).json({ ok: true, message: "StarPay WebApp API is running" });
};
