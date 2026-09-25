const { Pool } = require('pg');

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

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  let period = 'all';
  if (req.query && req.query.period) {
    period = req.query.period;
  } else if (req.body && req.body.period) {
    period = req.body.period;
  }

  let timeFilter = "";
  if (period === 'today') {
    timeFilter = "AND o.created_at >= CURRENT_DATE";
  } else if (period === 'week') {
    timeFilter = "AND o.created_at >= NOW() - INTERVAL '7 days'";
  } else if (period === 'month') {
    timeFilter = "AND o.created_at >= NOW() - INTERVAL '30 days'";
  }

  try {
    const db = getPool();
    
    // Rank users ONLY by actual purchases / spending (excluding topup/deposit)
    const query = `
      SELECT 
        o.telegram_id,
        COALESCE(NULLIF(MAX(u.username), ''), NULLIF(MAX(o.target_username), ''), 'User#' || o.telegram_id) as username,
        COALESCE(MAX(u.full_name), '') as full_name,
        SUM(o.amount)::BIGINT as total
      FROM orders o
      LEFT JOIN users u ON u.telegram_id = o.telegram_id
      WHERE o.status IN ('completed', 'paid')
        AND o.product_type NOT LIKE 'topup%'
        AND o.product_type NOT IN ('deposit', 'balance')
        ${timeFilter}
      GROUP BY o.telegram_id
      HAVING SUM(o.amount) > 0
      ORDER BY total DESC
      LIMIT 50
    `;

    const result = await db.query(query);

    let rating = result.rows.map(r => ({
      telegram_id: Number(r.telegram_id),
      username: (r.username ? (r.username.startsWith('@') ? r.username.replace(/^@/, '') : r.username) : `User#${r.telegram_id}`),
      total: Number(r.total || 0),
    }));

    return res.status(200).json({
      ok: true,
      period,
      rating,
    });
  } catch (err) {
    console.error('Rating query error:', err);
    return res.status(500).json({ ok: false, error: err.message, rating: [] });
  }
};
