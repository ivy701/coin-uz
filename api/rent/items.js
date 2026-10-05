const https = require('https');

const itemsCache = new Map();
const CACHE_TTL_MS = 60000; // 60 seconds cache per query

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const category = (req.query.category || 'gifts').toLowerCase();
  const collectionAddress = (req.query.collection_address || '').trim();
  const sortBy = (req.query.sort_by || 'recently_touch').trim();
  const cursor = (req.query.cursor || '').trim();

  const cacheKey = `${category}|${collectionAddress}|${sortBy}|${cursor}`;
  const now = Date.now();
  const cachedEntry = itemsCache.get(cacheKey);

  if (cachedEntry && (now - cachedEntry.time < CACHE_TTL_MS)) {
    return res.json({ ok: true, cached: true, ...cachedEntry.data });
  }

  const apiKey = (process.env.ROXIY_API_KEY || '').trim();
  const baseUrl = (process.env.ROXIY_API_URL || 'https://stars.roxiy.uz/api/v1').replace(/\/+$/, '');

  try {
    const queryParams = new URLSearchParams();
    queryParams.set('category', category);
    if (collectionAddress) queryParams.set('collection_address', collectionAddress);
    if (sortBy) queryParams.set('sort_by', sortBy);
    if (cursor) queryParams.set('cursor', cursor);

    const targetUrl = new URL(`${baseUrl}/rent/items?${queryParams.toString()}`);
    const options = {
      hostname: targetUrl.hostname,
      port: 443,
      path: targetUrl.pathname + targetUrl.search,
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
            reject(new Error(`Noto'g'ri JSON: ${body.slice(0, 100)}`));
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

    if (data && data.ok && data.data) {
      itemsCache.set(cacheKey, { time: now, data: data.data });
      // Clean up old cache keys (keep map under 200 items)
      if (itemsCache.size > 200) {
        const oldestKey = itemsCache.keys().next().value;
        itemsCache.delete(oldestKey);
      }
      return res.json({ ok: true, cached: false, ...data.data });
    } else {
      return res.status(502).json({ ok: false, error: 'API xatosi', raw: data });
    }
  } catch (err) {
    console.error('Rent items fetch error:', err.message);
    if (cachedEntry) {
      return res.json({ ok: true, cached: true, stale: true, ...cachedEntry.data });
    }
    return res.status(500).json({ ok: false, error: err.message });
  }
};
