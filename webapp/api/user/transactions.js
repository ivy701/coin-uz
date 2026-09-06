const { Pool } = require('pg');

let pool;
function getPool() {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL || 'postgresql://neondb_owner:npg_gbusDUvG1z8M@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require';
    pool = new Pool({
      connectionString,
      ssl: { rejectUnauthorized: false },
      max: 5,
      idleTimeoutMillis: 30000,
    });
  }
  return pool;
}

function parseUserId(req) {
  let uid = null;
  
  if (req.query) {
    uid = req.query.telegram_id || req.query.user_id || req.query.id || req.query.uid;
  }

  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch(e) {}
  }
  if (!uid && body) {
    uid = body.telegram_id || body.user_id || body.id || body.uid;
    if (!uid && body.initData) {
      try {
        const params = new URLSearchParams(body.initData);
        const userStr = params.get('user');
        if (userStr) {
          const u = JSON.parse(userStr);
          uid = u.id;
        }
      } catch (e) {}
    }
  }

  const initHeader = req.headers ? (req.headers['x-telegram-init-data'] || req.headers['X-Telegram-Init-Data']) : null;
  if (!uid && initHeader) {
    try {
      const params = new URLSearchParams(initHeader);
      const userStr = params.get('user');
      if (userStr) {
        const u = JSON.parse(userStr);
        uid = u.id;
      }
    } catch (e) {}
  }

  return uid ? parseInt(uid, 10) : null;
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
