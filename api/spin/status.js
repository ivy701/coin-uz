const { Pool } = require('pg');

let pool;
function getPool() {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL || 'postgresql://neondb_owner:npg_FOH4kIY9gEte@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require';
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

    // Check user bonus spins
    const bonusRes = await db.query('SELECT spins_left FROM user_bonus_spins WHERE telegram_id = $1', [parseInt(userId, 10)]);
    const bonusSpins = bonusRes.rows.length > 0 ? (bonusRes.rows[0].spins_left || 0) : 0;

    // Check Top 3 rank
    const topQuery = `
      SELECT o.telegram_id, SUM(o.amount) as total
      FROM orders o
      WHERE o.status IN ('completed', 'paid')
        AND o.product_type NOT LIKE 'topup%'
        AND o.product_type NOT IN ('deposit', 'balance')
      GROUP BY o.telegram_id
      HAVING SUM(o.amount) > 0
      ORDER BY total DESC
      LIMIT 3
    `;
    const topRes = await db.query(topQuery);
    const topIndex = topRes.rows.findIndex(r => String(r.telegram_id) === String(userId));
    const isTop3 = topIndex !== -1;
    const rank = isTop3 ? topIndex + 1 : null;

    if (bonusSpins > 0) {
      return res.status(200).json({
        ok: true,
        can_spin: true,
        bonus_spins: bonusSpins,
        is_top3: isTop3,
        rank: rank,
        cooldown_seconds: 0
      });
    }

    if (!isTop3) {
      return res.status(200).json({
        ok: true,
        can_spin: false,
        is_top3: false,
        bonus_spins: 0,
        rank: null,
        message: 'Omad g\'ildiragi faqat Top 3 yetakchilar uchun yoki Promo kod orqali ochiladi!'
      });
    }

    // Check last spin cooldown for top 3
    const lastSpinRes = await db.query('SELECT created_at FROM lucky_spins WHERE telegram_id = $1 ORDER BY id DESC LIMIT 1', [parseInt(userId, 10)]);
    let nextSpinSeconds = 0;
    let canSpin = true;

    if (lastSpinRes.rows.length > 0) {
      const lastDate = new Date(lastSpinRes.rows[0].created_at);
      const now = new Date();
      const passed = (now.getTime() - lastDate.getTime()) / 1000;
      const cooldown = 24 * 3600;
      if (passed < cooldown) {
        canSpin = false;
        nextSpinSeconds = Math.max(0, Math.floor(cooldown - passed));
      }
    }

    return res.status(200).json({
      ok: true,
      can_spin: canSpin,
      is_top3: true,
      rank: rank,
      bonus_spins: 0,
      next_spin_seconds: nextSpinSeconds
    });

  } catch (err) {
    console.error('Error in spin status:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
