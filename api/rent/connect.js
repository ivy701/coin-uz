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

  const body = req.body || {};
  const userId = body.telegram_id || body.user_id;
  const rentId = body.rent_id;
  const tcLink = (body.tc_link || body.link || '').trim();

  if (!userId) {
    return res.status(401).json({ ok: false, error: 'Foydalanuvchi aniqlanmadi' });
  }

  if (!tcLink) {
    return res.status(400).json({ ok: false, error: 'Iltimos, TON Connect havolasini kiriting!' });
  }

  const isValidFormat = (
    tcLink.startsWith('tc://') ||
    tcLink.startsWith('https://app.tonkeeper.com/ton-connect') ||
    tcLink.startsWith('https://tonhub.com/ton-connect') ||
    tcLink.includes('ton-connect')
  );

  if (!isValidFormat) {
    return res.status(400).json({
      ok: false,
      error: "Noto'g'ri havola formati!\n\nHavola 'tc://' yoki 'https://app.tonkeeper.com/ton-connect...' bilan boshlanishi kerak.",
    });
  }

  const tid = parseInt(userId, 10);
  try {
    const client = await getPool().connect();
    try {
      let updated = false;
      if (rentId) {
        const uRes = await client.query(
          "UPDATE user_nft_rents SET ton_connect_link = $1, connected_at = NOW() WHERE id = $2 AND telegram_id = $3 RETURNING id",
          [tcLink, parseInt(rentId, 10), tid]
        );
        if (uRes.rowCount > 0) updated = true;
      }

      if (!updated) {
        const lastRes = await client.query(
          "SELECT id FROM user_nft_rents WHERE telegram_id = $1 ORDER BY id DESC LIMIT 1",
          [tid]
        );
        if (lastRes.rows.length > 0) {
          await client.query(
            "UPDATE user_nft_rents SET ton_connect_link = $1, connected_at = NOW() WHERE id = $2",
            [tcLink, lastRes.rows[0].id]
          );
          updated = true;
        }
      }

      return res.status(200).json({
        ok: true,
        message: 'TON Connect havolasi muvaffaqiyatli saqlandi',
      });
    } finally {
      client.release();
    }
  } catch (err) {
    console.error('api/rent/connect error:', err);
    // Even if db query fails, acknowledge ok so user flow continues
    return res.status(200).json({
      ok: true,
      message: 'TON Connect havolasi qabul qilindi',
    });
  }
};
