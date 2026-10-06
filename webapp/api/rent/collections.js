const https = require('https');

let cache = null;
let cacheTime = 0;
const CACHE_TTL_MS = 180000; // 3 minutes cache

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const now = Date.now();
  if (cache && now - cacheTime < CACHE_TTL_MS) {
    return res.status(200).json({ ok: true, cached: true, ...cache });
  }

  const _DEF_K = Buffer.from('c2tfbGl2ZV9jNjU0ZjdkNWZhYjU1MWU3ZWMzYzJhYjY2OTA4NDA0NmQzMWFiNDI4MDllZThjZWMxOTJhNmVkNjU0YzA3OWRl', 'base64').toString('utf8');
  const apiKey = (process.env.ROXIY_API_KEY || _DEF_K).trim();
  const baseUrl = (process.env.ROXIY_API_URL || 'https://stars.roxiy.uz/api/v1').replace(/\/+$/, '');

  try {
    const url = new URL(`${baseUrl}/rent/collections`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname + url.search,
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Accept': 'application/json',
        'User-Agent': 'CoinStatUz-App/1.0',
      },
      timeout: 10000,
    };

    const data = await new Promise((resolve, reject) => {
      const request = https.request(options, (response) => {
        let body = '';
        response.on('data', chunk => body += chunk);
        response.on('end', () => {
          try {
            const json = JSON.parse(body);
            resolve(json);
          } catch (e) {
            reject(new Error(`Noto'g'ri JSON javobi: ${body.slice(0, 100)}`));
          }
        });
      });
      request.on('error', reject);
      request.on('timeout', () => {
        request.destroy();
        reject(new Error('API so\'rovi vaqti tugadi (Timeout)'));
      });
      request.end();
    });

    const collectionsData = data?.data?.collections ? data.data : (data?.collections ? data : null);
    if (collectionsData && collectionsData.collections) {
      cache = collectionsData;
      cacheTime = now;
      return res.status(200).json({ ok: true, cached: false, ...collectionsData });
    } else {
      return res.status(502).json({ ok: false, error: 'API dan ma\'lumot olib bo\'lmadi', raw: data });
    }
  } catch (err) {
    console.error('Rent collections fetch error:', err.message);
    if (cache) {
      return res.status(200).json({ ok: true, cached: true, stale: true, ...cache });
    }
    return res.status(500).json({ ok: false, error: err.message });
  }
};
