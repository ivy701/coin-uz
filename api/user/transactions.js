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
      idleTimeoutMillis: 30000,
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

function parseUserId(req) {
  const botToken = (process.env.BOT_TOKEN || '').trim();
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch(e) {}
  }

  const initData = (req.headers ? (req.headers['x-telegram-init-data'] || req.headers['X-Telegram-Init-Data']) : null)
    || (body && body.initData)
    || (req.query && req.query.initData);

  if (botToken && initData) {
    const validated = validateTelegramInitData(initData, botToken);
    if (validated && validated.user && validated.user.id) {
      return parseInt(validated.user.id, 10);
    }
  }

  if (process.env.ALLOW_UNSAFE_DEV_AUTH === 'true') {
    let uid = null;
    if (req.query) uid = req.query.telegram_id || req.query.user_id || req.query.id || req.query.uid;
    if (!uid && body) uid = body.telegram_id || body.user_id || body.id || body.uid;
    if (uid) return parseInt(uid, 10);
  }

  return null;
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const userId = parseUserId(req);
  if (!userId || isNaN(userId)) {
    return res.status(200).json({
      ok: true,
      orders: [],
      balance_history: [],
      total_spent: 0,
      orders_count: 0,
    });
  }

  try {
    const db = getPool();

    // 1. Fetch user orders
    let orders = [];
    try {
      const ordersResult = await db.query(
        `SELECT id, telegram_id, product_type, target_username, quantity, amount, status, external_id, created_at 
         FROM orders 
         WHERE telegram_id = $1 
         ORDER BY id DESC 
         LIMIT 100`,
        [userId]
      );
      orders = ordersResult.rows || [];
    } catch (e) {
      console.warn('Orders query error:', e.message);
    }

    // 2. Fetch user balance history
    let balanceHistory = [];
    try {
      const balResult = await db.query(
        `SELECT id, telegram_id, amount, type, balance_before, balance_after, reason, created_at 
         FROM balance_history 
         WHERE telegram_id = $1 
         ORDER BY id DESC 
         LIMIT 100`,
        [userId]
      );
      balanceHistory = balResult.rows || [];
    } catch (e) {
      console.warn('Balance history table error:', e.message);
    }

    // 3. Calculate total spent and orders count (ONLY actual purchases, excluding topup/deposit)
    const validOrders = orders.filter(o => {
      const pt = String(o.product_type || '').toLowerCase();
      return !pt.startsWith('topup') && 
             pt !== 'deposit' && 
             pt !== 'balance' && 
             o.status !== 'cancelled' && 
             o.status !== 'failed' && 
             o.status !== 'rejected';
    });
    
    let totalSpent = 0;
    validOrders.forEach(o => {
      if (o.status === 'completed' || o.status === 'paid') {
        totalSpent += Number(o.amount || 0);
      }
    });

    return res.status(200).json({
      ok: true,
      orders: orders,
      balance_history: balanceHistory,
      total_spent: totalSpent,
      orders_count: validOrders.length,
    });
  } catch (err) {
    console.error('Transactions query error:', err);
    return res.status(200).json({
      ok: true,
      orders: [],
      balance_history: [],
      total_spent: 0,
      orders_count: 0,
      error: err.message,
    });
  }
};
