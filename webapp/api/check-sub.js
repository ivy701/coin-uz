const https = require('https');

function checkTelegramMembership(botToken, channel, userId) {
  return new Promise((resolve) => {
    const cleanChannel = channel.startsWith('@') ? channel : `@${channel}`;
    const url = `https://api.telegram.org/bot${botToken}/getChatMember?chat_id=${encodeURIComponent(cleanChannel)}&user_id=${encodeURIComponent(userId)}`;

    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (json.ok && json.result) {
            const status = json.result.status;
            const isMember = ['creator', 'administrator', 'member'].includes(status) || 
                             (status === 'restricted' && Boolean(json.result.is_member));
            return resolve({ ok: true, subscribed: Boolean(isMember), status });
          }
          resolve({ ok: true, subscribed: false, error: json.description || 'Not a member' });
        } catch (e) {
          resolve({ ok: true, subscribed: false, error: 'JSON parse error' });
        }
      });
    }).on('error', (err) => {
      // In case of network error, resolve without crashing
      resolve({ ok: false, subscribed: true, error: err.message });
    });
  });
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
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const userId = parseUserId(req);
  const botToken = (process.env.BOT_TOKEN || '8540635645:AAE3c-NEqdR4F05X_7Vyiq7kP3XD5PmzX7Y').trim();
  const channel = (process.env.REQUIRED_CHANNEL || process.env.CHANNEL_ORDERS || '@CoinStatUz').trim();
  const channelUrl = `https://t.me/${channel.replace(/^@/, '')}`;

  if (!userId || isNaN(userId)) {
    return res.status(200).json({
      ok: true,
      subscribed: false,
      channel,
      channel_url: channelUrl,
      error: 'User ID missing'
    });
  }

  try {
    const result = await checkTelegramMembership(botToken, channel, userId);
    return res.status(200).json({
      ok: true,
      subscribed: result.subscribed,
      channel,
      channel_url: channelUrl,
      status: result.status || null
    });
  } catch (err) {
    return res.status(200).json({
      ok: true,
      subscribed: false,
      channel,
      channel_url: channelUrl,
      error: err.message
    });
  }
};
