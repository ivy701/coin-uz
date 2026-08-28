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

  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'Method not allowed' });
  }

  try {
    let body = req.body || {};
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body);
      } catch (e) {}
    }

    let userId = body.telegram_id || body.user_id;
    if (!userId && body.initData) {
      try {
        const parsed = new URLSearchParams(body.initData);
        const userStr = parsed.get('user');
        if (userStr) {
          const u = JSON.parse(userStr);
          if (u && u.id) userId = u.id;
        }
      } catch(e) {}
    }
    const code = (body.code || '').trim().toUpperCase();

    if (!userId) {
      return res.status(200).json({ ok: false, error: 'Foydalanuvchi aniqlanmadi. Iltimos qayta kiring!' });
    }
    if (!code) {
      return res.status(200).json({ ok: false, error: 'Iltimos, promo kodni kiriting!' });
    }

    const db = getPool();

    // Ensure lucky_promocodes and user_bonus_spins tables exist
    await db.query(`
      CREATE TABLE IF NOT EXISTS lucky_promocodes (
        id SERIAL PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        is_used BOOLEAN NOT NULL DEFAULT FALSE,
        used_by_id BIGINT,
        used_by_username TEXT,
        used_by_name TEXT,
        used_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);

    await db.query(`
      CREATE TABLE IF NOT EXISTS user_bonus_spins (
        telegram_id BIGINT PRIMARY KEY,
        spins_left INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);

    // Check if code exists
    let promoRes = await db.query('SELECT * FROM lucky_promocodes WHERE UPPER(code) = UPPER($1)', [code]);
    
    // Auto-seed default promo codes
    const defaultCodes = [
      'CS-7711', 'CS-781', 'BEAR-99', 'TEDDY2026', 'BEAR777',
      'CS-8822', 'CS-892', 'GOLD-77', 'VINO2026',
      'CS-3399', 'CS-345', 'RUBY-44', 'ROSE2026',
      'CS-9900', 'CS-911', 'DIAMOND-7', 'PREMIUM2026',
      'CS-5544', 'CS-567', 'TURBO-88', 'ROCKET2026',
      'CS-1122', 'CS-123', 'MEGA-50', 'STARS2026',
      'CS-4433', 'CS-456', 'CASH-20', 'MONEY2026',
      'CS-2026', 'WIN-777', 'SPIN777', 'LUCKY-VIP', 'LUCKY2026',
      'COINSTATVIP', 'GIFT2026', 'VIP2026', 'TOP1', 'TOP2', 'TOP3'
    ];
    if (promoRes.rows.length === 0 && defaultCodes.includes(code)) {
      await db.query('INSERT INTO lucky_promocodes (code) VALUES ($1) ON CONFLICT DO NOTHING', [code]);
      promoRes = await db.query('SELECT * FROM lucky_promocodes WHERE UPPER(code) = UPPER($1)', [code]);
    }

    if (promoRes.rows.length === 0) {
      return res.status(200).json({ ok: false, error: `'${code}' nomli promo kod topilmadi!` });
    }

    const promo = promoRes.rows[0];

    if (promo.is_used) {
      let userLabel = 'boshqa foydalanuvchi';
      if (promo.used_by_username) {
        userLabel = `@${promo.used_by_username.replace('@', '')}`;
      } else if (promo.used_by_name) {
        userLabel = promo.used_by_name;
      } else if (promo.used_by_id) {
        userLabel = `Foydalanuvchi #${promo.used_by_id}`;
      }

      if (promo.used_by_id && String(promo.used_by_id) === String(userId)) {
        return res.status(200).json({
          ok: false,
          already_used: true,
          error: 'Siz ushbu promo kodni allaqachon faollashtirgansiz!'
        });
      }

      return res.status(200).json({
        ok: false,
        already_used: true,
        used_by: userLabel,
        error: `Ushbu promo kod allaqachon faollashtirilgan! (${userLabel})`
      });
    }

    // Get user info if available
    let uname = '';
    let fname = '';
    const userRes = await db.query('SELECT username, full_name FROM users WHERE telegram_id = $1', [parseInt(userId, 10)]);
    if (userRes.rows.length > 0) {
      uname = userRes.rows[0].username || '';
      fname = userRes.rows[0].full_name || '';
    }

    // Mark as used atomically
    const updateRes = await db.query(`
      UPDATE lucky_promocodes 
      SET is_used = TRUE, used_by_id = $1, used_by_username = $2, used_by_name = $3, used_at = NOW() 
      WHERE UPPER(code) = UPPER($4) AND is_used = FALSE
      RETURNING id
    `, [parseInt(userId, 10), uname, fname, code]);

    if (updateRes.rows.length === 0) {
      return res.status(200).json({
        ok: false,
        error: 'Ushbu promo kod boshqa foydalanuvchi tomonidan hozirgina faollashtirildi!'
      });
    }

    // Add +1 bonus spin
    await db.query(`
      INSERT INTO user_bonus_spins (telegram_id, spins_left, updated_at)
      VALUES ($1, 1, NOW())
      ON CONFLICT (telegram_id)
      DO UPDATE SET spins_left = user_bonus_spins.spins_left + 1, updated_at = NOW();
    `, [parseInt(userId, 10)]);

    return res.status(200).json({
      ok: true,
      message: 'Promo kod muvaffaqiyatli faollashtirildi! Sizga +1 ta bepul aylantirish berildi 🎉'
    });

  } catch (err) {
    console.error('Error in promocode endpoint:', err);
    return res.status(500).json({ ok: false, error: 'Server xatoligi: ' + err.message });
  }
};
