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

  const userId = req.query.telegram_id || req.query.user_id || (req.body && (req.body.telegram_id || req.body.user_id));
  if (!userId) {
    return res.status(200).json({ ok: true, rents: [], count: 0 });
  }

  const tid = parseInt(userId, 10);
  if (isNaN(tid)) {
    return res.status(200).json({ ok: true, rents: [], count: 0 });
  }

  try {
    const client = await getPool().connect();
    try {
      // 1. Fetch user_nft_rents
      let rents = [];
      try {
        const rentsRes = await client.query(
          "SELECT * FROM user_nft_rents WHERE telegram_id = $1 ORDER BY id DESC LIMIT 50",
          [tid]
        );
        rents = rentsRes.rows || [];
      } catch (tableErr) {
        // Table may not exist yet in Postgres
      }

      // 2. Fetch default username
      let defaultUname = '';
      try {
        const uRes = await client.query("SELECT username FROM users WHERE telegram_id = $1 LIMIT 1", [tid]);
        if (uRes.rows.length > 0) {
          defaultUname = uRes.rows[0].username || '';
        }
      } catch (e) {}

      // 3. Fallback to orders if user_nft_rents is empty
      if (!rents || rents.length === 0) {
        try {
          const ordRes = await client.query(
            "SELECT * FROM orders WHERE telegram_id = $1 AND product_type = 'nft_rent' ORDER BY id DESC LIMIT 10",
            [tid]
          );
          for (const o of ordRes.rows) {
            rents.push({
              id: o.id,
              nft_name: o.target_username || "Telegram NFT",
              category: "gifts",
              image_url: "./images/gift.webp",
              days: o.quantity || 30,
              remaining_days: o.quantity || 30,
              price_total: o.amount || 0,
              target_username: defaultUname,
              status: "active",
              is_connected: false,
            });
          }
        } catch (e) {}
      }

      const formatted = rents.map(r => {
        const target = r.target_username || defaultUname || '';
        return {
          id: r.id,
          nft_name: r.nft_name || 'Telegram NFT',
          nft_address: r.nft_address || '',
          category: r.category || 'gifts',
          image_url: r.image_url || './images/gift.webp',
          days: r.days || 1,
          remaining_days: r.remaining_days || r.days || 1,
          price_total: r.price_total || 0,
          target_username: target,
          status: r.status || 'active',
          is_connected: Boolean(r.ton_connect_link || r.is_connected),
          created_at: r.created_at,
          expires_at: r.expires_at,
        };
      });

      return res.status(200).json({
        ok: true,
        rents: formatted,
        count: formatted.length,
      });
    } finally {
      client.release();
    }
  } catch (err) {
    console.error('api/rent/my error:', err);
    return res.status(200).json({ ok: true, rents: [], count: 0 });
  }
};
