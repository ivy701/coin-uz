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

  try {
    let body = req.body || {};
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch (e) {}
    }
    const userId = req.query?.telegram_id || req.query?.user_id || body.telegram_id || body.user_id;
    if (!userId) {
      return res.status(200).json({ ok: false, error: 'User ID missing' });
    }

    const db = getPool();

    // Check user bonus spins (Promokod orqali berilgan)
    const bonusRes = await db.query('SELECT spins_left, forced_prize FROM user_bonus_spins WHERE telegram_id = $1', [parseInt(userId, 10)]);
    const bonusSpins = bonusRes.rows.length > 0 ? (bonusRes.rows[0].spins_left || 0) : 0;
    const forcedPrize = bonusRes.rows.length > 0 ? (bonusRes.rows[0].forced_prize || 'bear') : 'bear';

    if (bonusSpins > 0) {
      return res.status(200).json({
        ok: true,
        can_spin: true,
        bonus_spins: bonusSpins,
        forced_prize: forcedPrize,
        message: `Sizda ${bonusSpins} ta bepul aylantirish mavjud!`
      });
    }

    return res.status(200).json({
      ok: true,
      can_spin: false,
      bonus_spins: 0,
      message: 'Omad g\'ildiragi faqat Promo Kod orqali ochiladi!'
    });

  } catch (err) {
    console.error('Error in spin status:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
