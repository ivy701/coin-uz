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

    // 1. 2-soatlik cheklov (G'olib bo'lgan foydalanuvchi 2 soat ichida yana promo-kod ishlata olmaydi)
    const lastUsedRes = await db.query(`
      SELECT used_at FROM lucky_promocodes 
      WHERE used_by_id = $1 AND is_used = TRUE AND used_at IS NOT NULL 
      ORDER BY used_at DESC LIMIT 1
    `, [parseInt(userId, 10)]);

    if (lastUsedRes.rows.length > 0 && lastUsedRes.rows[0].used_at) {
      const lastUsedAt = new Date(lastUsedRes.rows[0].used_at).getTime();
      const now = Date.now();
      const diffMs = now - lastUsedAt;
      const twoHoursMs = 2 * 60 * 60 * 1000;
      if (diffMs < twoHoursMs) {
        const remMs = twoHoursMs - diffMs;
        const remHours = Math.floor(remMs / (60 * 60 * 1000));
        const remMins = Math.floor((remMs % (60 * 60 * 1000)) / (60 * 1000));
        const timeMsg = remHours > 0 ? `${remHours} soat ${remMins} daqiqadan` : `${remMins} daqiqadan`;
        return res.status(200).json({
          ok: false,
          error: `⏳ Siz so'nggi 2 soat ichida allaqachon promo-kod orqali g'olib bo'lgansiz! Yangi promo-kodni ${timeMsg} so'ng ishlatishingiz mumkin.`
        });
      }
    }

    // 2. Check if code exists
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
      return res.status(200).json({ ok: false, error: `❌ '${code}' nomli promo-kod topilmadi yoki muddati tugagan!` });
    }

    const promo = promoRes.rows[0];

    // 3. Single-use check (Bitta odam ishlatdi - boshqa hech kim ishlata olmaydi)
    if (promo.is_used) {
      return res.status(200).json({
        ok: false,
        already_used: true,
        error: '❌ Ushbu promo-kod allaqachon ishlatilgan! (Har bir kod faqat 1 kishi uchun)'
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
        error: '❌ Ushbu promo-kod boshqa foydalanuvchi tomonidan hozirgina ishlatildi!'
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
      forced_prize: promo.prize_type || 'bear',
      message: 'Promo kod muvaffaqiyatli faollashtirildi! Sizga +1 ta bepul aylantirish berildi 🎉'
    });

  } catch (err) {
    console.error('Error in promocode endpoint:', err);
    return res.status(500).json({ ok: false, error: 'Server xatoligi: ' + err.message });
  }
};
