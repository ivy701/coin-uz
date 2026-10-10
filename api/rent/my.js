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
      // 1. Fetch user_nft_rents (active and not expired)
      let rents = [];
      try {
        await client.query(
          "UPDATE user_nft_rents SET status = 'expired' WHERE telegram_id = $1 AND status != 'expired' AND expires_at IS NOT NULL AND expires_at <= NOW()",
          [tid]
        ).catch(() => {});

        const rentsRes = await client.query(
          "SELECT * FROM user_nft_rents WHERE telegram_id = $1 AND status = 'active' AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY id DESC LIMIT 50",
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
            "SELECT * FROM orders WHERE telegram_id = $1 AND product_type = 'nft_rent' AND status != 'failed' ORDER BY id DESC LIMIT 20",
            [tid]
          );
          const nowMs = Date.now();
          for (const o of ordRes.rows) {
            const days = o.quantity || 1;
            const createdAtMs = o.created_at ? new Date(o.created_at).getTime() : nowMs;
            const expiresAtMs = createdAtMs + (days * 24 * 60 * 60 * 1000);
            const remainingMs = expiresAtMs - nowMs;
            if (remainingMs <= 0) {
              continue; // EXPIRED! Skip so it disappears from Mening rentlarim
            }
            const remainingDays = Math.max(1, Math.ceil(remainingMs / (24 * 60 * 60 * 1000)));

            rents.push({
              id: o.id,
              nft_name: o.target_username || "Telegram NFT",
              category: "gifts",
              image_url: "./images/gift.webp",
              days: days,
              remaining_days: remainingDays,
              price_total: o.amount || 0,
              target_username: defaultUname,
              status: "active",
              is_connected: false,
              created_at: o.created_at,
              expires_at: new Date(expiresAtMs).toISOString(),
            });
          }
        } catch (e) {}
      }

      const nowMs = Date.now();
      const formatted = [];
      for (const r of rents) {
        let isExpired = r.status === 'expired';
        let remDays = r.remaining_days || r.days || 1;
        if (r.expires_at) {
          const expMs = new Date(r.expires_at).getTime();
          if (!isNaN(expMs)) {
            const diffMs = expMs - nowMs;
            if (diffMs <= 0) {
              isExpired = true;
            } else {
              remDays = Math.max(1, Math.ceil(diffMs / (24 * 60 * 60 * 1000)));
            }
          }
        }
        if (isExpired) {
          continue; // EXPIRED! Filter out so it disappears from Mening rentlarim
        }

        const target = r.target_username || defaultUname || '';
        formatted.push({
          id: r.id,
          nft_name: r.nft_name || 'Telegram NFT',
          nft_address: r.nft_address || '',
          category: r.category || 'gifts',
          image_url: r.image_url || './images/gift.webp',
          days: r.days || 1,
          remaining_days: remDays,
          price_total: r.price_total || 0,
          target_username: target,
          status: 'active',
          is_connected: Boolean(r.ton_connect_link || r.is_connected),
          created_at: r.created_at,
          expires_at: r.expires_at,
        });
      }

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
