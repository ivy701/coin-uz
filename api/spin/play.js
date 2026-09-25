const { Pool } = require('pg');
const crypto = require('crypto');

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

function validateTelegramInitData(initData, botToken) {
  if (!initData || !botToken) return null;
  try {
    const urlParams = new URLSearchParams(initData);
    const hash = urlParams.get('hash');
    if (!hash) return null;
    urlParams.delete('hash');

    const dataCheckArr = [];
    for (const [key, val] of Array.from(urlParams.entries()).sort(([a], [b]) => a.localeCompare(b))) {
      dataCheckArr.push(`${key}=${val}`);
    }
    const dataCheckString = dataCheckArr.join('\n');

    const secretKey = crypto.createHmac('sha256', 'WebAppData').update(botToken).digest();
    const calculatedHash = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');

    if (calculatedHash !== hash) return null;

    const userRaw = urlParams.get('user');
    if (userRaw) {
      try {
        return { user: JSON.parse(userRaw) };
      } catch (e) {}
    }
    return {};
  } catch (e) {
    return null;
  }
}

const CLASSIC_PRIZES = [
  { key: "bear", title: "🧸 Teddy Bear Gift (15⭐)", type: "gift", weight: 50, index: 0 },
  { key: "rose", title: "🌹 Rose Gift (25⭐)", type: "gift", weight: 25, index: 1 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 0, index: 2 },
  { key: "uzs10000", title: "💰 10 000 UZS Balans", type: "balance", amount: 10000, weight: 0, index: 3 },
  { key: "box", title: "🎁 Gift Box (25⭐)", type: "gift", weight: 25, index: 4 },
  { key: "bear", title: "🧸 Teddy Bear Gift (15⭐)", type: "gift", weight: 50, index: 5 },
  { key: "rose", title: "🌹 Rose Gift (25⭐)", type: "gift", weight: 25, index: 6 },
  { key: "stars25", title: "⭐️ 25 Stars", type: "stars", amount: 25, weight: 0, index: 7 },
  { key: "uzs5000", title: "💰 5 000 UZS Balans", type: "balance", amount: 5000, weight: 0, index: 8 },
  { key: "box", title: "🎁 Gift Box (25⭐)", type: "gift", weight: 25, index: 9 },
  { key: "bear", title: "🧸 Teddy Bear Gift (15⭐)", type: "gift", weight: 50, index: 10 },
  { key: "rose", title: "🌹 Rose Gift (25⭐)", type: "gift", weight: 25, index: 11 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 0, index: 12 },
  { key: "uzs10000", title: "💰 10 000 UZS Balans", type: "balance", amount: 10000, weight: 0, index: 13 },
  { key: "box", title: "🎁 Gift Box (25⭐)", type: "gift", weight: 25, index: 14 },
  { key: "bear", title: "🧸 Teddy Bear Gift (15⭐)", type: "gift", weight: 50, index: 15 },
  { key: "rose", title: "🌹 Rose Gift (25⭐)", type: "gift", weight: 25, index: 16 },
  { key: "stars25", title: "⭐️ 25 Stars", type: "stars", amount: 25, weight: 0, index: 17 },
  { key: "box", title: "🎁 Gift Box (25⭐)", type: "gift", weight: 25, index: 18 },
  { key: "bear", title: "🧸 Teddy Bear Gift (15⭐)", type: "gift", weight: 50, index: 19 }
];

const VIP_PRIZES = [
  { key: "aprel_bear", title: "🌸 Aprel Ayiqchasi (50⭐)", type: "gift", weight: 10, index: 0 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 1 },
  { key: "easter_bear", title: "🐰 Pasxa Ayiqchasi (50⭐)", type: "gift", weight: 10, index: 2 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 3 },
  { key: "newyear_bear", title: "🎅 Yangi Yil Ayiqchasi (50⭐)", type: "gift", weight: 10, index: 4 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 5 },
  { key: "builder_bear", title: "🔨 Usta Ayiqcha (50⭐)", type: "gift", weight: 10, index: 6 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 7 },
  { key: "football_bear", title: "⚽ Futbolchi Ayiqcha (50⭐)", type: "gift", weight: 10, index: 8 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 9 },
  { key: "soldier_bear", title: "💣 Jangchi Ayiqcha (50⭐)", type: "gift", weight: 10, index: 10 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 11 },
  { key: "newyear_tree", title: "🎄 Yangi Yil Archasi (50⭐)", type: "gift", weight: 10, index: 12 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 13 },
  { key: "patrick_bear", title: "🍀 Patrik Ayiqchasi (50⭐)", type: "gift", weight: 10, index: 14 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 15 },
  { key: "valentine_bear", title: "💘 Valentin Ayiqchasi (50⭐)", type: "gift", weight: 10, index: 16 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 17 },
  { key: "valentine_heart", title: "💕 Valentinka Yurakchasi (50⭐)", type: "gift", weight: 10, index: 18 },
  { key: "stars50", title: "⭐️ 50 Stars", type: "stars", amount: 50, weight: 15, index: 19 }
];

const ALL_PRIZES = [...CLASSIC_PRIZES, ...VIP_PRIZES];

