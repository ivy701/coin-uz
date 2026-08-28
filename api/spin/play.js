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

const PRIZES = [
  { key: "teddy", title: "🧸 Teddy Bear Gift", type: "gift", weight: 12, index: 0 },
  { key: "rose", title: "🌹 Rose Gift", type: "gift", weight: 6, index: 1 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 5, index: 2 },
  { key: "uzs10000", title: "💰 10 000 UZS Balans", type: "balance", amount: 10000, weight: 5, index: 3 },
  { key: "champagne", title: "🍾 Champagne Gift", type: "gift", weight: 6, index: 4 },
  { key: "teddy", title: "🧸 Teddy Bear Gift", type: "gift", weight: 12, index: 5 },
  { key: "rocket", title: "🚀 Rocket Gift", type: "gift", weight: 3, index: 6 },
  { key: "stars25", title: "⭐️ 25 Stars", type: "stars", amount: 25, weight: 6, index: 7 },
  { key: "uzs5000", title: "💰 5 000 UZS Balans", type: "balance", amount: 5000, weight: 6, index: 8 },
  { key: "rose", title: "🌹 Rose Gift", type: "gift", weight: 6, index: 9 },
  { key: "teddy", title: "🧸 Teddy Bear Gift", type: "gift", weight: 12, index: 10 },
  { key: "champagne", title: "🍾 Champagne Gift", type: "gift", weight: 6, index: 11 },
  { key: "stars100", title: "⭐️ 100 Stars", type: "stars", amount: 100, weight: 3, index: 12 },
  { key: "uzs20000", title: "💰 20 000 UZS Balans", type: "balance", amount: 20000, weight: 3, index: 13 },
  { key: "premium", title: "💎 Telegram Premium", type: "premium", weight: 2, index: 14 },
  { key: "teddy", title: "🧸 Teddy Bear Gift", type: "gift", weight: 12, index: 15 },
  { key: "rose", title: "🌹 Rose Gift", type: "gift", weight: 6, index: 16 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 5, index: 17 },
  { key: "rocket", title: "🚀 Rocket Gift", type: "gift", weight: 3, index: 18 },
  { key: "teddy", title: "🧸 Teddy Bear Gift", type: "gift", weight: 12, index: 19 }
];

function pickWeightedPrize() {
  const totalWeight = PRIZES.reduce((sum, p) => sum + p.weight, 0);
  let rand = Math.random() * totalWeight;
  for (const prize of PRIZES) {
    if (rand < prize.weight) return prize;
    rand -= prize.weight;
  }
  return PRIZES[0];
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
    let body = req.body || {};
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch (e) {}
    }
    const userId = body.telegram_id || body.user_id;
    if (!userId) {
      return res.status(401).json({ ok: false, error: 'Unauthorized' });
    }

    const db = getPool();

    // Consume bonus spin if available
    const bonusRes = await db.query(`
      UPDATE user_bonus_spins
      SET spins_left = spins_left - 1, updated_at = NOW()
      WHERE telegram_id = $1 AND spins_left > 0
      RETURNING spins_left
    `, [parseInt(userId, 10)]);

    const usedBonus = bonusRes.rows.length > 0;

    if (!usedBonus) {
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
      const isTop3 = topRes.rows.some(r => String(r.telegram_id) === String(userId));
      if (!isTop3) {
        return res.status(403).json({
          ok: false,
          error: 'Omad g\'ildiragi faqat Top 3 yetakchilar uchun yoki Promo kod orqali ochiladi!'
        });
      }

      // Check 24h cooldown
      const lastSpinRes = await db.query('SELECT created_at FROM lucky_spins WHERE telegram_id = $1 ORDER BY id DESC LIMIT 1', [parseInt(userId, 10)]);
      if (lastSpinRes.rows.length > 0) {
        const lastDate = new Date(lastSpinRes.rows[0].created_at);
        const now = new Date();
        const passed = (now.getTime() - lastDate.getTime()) / 1000;
        const cooldown = 24 * 3600;
        if (passed < cooldown) {
          const leftHours = Math.floor((cooldown - passed) / 3600);
          const leftMinutes = Math.floor(((cooldown - passed) % 3600) / 60);
          return res.status(400).json({
            ok: false,
            error: `Siz bugun aylantirgansiz. Keyingi imkoniyat ${leftHours} soat ${leftMinutes} daqiqadan keyin.`
          });
        }
      }
    }

    const chosenPrize = pickWeightedPrize();

    // Reward balance if type balance
    if (chosenPrize.type === 'balance' && chosenPrize.amount) {
      await db.query(`
        UPDATE users 
        SET balance = balance + $1 
        WHERE telegram_id = $2
      `, [chosenPrize.amount, parseInt(userId, 10)]);
    }

    // Record lucky spin
    await db.query(`
      CREATE TABLE IF NOT EXISTS lucky_spins (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        prize_key TEXT NOT NULL,
        prize_title TEXT NOT NULL,
        prize_type TEXT NOT NULL,
        prize_amount INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);

    await db.query(`
      INSERT INTO lucky_spins (telegram_id, prize_key, prize_title, prize_type, prize_amount)
      VALUES ($1, $2, $3, $4, $5)
    `, [parseInt(userId, 10), chosenPrize.key, chosenPrize.title, chosenPrize.type, chosenPrize.amount || 0]);

    return res.status(200).json({
      ok: true,
      prize: chosenPrize
    });

  } catch (err) {
    console.error('Error in spin play:', err);
    return res.status(500).json({ ok: false, error: err.message });
  }
};
