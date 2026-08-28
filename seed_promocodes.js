const { Pool } = require('pg');

const pool = new Pool({
  connectionString: 'postgresql://neondb_owner:npg_FOH4kIY9gEte@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require',
  ssl: { rejectUnauthorized: false }
});

const codes = [
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

async function main() {
  try {
    await pool.query(`
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

    for (const code of codes) {
      const existing = await pool.query('SELECT id FROM lucky_promocodes WHERE UPPER(code) = UPPER($1)', [code]);
      if (existing.rows.length === 0) {
        await pool.query('INSERT INTO lucky_promocodes (code, is_used) VALUES ($1, false)', [code]);
      } else {
        await pool.query('UPDATE lucky_promocodes SET is_used = false, used_by_id = NULL, used_by_username = NULL, used_by_name = NULL, used_at = NULL WHERE UPPER(code) = UPPER($1)', [code]);
      }
    }

    const all = await pool.query('SELECT code, is_used FROM lucky_promocodes ORDER BY id ASC');
    console.log(`Successfully seeded ${all.rows.length} promo codes!`);
    console.log(all.rows.map(r => r.code).join(', '));
  } catch (e) {
    console.error('Error seeding promocodes:', e);
  } finally {
    await pool.end();
  }
}

main();