function pickWeightedPrize(isVip = false) {
  const list = isVip ? VIP_PRIZES : CLASSIC_PRIZES;
  const eligible = list.filter(p => p.weight > 0);
  const totalWeight = eligible.reduce((sum, p) => sum + p.weight, 0);
  let rand = Math.random() * totalWeight;
  for (const prize of eligible) {
    if (rand < prize.weight) return prize;
    rand -= prize.weight;
  }
  return list[0];
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

  const db = getPool();

  try {
    const botToken = (process.env.BOT_TOKEN || '').trim();
    const body = req.body || {};
    const initData = req.headers['x-telegram-init-data'] || body.initData || '';

    let authUserId = null;
    if (botToken && initData) {
      const validated = validateTelegramInitData(initData, botToken);
      authUserId = validated?.user?.id;
    }

    if (!authUserId && process.env.ALLOW_UNSAFE_DEV_AUTH === 'true') {
      authUserId = body.telegram_id || body.user_id;
    }

    if (!authUserId) {
      return res.status(401).json({ ok: false, error: 'Telegram initData yaroqsiz yoki muddati o\'tgan (Unauthorized)' });
    }

    const claimedId = body.telegram_id || body.user_id;
    if (claimedId && parseInt(claimedId, 10) !== parseInt(authUserId, 10)) {
      return res.status(403).json({ ok: false, error: 'Foydalanuvchi identifikatori mos kelmadi (Forbidden)' });
    }

    const userId = parseInt(authUserId, 10);

    // Consume bonus spin if available
    const bonusRes = await db.query(`
      UPDATE user_bonus_spins
      SET spins_left = spins_left - 1, updated_at = NOW()
      WHERE telegram_id = $1 AND spins_left > 0
      RETURNING spins_left, forced_prize
    `, [userId]);

    const usedBonus = bonusRes.rows.length > 0;

    if (!usedBonus) {
      return res.status(403).json({
        ok: false,
        error: 'Omad g\'ildiragini aylantirish uchun avval Promo Kod kiriting!'
      });
    }

    const isVipMode = body.mode === 'vip';
    // SECURITY: The user cannot supply forced_prize. It is strictly determined by the DB record!
    const effectiveForcedKey = bonusRes.rows[0]?.forced_prize || 'bear';
    const searchClean = String(effectiveForcedKey).toLowerCase().trim();
    const rareKeys = ['aprel_bear', 'easter_bear', 'newyear_bear', 'builder_bear', 'football_bear', 'soldier_bear', 'newyear_tree', 'patrick_bear', 'valentine_bear', 'valentine_heart', 'rare', 'vipgift'];

    // Security: Block Classic Promo on VIP wheel
    if (isVipMode && !rareKeys.includes(searchClean)) {
      await db.query(`
        UPDATE user_bonus_spins
        SET spins_left = spins_left + 1
        WHERE telegram_id = $1
      `, [parseInt(userId, 10)]);

      return res.status(400).json({
        ok: false,
        error: '❌ Siz kiritgan promo-kod faqat Klassik Spin uchun! Iltimos, \'Klassik Spin\' bo\'limiga o\'ting.'
      });
    }

    let chosenPrize = null;

    if (effectiveForcedKey) {
      let searchKey = searchClean;
      if (searchKey === 'rare' || searchKey === 'vipgift') {
        const giftList = ['aprel_bear', 'easter_bear', 'newyear_bear', 'builder_bear', 'football_bear', 'soldier_bear', 'newyear_tree', 'patrick_bear', 'valentine_bear', 'valentine_heart'];
        searchKey = giftList[Math.floor(Math.random() * giftList.length)];
      } else if (searchKey === 'builder' || searchKey === 'usta' || searchKey === 'builder_bear') {
        searchKey = 'builder_bear';
      } else if (searchKey === 'football' || searchKey === 'futbol' || searchKey === 'football_bear') {
        searchKey = 'football_bear';
      } else if (searchKey === 'soldier' || searchKey === 'jangchi' || searchKey === 'military' || searchKey === 'cs' || searchKey === 'soldier_bear') {
        searchKey = 'soldier_bear';
      } else if (searchKey === 'gift25' || searchKey === 'gift') {
        searchKey = Math.random() < 0.5 ? 'rose' : 'box';
      } else if (searchKey === 'stars') {
        searchKey = 'stars50';
      } else if (searchKey === 'starvip') {
        searchKey = 'stars50';
      } else if (searchKey === 'money' || searchKey === 'balans') {
        searchKey = Math.random() < 0.5 ? 'uzs10000' : 'uzs20000';
      } else if (searchKey === 'moneyvip') {
        searchKey = Math.random() < 0.5 ? 'uzs50000' : 'uzs100000';
      } else if (searchKey === 'bear' || searchKey === 'teddy') {
        searchKey = 'bear';
      } else if (searchKey === 'premium' || searchKey === 'vip') {
        searchKey = 'premium';
      }

      const activeList = isVipMode ? VIP_PRIZES : ALL_PRIZES;
      const matched = activeList.filter(p => p.key === searchKey);
      if (matched.length > 0) {
        chosenPrize = matched[Math.floor(Math.random() * matched.length)];
      } else {
        const anyMatched = ALL_PRIZES.filter(p => p.key === searchKey);
        if (anyMatched.length > 0) {
          chosenPrize = anyMatched[Math.floor(Math.random() * anyMatched.length)];
        }
      }
    }

    if (!chosenPrize) {
      chosenPrize = pickWeightedPrize(isVipMode);
    }

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
