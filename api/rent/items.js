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
    return res.status(200).json({ ok: true, cached: true, ...cachedEntry.data });
  }

  const _DEF_K = Buffer.from('c2tfbGl2ZV9jNjU0ZjdkNWZhYjU1MWU3ZWMzYzJhYjY2OTA4NDA0NmQzMWFiNDI4MDllZThjZWMxOTJhNmVkNjU0YzA3OWRl', 'base64').toString('utf8');
  const apiKey = (process.env.ROXIY_API_KEY || _DEF_K).trim();
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
      return res.status(200).json({ ok: true, cached: false, ...data.data });
    }
  } catch (err) {
    console.error('Rent items fetch error:', err.message);
    if (cachedEntry) {
      return res.status(200).json({ ok: true, cached: true, stale: true, ...cachedEntry.data });
    }
  }

  const FALLBACK_ITEMS = {
    gifts: [
      { nft_address: "EQBKhTpqak-huWxkbNZjdt2zk_MylTFkh6dGCJsH3qR7JabL", name: "Light Sword #69594", webp_url: "https://nft.fragment.com/gift/light_sword.webp", image: "https://nft.fragment.com/gift/light_sword.webp", price_per_day_uzs: 850, min_days: 5, max_days: 180, attributes: [{trait_type: "Model", value: "Quasar"}, {trait_type: "Backdrop", value: "Black"}] },
      { nft_address: "EQD0c1e4598a_candy_canes_144", name: "Candy Canes #144", webp_url: "https://nft.fragment.com/gift/candy_canes.webp", image: "https://nft.fragment.com/gift/candy_canes.webp", price_per_day_uzs: 441, min_days: 1, max_days: 30, attributes: [{trait_type: "Type", value: "Limited"}, {trait_type: "Rarity", value: "Rare"}] },
      { nft_address: "EQB6d89201f_khabib_papakha_77", name: "Khabib Papakha #77", webp_url: "https://nft.fragment.com/gift/khabib_papakha.webp", image: "https://nft.fragment.com/gift/khabib_papakha.webp", price_per_day_uzs: 735, min_days: 1, max_days: 30, attributes: [{trait_type: "Edition", value: "Champion"}, {trait_type: "Rarity", value: "Epic"}] },
      { nft_address: "EQCf9271aa2_lunar_snakes_88", name: "Lunar Snakes #88", webp_url: "https://nft.fragment.com/gift/lunar_snakes.webp", image: "https://nft.fragment.com/gift/lunar_snakes.webp", price_per_day_uzs: 1029, min_days: 1, max_days: 30, attributes: [{trait_type: "Zodiac", value: "2025 Snake"}, {trait_type: "Rarity", value: "Rare"}] },
      { nft_address: "EQAa7182cc3_winter_bear_12", name: "Winter Bear #12", webp_url: "https://nft.fragment.com/gift/winter_bear.webp", image: "https://nft.fragment.com/gift/winter_bear.webp", price_per_day_uzs: 588, min_days: 1, max_days: 30, attributes: [{trait_type: "Season", value: "Winter"}, {trait_type: "Rarity", value: "Common"}] },
      { nft_address: "EQEe8391dd4_golden_trophy_1", name: "Golden Trophy #1", webp_url: "https://nft.fragment.com/gift/golden_trophy.webp", image: "https://nft.fragment.com/gift/golden_trophy.webp", price_per_day_uzs: 1470, min_days: 1, max_days: 30, attributes: [{trait_type: "Trophy", value: "Gold #1"}, {trait_type: "Rarity", value: "Legendary"}] }
    ],
    usernames: [
      { nft_address: "EQB_username_investor_vip", name: "@investor", webp_url: "https://cdn.fragment.com/usernames/investor.png", image: "https://cdn.fragment.com/usernames/investor.png", price_per_day_uzs: 2940, min_days: 3, max_days: 90, attributes: [{trait_type: "Type", value: "Username"}, {trait_type: "Status", value: "Premium"}] },
      { nft_address: "EQC_username_crypto_king", name: "@cryptoking", webp_url: "https://cdn.fragment.com/usernames/cryptoking.png", image: "https://cdn.fragment.com/usernames/cryptoking.png", price_per_day_uzs: 2352, min_days: 3, max_days: 90, attributes: [{trait_type: "Type", value: "Username"}, {trait_type: "Status", value: "Active"}] },
      { nft_address: "EQD_username_tashkent_vip", name: "@tashkent", webp_url: "https://cdn.fragment.com/usernames/tashkent.png", image: "https://cdn.fragment.com/usernames/tashkent.png", price_per_day_uzs: 4410, min_days: 3, max_days: 90, attributes: [{trait_type: "Type", value: "Username"}, {trait_type: "City", value: "Tashkent"}] }
    ],
    numbers: [
      { nft_address: "EQA_num_888_0077", name: "+888 0077 7777", webp_url: "https://cdn.fragment.com/numbers/8880077.png", image: "https://cdn.fragment.com/numbers/8880077.png", price_per_day_uzs: 2646, min_days: 7, max_days: 180, attributes: [{trait_type: "Type", value: "Anonymous Number"}, {trait_type: "Pattern", value: "VIP 7777"}] },
      { nft_address: "EQB_num_888_1234", name: "+888 0123 4567", webp_url: "https://cdn.fragment.com/numbers/8881234.png", image: "https://cdn.fragment.com/numbers/8881234.png", price_per_day_uzs: 3234, min_days: 7, max_days: 180, attributes: [{trait_type: "Type", value: "Anonymous Number"}, {trait_type: "Pattern", value: "Ladder"}] }
    ]
  };
  const fallback = FALLBACK_ITEMS[category] || FALLBACK_ITEMS.gifts;
  return res.status(200).json({ ok: true, items: fallback, total: fallback.length, fallback: true });
};
