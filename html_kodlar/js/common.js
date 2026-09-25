// StarPayUz - Common JavaScript Functions

const STARS_MIN = 50;
const STARS_MAX = 1000000;

const tg = window.Telegram?.WebApp || (typeof tg !== 'undefined' ? tg : null);
if (tg) {
    try {
        tg.expand();
        tg.ready();
        tg.setHeaderColor('#0a0a0f');
        tg.setBackgroundColor('#0a0a0f');
    } catch(e){}
}

let userBalance = 0;

// API base — can be overridden per-page via window.API_BASE
function getApiBase() {
    if (typeof window !== 'undefined' && window.location) {
        const host = (window.location.hostname || '').toLowerCase();
        if (host.includes('railway.app') || host.includes('localhost') || host.includes('127.0.0.1')) {
            return window.location.origin;
        }
    }
    if (typeof window.API_BASE !== 'undefined' && window.API_BASE && window.API_BASE.trim() !== '') {
        return window.API_BASE.replace(/\/$/, '');
    }
    return 'https://web-production-1b7cb.up.railway.app';
}

// Telegram Native Haptic Engine
function triggerHaptic(type = 'light') {
    if (!tg || !tg.HapticFeedback) return;
    try {
        if (type === 'light' || type === 'medium' || type === 'heavy' || type === 'rigid' || type === 'soft') {
            tg.HapticFeedback.impactOccurred(type);
        } else if (type === 'selection') {
            tg.HapticFeedback.selectionChanged();
        } else if (type === 'success' || type === 'error' || type === 'warning') {
            tg.HapticFeedback.notificationOccurred(type);
        }
    } catch (e) {}
}

function initHaptics() {
    document.addEventListener('click', (e) => {
        try {
            const clickable = e.target.closest(
                'button, .back-pill-btn, .lang-badge-pill, .stars-equiv-badge-btn, ' +
                '.spin-mode-tab, .filter-chip-btn, .package-card, .tab-btn'
            );
            if (clickable && !clickable.closest('.dock-tab-btn')) {
                triggerHaptic('light');
            }
        } catch(err) {}
    }, { passive: true });
}

// Instant Zero-Flash Hydration for Header, User Profile and Cached Stats
function hydrateInstantUserData() {
    try {
        const tgUser = tg?.initDataUnsafe?.user;
        const uid = getUserId();
        const userKey = uid || 'guest';

        // 1. User Display Name
        const cachedName = localStorage.getItem('cs_cached_name');
        let resolvedName = 'Foydalanuvchi';
        if (tgUser?.first_name) {
            resolvedName = (tgUser.first_name + (tgUser.last_name ? ' ' + tgUser.last_name : '')).trim();
            localStorage.setItem('cs_cached_name', resolvedName);
        } else if (cachedName) {
            resolvedName = cachedName;
        }
        document.querySelectorAll('#profileName, #profileHubName').forEach(nameEl => {
            nameEl.textContent = resolvedName;
        });

        // 2. User Handle or ID
        const cachedHandle = localStorage.getItem('cs_cached_handle');
        let resolvedHandle = 'ID: —';
        if (tgUser?.username) {
            resolvedHandle = '@' + tgUser.username;
            localStorage.setItem('cs_cached_handle', resolvedHandle);
        } else if (tgUser?.id || uid) {
            resolvedHandle = 'ID: ' + (tgUser?.id || uid);
            localStorage.setItem('cs_cached_handle', resolvedHandle);
        } else if (cachedHandle) {
            resolvedHandle = cachedHandle;
        }
        document.querySelectorAll('#profileUserId, #profileHubUserId').forEach(idEl => {
            idEl.textContent = resolvedHandle;
        });

        // 3. User Avatar
        const avatarImg = document.getElementById('avatarImg');
        const placeholderEl = document.getElementById('avatarPlaceholder');
        const photoUrl = tgUser?.photo_url || localStorage.getItem('cs_cached_photo');
        if (photoUrl && avatarImg) {
            avatarImg.src = photoUrl;
            avatarImg.style.display = 'block';
            if (placeholderEl) placeholderEl.style.display = 'none';
            if (tgUser?.photo_url) localStorage.setItem('cs_cached_photo', tgUser.photo_url);
        } else if (placeholderEl && tgUser?.first_name) {
            placeholderEl.textContent = tgUser.first_name.charAt(0).toUpperCase();
        }

        const myAv = document.getElementById('myAvatarImg');
        if (myAv && photoUrl) myAv.src = photoUrl;

        const profAv = document.getElementById('profileAvatar');
        if (profAv) {
            profAv.onerror = function() {
                this.onerror = null;
                if (tgUser && tgUser.first_name) {
                    this.src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(tgUser.first_name) + '&background=2563eb&color=fff&bold=true&rounded=true&size=128';
                } else {
                    this.src = './images/profile.webp?v=3';
                }
            };
            if (photoUrl) {
                profAv.src = photoUrl;
            } else if (tgUser && tgUser.username) {
                profAv.src = 'https://t.me/i/userpic/320/' + tgUser.username.replace(/^@/, '') + '.jpg';
            } else if (tgUser && tgUser.first_name) {
                profAv.src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(tgUser.first_name) + '&background=2563eb&color=fff&bold=true&rounded=true&size=128';
            } else {
                profAv.src = './images/profile.webp?v=3';
            }
        }

        // 4. Cached Balance
        const cachedBal = localStorage.getItem('starpay_balance_' + userKey) || localStorage.getItem('cs_cached_balance');
        if (cachedBal !== null && !isNaN(parseInt(cachedBal, 10))) {
            setBalUI(parseInt(cachedBal, 10));
        }

        // 5. Cached Stats (Orders count & Total spent)
        const cachedOrders = localStorage.getItem('cs_stat_orders_' + userKey);
        if (cachedOrders !== null) {
            document.querySelectorAll('#ordersCount, #profileOrdersCount, .live-orders-count').forEach(el => {
                el.textContent = cachedOrders;
            });
        }
        const cachedSpent = localStorage.getItem('cs_stat_spent_' + userKey);
        if (cachedSpent !== null) {
            document.querySelectorAll('#totalSpent, #profileTotalSpent, .live-total-spent').forEach(el => {
                el.textContent = cachedSpent;
            });
        }

        // 6. Card mask and holder on Index page
        if (uid) {
            const maskEl = document.getElementById('cardMaskUid');
            if (maskEl) maskEl.textContent = String(uid).slice(-4) || '0000';
        }
        const holderEl = document.getElementById('cardHolderName');
        if (holderEl && tgUser) {
            holderEl.textContent = tgUser.username ? ('@' + tgUser.username) : (((tgUser.first_name || '') + ' ' + (tgUser.last_name || '')).trim() || 'VIP FOYDALANUVCHI');
        }
    } catch (e) {
        console.warn('Hydration error:', e);
    }
}

// Lite Mode (Low Motion & High Efficiency without freezing images)
function isAnimationsDisabled() {
    return localStorage.getItem('coinstat_disable_animations') === 'true';
}

function initAnimationsSetting() {
    if (isAnimationsDisabled()) {
        document.documentElement.classList.add('lite-mode');
        if (document.body) document.body.classList.add('lite-mode');
    } else {
        document.documentElement.classList.remove('lite-mode');
        if (document.body) document.body.classList.remove('lite-mode');
    }
}

function toggleAnimations(disable) {
    if (typeof disable === 'undefined') {
        disable = !isAnimationsDisabled();
    }
    localStorage.setItem('coinstat_disable_animations', disable ? 'true' : 'false');
    initAnimationsSetting();
    return disable;
}

// Immediate execution of hydration & animation settings
initAnimationsSetting();
hydrateInstantUserData();

document.addEventListener('DOMContentLoaded', function () {
    hydrateInstantUserData();
    initAnimationsSetting();
    initTheme();
    fillUsernameFromTelegram();
    setupUserProfileHeader();
    loadUserBalance();
    applyTranslations();
    hideLoader();
    initInstantNavigation();
    initHaptics();
    initChannelSubscriptionGate();

    // Battery-friendly balance auto-sync (every 10 seconds, only when tab is visible)
    setInterval(() => {
        if (!document.hidden) {
            loadUserBalance();
        }
    }, 10000);

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            loadUserBalance();
            if (typeof checkSubscriptionGateAuto === 'function') {
                checkSubscriptionGateAuto();
            }
        }
    });
});

// Instant Page Navigation & Cache Accelerator
function initInstantNavigation() {
    const pagesToPrefetch = [
        'index.html',
        'gift.html',
        'rating.html',
        'profile.html',
        'stars.html',
        'premium.html',
        'spin.html',
        'topup.html',
        'phone.html',
        'orders.html'
    ];

    const prefetchPages = () => {
        pagesToPrefetch.forEach(page => {
            const link = document.createElement('link');
            link.rel = 'prefetch';
            link.as = 'document';
            link.href = page;
            document.head.appendChild(link);
        });
    };

    if (window.requestIdleCallback) {
        requestIdleCallback(prefetchPages);
    } else {
        setTimeout(prefetchPages, 200);
    }

    // Bulletproof click navigation for bottom dock navigation tabs and FAB
    document.addEventListener('click', function(e) {
        const tabBtn = e.target.closest('.dock-tab-btn, .dock-fab-btn');
        if (tabBtn) {
            const href = tabBtn.getAttribute('href');
            if (href && href !== '#' && !href.startsWith('javascript:')) {
                const current = (window.location.pathname || '').split('/').pop() || 'index.html';
                if (current !== href) {
                    e.preventDefault();
                    document.querySelectorAll('.dock-tab-btn, .dock-fab-btn').forEach(b => b.classList.remove('active'));
                    tabBtn.classList.add('active');
                    triggerHaptic('medium');
                    window.location.href = href;
                }
            }
        }
    });

    // Delegated click navigation for service cards, banners and stat boxes
    document.addEventListener('click', function(e) {
        const card = e.target.closest('.service-quad-card, .vip-spin-banner, .stat-card-box');
        if (card) {
            const oc = card.getAttribute('onclick');
            if (oc && oc.includes('window.location.href')) {
                const match = oc.match(/window\.location\.href\s*=\s*['"]([^'"]+)['"]/);
                if (match && match[1]) {
                    e.preventDefault();
                    triggerHaptic('light');
                    window.location.href = match[1];
                }
            }
        }
    });
}

function initTheme() {
    const savedTheme = localStorage.getItem('starpay_theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
    } else {
        document.body.classList.remove('light-theme');
    }
}

function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');
    localStorage.setItem('starpay_theme', isLight ? 'light' : 'dark');
}

function setupUserProfileHeader() {
    hydrateInstantUserData();
}

function updateStarsEquivalent(bal) {
    const starsEl = document.getElementById('starsEquivalent') || document.getElementById('approxStars');
    if (starsEl) {
        const starsEquiv = Math.floor((bal || 0) / 200);
        starsEl.textContent = starsEquiv.toLocaleString('uz-UZ');
    }
    const approxEl = document.getElementById('approxStars');
    if (approxEl) {
        const starsEquiv = Math.floor((bal || 0) / 200);
        approxEl.textContent = starsEquiv.toLocaleString('uz-UZ');
    }
}

function fillUsernameFromTelegram() {
    const input = document.getElementById('username');
    const user = tg.initDataUnsafe?.user;
    if (input && user?.username && !input.value.trim()) {
        input.value = '@' + user.username;
    }
}

function getUserId() {
    // 1. Check URL parameters from Telegram WebApp button
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const uidParam = urlParams.get('uid') || urlParams.get('user_id');
        if (uidParam && !isNaN(parseInt(uidParam, 10))) {
            const uid = parseInt(uidParam, 10);
            try { localStorage.setItem('starpay_user_id', String(uid)); } catch(e) {}
            return uid;
        }
    } catch(e) {}

    // 2. Official source: Telegram WebApp initDataUnsafe
    if (tg.initDataUnsafe?.user?.id) {
        const uid = tg.initDataUnsafe.user.id;
        try { localStorage.setItem('starpay_user_id', String(uid)); } catch(e) {}
        return uid;
    }

    // 3. Parse from Telegram initData signed string
    if (tg.initData) {
        try {
            const parsedParams = new URLSearchParams(tg.initData);
            const userStr = parsedParams.get('user');
            if (userStr) {
                const userObj = JSON.parse(userStr);
                if (userObj && userObj.id) {
                    const uid = userObj.id;
                    try { localStorage.setItem('starpay_user_id', String(uid)); } catch(e) {}
                    return uid;
                }
            }
        } catch(e) {}
    }

    try {
        const cached = localStorage.getItem('starpay_user_id');
        if (cached) return parseInt(cached, 10);
    } catch(e) {}

    return null;
}

let _previousBalance = null;
let isBalanceHidden = localStorage.getItem('coinstat_hide_balance') === 'true';

function toggleBalanceVisibility() {
    isBalanceHidden = !isBalanceHidden;
    localStorage.setItem('coinstat_hide_balance', isBalanceHidden ? 'true' : 'false');
    if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
    setBalUI(userBalance);
}

function setBalUI(val) {
    const prev = userBalance;
    userBalance = Number(val) || 0;
    const isHidden = localStorage.getItem('coinstat_hide_balance') === 'true';
    const formatted = isHidden ? '••••••' : userBalance.toLocaleString('uz-UZ');

    const eyeSvg = document.getElementById('eyeIconSvg');
    if (eyeSvg) {
        if (isHidden) {
            eyeSvg.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>';
        } else {
            eyeSvg.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>';
        }
    }

    // Update all balance elements across views (Home card, Profile card, live badges)
    document.querySelectorAll('#balance, [id="balance"], .user-balance-val, .live-user-balance, #profileBalance, #userBalanceStat, #servicesBalance').forEach(el => {
        if (el.id === 'balance' && _previousBalance !== null && _previousBalance !== userBalance) {
            el.classList.remove('balance-num-updated');
            void el.offsetWidth;
            el.classList.add('balance-num-updated');
        }
        el.textContent = formatted;
    });

    updateStarsEquivalent(userBalance);
    _previousBalance = userBalance;
}

function loadUserBalance() {
    const userId = getUserId();
    if (!userId) {
        setBalUI(0);
        return;
    }

    // 1. Immediately read from URL if present
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const urlBal = urlParams.get('bal') || urlParams.get('balance');
        if (urlBal !== null && !isNaN(parseInt(urlBal, 10))) {
            const numBal = parseInt(urlBal, 10);
            setBalUI(numBal);
            try { localStorage.setItem('starpay_balance_' + userId, String(numBal)); } catch(e) {}
        } else {
            // 2. Read from localStorage cache
            const cachedBal = localStorage.getItem('starpay_balance_' + userId);
            if (cachedBal !== null && !isNaN(parseInt(cachedBal, 10))) {
                setBalUI(parseInt(cachedBal, 10));
            }
        }
    } catch(e) {}

    // 3. Query API for live balance update
    const apiBase = getApiBase();
    const fetchBalance = (url) => {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': tg.initData || '',
            },
            body: JSON.stringify({ telegram_id: userId, initData: tg.initData || '' }),
        }).then(r => {
            if (!r.ok) throw new Error('API status ' + r.status);
            return r.json();
        });
    };

    fetchBalance((apiBase ? apiBase : '') + '/api/user/balance?t=' + Date.now())
    .then(data => {
        if (data && data.ok && typeof data.balance === 'number') {
            const newBal = Number(data.balance);
            setBalUI(newBal);
            try { 
                localStorage.setItem('starpay_balance_' + userId, String(newBal)); 
                localStorage.setItem('cs_cached_balance', String(newBal));
            } catch(e) {}
        }
    })
    .catch(() => {});
}


function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

function getUsername(inputId) {
    const val = (document.getElementById(inputId || 'username')?.value || '').trim();
    if (!val || val === '@') return null;
    return val.startsWith('@') ? val : '@' + val;
}

function setBuyButtonLoading(btnId, loading) {
    const btn = document.getElementById(btnId || 'buyBtn');
    if (!btn) return;
    if (loading) {
        btn.dataset.originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = t('common.sending');
    } else {
        btn.disabled = false;
        btn.textContent = btn.dataset.originalText || t('common.buy');
    }
}

/**
 * Submit order via HTTP POST to the API server.
 * Works with both inline and reply keyboard WebApp buttons.
 *
 * payload fields:
 *   action: 'buy_stars' | 'buy_premium' | 'buy_gift' | 'buy_phone'
 *   + action-specific fields (amount, username, duration, etc.)
 */
async function submitOrder(payload, btnId) {
    setBuyButtonLoading(btnId, true);

    // Map action → API endpoint
    const endpoints = {
        buy_stars:   '/api/order/stars',
        buy_premium: '/api/order/premium',
        buy_gift:    '/api/order/gift',
        buy_phone:   '/api/order/phone',
    };

    const endpoint = endpoints[payload.action];
    if (!endpoint) {
        setBuyButtonLoading(btnId, false);
        tg.showAlert(t('common.unknown_order'));
        return;
    }

    // Build request body — rename fields to what the API expects
    const body = { ...payload };
    if (payload.action === 'buy_stars') {
        body.quantity = payload.amount;
    }
    if (payload.action === 'buy_premium') {
        body.months = payload.duration;
    }

    // Pass Telegram initData for auth
    body.initData = tg.initData || '';
    body.telegram_id = tg.initDataUnsafe?.user?.id || null;

    try {
        const response = await fetch(getApiBase() + endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': tg.initData || '',
                'Bypass-Tunnel-Reminder': 'true',
            },
            body: JSON.stringify(body),
        });

        const result = await response.json();

        if (result.ok) {
            const successMessages = {
                buy_stars:   t('success.stars'),
                buy_premium: t('success.premium'),
                buy_gift:    t('success.gift'),
                buy_phone:   t('success.phone'),
            };
            tg.showPopup({
                title: t('success.title'),
                message: successMessages[payload.action] || t('success.order_done'),
                buttons: [{ type: 'ok' }]
            }, () => tg.close());
        } else {
            setBuyButtonLoading(btnId, false);
            tg.showPopup({
                title: t('error.title'),
                message: result.error || t('error.retry'),
                buttons: [{ type: 'close' }]
            });
        }
    } catch (e) {
        setBuyButtonLoading(btnId, false);
        tg.showPopup({
            title: t('error.network_title'),
            message: e.message || t('error.network'),
            buttons: [{ type: 'close' }]
        });
    }
}

function setupPurchaseButton(onClick, text) {
    const label = text || t('common.buy');
    const btn = document.getElementById('buyBtn');
    if (!btn) return;

    btn.disabled = false;
    btn.textContent = label;
    btn.onclick = onClick;

    if (tg.MainButton) {
        tg.MainButton.hide();
    }
}

// ===== LOADER =====
function showLoader(text) {
  const overlay = document.getElementById('loaderOverlay');
  if (!overlay) return;
  const sub = overlay.querySelector('.loader-sub');
  if (sub && text) sub.textContent = text;
  overlay.classList.remove('hidden');
}

function hideLoader() {
  const overlay = document.getElementById('loaderOverlay');
  if (overlay) overlay.classList.add('hidden');
  const splash = document.getElementById('appSplashScreen');
  if (splash) {
    splash.style.opacity = '0';
    splash.style.pointerEvents = 'none';
    setTimeout(() => {
        splash.style.display = 'none';
    }, 80);
  }
}

function validateStarsAmount(amount) {
    const n = parseInt(amount, 10);
    if (isNaN(n) || n < STARS_MIN) {
        return { ok: false, message: `${t('validate.min_stars')}`.replace('{min}', STARS_MIN) };
    }
    if (n > STARS_MAX) {
        return { ok: false, message: `${t('validate.max_stars')}`.replace('{max}', STARS_MAX.toLocaleString('uz-UZ')) };
    }
    return { ok: true, value: n };
}

// ===== i18n Translations =====
const LANGUAGES = {
    uz: { name: "O'zbek", nativeName: "O'zbekcha", code: "uz" },
    ru: { name: "Русский", nativeName: "Русский", code: "ru" },
    en: { name: "English", nativeName: "English", code: "en" },
};

const TRANSLATIONS = {
    uz: {
        'nav.home': 'Asosiy',
        'nav.gifts': 'Gift',
        'nav.rating': 'Top',
        'nav.profile': 'Profil',
        'nav.menu': 'Menu',

        'home.balance_title': 'BALANS',
        'home.topup': 'To\'ldirish',
        'home.orders': 'Buyurtmalar',
        'home.spent': 'Sarflangan',
        'home.balance_stat': 'Balans',
        'home.lucky_spin': 'Lucky Spin',
        'home.promo_code': 'PROMO KOD',
        'home.spin_subtext': 'Promo-kod orqali bepul Telegram sovg\'alarini yuting!',
        'home.service_stars': 'Stars',
        'home.service_premium': 'Premium',
        'home.service_gifts': 'Sovg\'alar',
        'home.service_phone': 'Virtual Nomer',
        'home.badge_discount': '-10% Chegirma',
        'home.desc_stars': 'Eng tezkor yetkazish',
        'home.badge_premium': '3 / 6 / 12 oy',
        'home.desc_premium': 'Rasmiy obuna',
        'home.badge_gifts': 'Jonli Gifts',
        'home.desc_gifts': 'Teddy, Rose & Box',
        'home.badge_phone': 'SMS Tasdiq',
        'home.desc_phone': 'Telegram faollashtirish',
        'home.active_account': 'Faol hisob',
        'home.cashback': 'Keshbek',
        'home.spin_free_badge': '1 TA BEPUL',
        'common.unit_count': 'ta',

        'gift.header_title': 'Telegram Sovg\'alari',
        'gift.header_subtitle': 'O\'zingiz yoki do\'stlaringiz uchun original Telegram sovg\'alarini xarid qiling!',
        'gift.cat_all': 'Barchasi (19)',
        'gift.cat_vip': 'VIP (10)',
        'gift.cat_classic': 'Klassik (3)',
        'gift.cat_deluxe': 'Hashamatli (7)',
        'gift.modal_for_self': 'O\'zimga',
        'gift.modal_for_friend': 'Do\'stimga',
        'gift.modal_buy_btn': 'Sovg\'ani Xarid Qilish',
        'gift.modal_cancel': 'Bekor qilish',
        'gift.win_title': 'XARID MUBORAK!',
        'gift.win_claim': 'Sovg\'ani Qabul Qilish',
        'gift.win_close': 'Yopish',
        'gift.balance_label': 'Balans:',

        'topup.header_title': 'Balans To\'ldirish',
        'topup.step1_sub': '1-qadam: Kerakli to\'lov summasini tanlang',
        'topup.step2_sub': '2-qadam: Kartaga to\'lov qiling',
        'topup.select_amount_title': 'Summani tanlang',
        'topup.custom_placeholder': 'Boshqa summa kiriting...',
        'topup.proceed_btn': 'To\'lovga o\'tish',
        'topup.timer_label': 'To\'lov uchun berilgan vaqt:',
        'topup.timer_hint': '5 daqiqa ichida to\'lang',
        'topup.pay_amount_label': 'To\'lanadigan summa:',
        'topup.card_label': 'Karta raqami (Nusxalash uchun bosing)',
        'topup.receiver_label': 'Qabul qiluvchi',
        'topup.copy_btn': 'Nusxalash',
        'topup.copied_toast': 'Karta raqami nusxalandi!',
        'topup.warning_notice': 'Iltimos, 5 daqiqa ichida ko\'rsatilgan kartaga aniq to\'lovni o\'tkazing va quyidagi tugmani bosing.',
        'topup.submit_btn': 'To\'lovni amalga oshirdim',
        'topup.change_amount_btn': 'Summani o\'zgartirish',
        'topup.help_title': 'Yordam kerakmi?',
        'topup.help_text': 'To\'lov qilishda qiyinchilik bo\'lsa yoki savollaringiz bo\'lsa, adminga yozing:',
        'topup.admin_btn': 'Adminga murojaat qilish',

        'rating.title': 'Savdo Statistikasi',
        'rating.subtitle': 'Eng yaxshi sotuvchilar reytingi',
        'rating.tab.today': 'Bugun',
        'rating.tab.week': 'Shu Hafta',
        'rating.tab.month': 'Shu Oy',
        'rating.tab.all': 'Barcha Vaqt',
        'rating.loading': 'Yuklanmoqda...',
        'rating.empty': 'Hozircha ma\'lumot yo\'q',
        'rating.error': 'Yuklashda xatolik yuz berdi',

        'profile.section.main': 'ASOSIY',
        'profile.topup_title': 'Balans To\'ldirish',
        'profile.topup_sub': 'Hisobni to\'ldirish va xarid qilish',
        'profile.orders_title': 'Buyurtmalarim',
        'profile.orders_sub': 'Xaridlar va to\'lovlar tarixi',
        'profile.rating_title': 'Savdo Reytingi',
        'profile.rating_sub': 'Eng faol foydalanuvchilar ro\'yxati',
        'profile.gifts': 'Giftlarim',
        'profile.referrals': 'Takliflarim',
        'profile.section.transactions': 'TRANZAKSIYALAR',
        'profile.section.settings': 'SOZLAMALAR',
        'profile.lite_mode': 'Tezkor Rejim (Lite Mode)',
        'profile.lite_sub': 'Animatsiyalarni o\'chirib, tezlikni oshirish',
        'profile.support': 'Qo\'llab-quvvatlash',
        'profile.support_sub': 'Admin va yordam markazi',
        'profile.news_channel': 'Yangiliklar kanali',
        'profile.news': 'Yangiliklar va E\'lonlar',
        'profile.news_sub': 'Rasmiy telegram kanalimiz: @CoinStatUz',
        'profile.konkurs': 'Konkurs bo\'limi',
        'profile.konkurs_badge': 'FAOL',
        'profile.konkurs_sub': 'Aksiya va yutuqli konkurslarda qatnashish',

        'stars.title': 'Telegram Stars sotib olish',
        'stars.amount': 'Stars miqdori',
        'stars.custom_title': 'Boshqa miqdor',
        'stars.custom_sub': 'Ixtiyoriy miqdorni kiriting (min 50)',
        'stars.recipient_for_me': 'O\'zimga',
        'premium.title': 'Telegram Premium sotib olish',
        'premium.3_months': '3 Oylik Premium',
        'premium.6_months': '6 Oylik Premium',
        'premium.12_months': '12 Oylik Premium',
        'spin.title': 'Lucky Spin — Omadli G\'ildirak',

        'common.loading': 'Yuklanmoqda...',
        'common.sending': 'Yuborilmoqda...',
        'common.buy': 'Sotib olish',
        'common.unit_som': 'so\'m',
        'success.title': '✅ Muvaffaqiyatli',
        'error.title': '❌ Xatolik',
    },
    ru: {
        'nav.home': 'Главная',
        'nav.gifts': 'Gift',
        'nav.rating': 'Топ',
        'nav.profile': 'Профиль',
        'nav.menu': 'Меню',

        'home.balance_title': 'БАЛАНС',
        'home.topup': 'Пополнить',
        'home.orders': 'Заказы',
        'home.spent': 'Потрачено',
        'home.balance_stat': 'Баланс',
        'home.lucky_spin': 'Lucky Spin',
        'home.promo_code': 'ПРОМОКОД',
        'home.spin_subtext': 'Выигрывайте подарки Telegram по промокоду!',
        'home.service_stars': 'Stars',
        'home.service_premium': 'Premium',
        'home.service_gifts': 'Подарки',
        'home.service_phone': 'Виртуальный номер',
        'home.badge_discount': '-10% Скидка',
        'home.desc_stars': 'Быстрая доставка',
        'home.badge_premium': '3 / 6 / 12 мес',
        'home.desc_premium': 'Официальная подписка',
        'home.badge_gifts': 'Telegram Gifts',
        'home.desc_gifts': 'Teddy, Rose & Box',
        'home.badge_phone': 'SMS Активация',
        'home.desc_phone': 'Активация Telegram',
        'home.active_account': 'Активный аккаунт',
        'home.cashback': 'Кэшбэк',
        'home.spin_free_badge': '1 БЕСПЛАТНО',
        'common.unit_count': 'шт',

        'gift.header_title': 'Telegram Подарки',
        'gift.header_subtitle': 'Купите оригинальные подарки Telegram для себя или друзей!',
        'gift.cat_all': 'Все (19)',
        'gift.cat_vip': 'VIP (10)',
        'gift.cat_classic': 'Классика (3)',
        'gift.cat_deluxe': 'Премиум (7)',
        'gift.modal_for_self': 'Себе',
        'gift.modal_for_friend': 'Другу',
        'gift.modal_buy_btn': 'Купить подарок',
        'gift.modal_cancel': 'Отмена',
        'gift.win_title': 'ПОЗДРАВЛЯЕМ!',
        'gift.win_claim': 'Получить подарок',
        'gift.win_close': 'Закрыть',
        'gift.balance_label': 'Баланс:',

        'topup.header_title': 'Пополнение Баланса',
        'topup.step1_sub': 'Шаг 1: Выберите сумму пополнения',
        'topup.step2_sub': 'Шаг 2: Оплатите на карту',
        'topup.select_amount_title': 'Выберите сумму',
        'topup.custom_placeholder': 'Введите другую сумму...',
        'topup.proceed_btn': 'Перейти к оплате',
        'topup.timer_label': 'Время на оплату:',
        'topup.timer_hint': 'Оплатите в течение 5 минут',
        'topup.pay_amount_label': 'Сумма к оплате:',
        'topup.card_label': 'Номер карты (Нажмите для копирования)',
        'topup.receiver_label': 'Получатель',
        'topup.copy_btn': 'Скопировать',
        'topup.copied_toast': 'Номер карты скопирован!',
        'topup.warning_notice': 'Пожалуйста, в течение 5 минут переведите точную сумму на карту и нажмите кнопку ниже.',
        'topup.submit_btn': 'Я оплатил',
        'topup.change_amount_btn': 'Изменить сумму',
        'topup.help_title': 'Нужна помощь?',
        'topup.help_text': 'Если у вас возникли сложности с оплатой, напишите администратору:',
        'topup.admin_btn': 'Связаться с админом',

        'rating.title': 'Статистика Продаж',
        'rating.subtitle': 'Рейтинг лучших продавцов',
        'rating.tab.today': 'Сегодня',
        'rating.tab.week': 'На этой неделе',
        'rating.tab.month': 'В этом месяце',
        'rating.tab.all': 'За всё время',
        'rating.loading': 'Загрузка...',
        'rating.empty': 'Нет данных',
        'rating.error': 'Ошибка загрузки',

        'profile.section.main': 'ОСНОВНОЕ',
        'profile.topup_title': 'Пополнение Баланса',
        'profile.topup_sub': 'Пополнить счет для покупок',
        'profile.orders_title': 'Мои Заказы',
        'profile.orders_sub': 'История покупок и платежей',
        'profile.rating_title': 'Рейтинг Продаж',
        'profile.rating_sub': 'Список лучших пользователей',
        'profile.gifts': 'Мои подарки',
        'profile.referrals': 'Мои приглашения',
        'profile.section.transactions': 'ТРАНЗАКЦИИ',
        'profile.section.settings': 'НАСТРОЙКИ',
        'profile.lite_mode': 'Быстрый режим (Lite Mode)',
        'profile.lite_sub': 'Отключить анимации для ускорения',
        'profile.support': 'Поддержка',
        'profile.support_sub': 'Администратор и помощь',
        'profile.news_channel': 'Новостной канал',
        'profile.news': 'Новости и Объявления',
        'profile.news_sub': 'Официальный telegram-канал: @CoinStatUz',
        'profile.konkurs': 'Раздел конкурсов',
        'profile.konkurs_badge': 'АКТИВЕН',
        'profile.konkurs_sub': 'Участие в акциях и конкурсах',

        'stars.title': 'Купить Telegram Stars',
        'stars.amount': 'Количество Stars',
        'stars.custom_title': 'Другое количество',
        'stars.custom_sub': 'Введите любое количество (мин. 50)',
        'stars.recipient_for_me': 'Себе',
        'premium.title': 'Купить Telegram Premium',
        'premium.3_months': 'Premium на 3 Месяца',
        'premium.6_months': 'Premium на 6 Месяцев',
        'premium.12_months': 'Premium на 12 Месяцев',
        'spin.title': 'Lucky Spin — Колесо Удачи',

        'common.loading': 'Загрузка...',
        'common.sending': 'Отправка...',
        'common.buy': 'Купить',
        'common.unit_som': 'сум',
        'success.title': '✅ Успешно',
        'error.title': '❌ Ошибка',
    },
    en: {
        'nav.home': 'Home',
        'nav.gifts': 'Gifts',
        'nav.rating': 'Top',
        'nav.profile': 'Profile',
        'nav.menu': 'Menu',

        'home.balance_title': 'BALANCE',
        'home.topup': 'Top Up',
        'home.orders': 'Orders',
        'home.spent': 'Spent',
        'home.balance_stat': 'Balance',
        'home.lucky_spin': 'Lucky Spin',
        'home.promo_code': 'PROMO CODE',
        'home.spin_subtext': 'Win free Telegram gifts with promo codes!',
        'home.service_stars': 'Stars',
        'home.service_premium': 'Premium',
        'home.service_gifts': 'Gifts',
        'home.service_phone': 'Virtual Number',
        'home.badge_discount': '-10% Discount',
        'home.desc_stars': 'Instant Delivery',
        'home.badge_premium': '3 / 6 / 12 mo',
        'home.desc_premium': 'Official Subscription',
        'home.badge_gifts': 'Telegram Gifts',
        'home.desc_gifts': 'Teddy, Rose & Box',
        'home.badge_phone': 'SMS Verify',
        'home.desc_phone': 'Telegram Activation',
        'home.active_account': 'Active Account',
        'home.cashback': 'Cashback',
        'home.spin_free_badge': '1 FREE SPIN',
        'common.unit_count': 'pcs',

        'gift.header_title': 'Telegram Gifts',
        'gift.header_subtitle': 'Purchase authentic Telegram gifts for yourself or friends!',
        'gift.cat_all': 'All (19)',
        'gift.cat_vip': 'VIP (10)',
        'gift.cat_classic': 'Classic (3)',
        'gift.cat_deluxe': 'Deluxe (7)',
        'gift.modal_for_self': 'For Myself',
        'gift.modal_for_friend': 'For a Friend',
        'gift.modal_buy_btn': 'Buy Gift',
        'gift.modal_cancel': 'Cancel',
        'gift.win_title': 'CONGRATULATIONS!',
        'gift.win_claim': 'Claim Gift',
        'gift.win_close': 'Close',
        'gift.balance_label': 'Balance:',

        'topup.header_title': 'Balance Top Up',
        'topup.step1_sub': 'Step 1: Select top-up amount',
        'topup.step2_sub': 'Step 2: Pay to card',
        'topup.select_amount_title': 'Select Amount',
        'topup.custom_placeholder': 'Enter custom amount...',
        'topup.proceed_btn': 'Proceed to Payment',
        'topup.timer_label': 'Payment time remaining:',
        'topup.timer_hint': 'Pay within 5 minutes',
        'topup.pay_amount_label': 'Amount to pay:',
        'topup.card_label': 'Card Number (Tap to copy)',
        'topup.receiver_label': 'Receiver',
        'topup.copy_btn': 'Copy',
        'topup.copied_toast': 'Card number copied!',
        'topup.warning_notice': 'Please transfer the exact amount to the card within 5 minutes and click the button below.',
        'topup.submit_btn': 'I Have Paid',
        'topup.change_amount_btn': 'Change Amount',
        'topup.help_title': 'Need Help?',
        'topup.help_text': 'If you have any issues with payment, contact our admin:',
        'topup.admin_btn': 'Contact Admin',

        'rating.title': 'Sales Leaderboard',
        'rating.subtitle': 'Ranking of top sellers',
        'rating.tab.today': 'Today',
        'rating.tab.week': 'This Week',
        'rating.tab.month': 'This Month',
        'rating.tab.all': 'All Time',
        'rating.loading': 'Loading...',
        'rating.empty': 'No data available',
        'rating.error': 'Failed to load',

        'profile.section.main': 'MAIN',
        'profile.topup_title': 'Top Up Balance',
        'profile.topup_sub': 'Add funds to balance and purchase',
        'profile.orders_title': 'My Orders',
        'profile.orders_sub': 'Purchases and payments history',
        'profile.rating_title': 'Sales Leaderboard',
        'profile.rating_sub': 'Top active users ranking',
        'profile.gifts': 'My Gifts',
        'profile.referrals': 'My Referrals',
        'profile.section.transactions': 'TRANSACTIONS',
        'profile.section.settings': 'SETTINGS',
        'profile.lite_mode': 'Lite Mode (Ultra Fast)',
        'profile.lite_sub': 'Disable animations for maximum speed',
        'profile.support': 'Support',
        'profile.support_sub': 'Admin and help center',
        'profile.news_channel': 'News Channel',
        'profile.news': 'News & Announcements',
        'profile.news_sub': 'Official telegram channel: @CoinStatUz',
        'profile.konkurs': 'Contests Section',
        'profile.konkurs_badge': 'ACTIVE',
        'profile.konkurs_sub': 'Participate in prize draws and promos',

        'stars.title': 'Buy Telegram Stars',
        'stars.amount': 'Stars Amount',
        'stars.custom_title': 'Custom Amount',
        'stars.custom_sub': 'Enter any amount (min 50)',
        'stars.recipient_for_me': 'For Myself',
        'premium.title': 'Buy Telegram Premium',
        'premium.3_months': '3 Months Premium',
        'premium.6_months': '6 Months Premium',
        'premium.12_months': '12 Months Premium',
        'spin.title': 'Lucky Spin — Lucky Wheel',

        'common.loading': 'Loading...',
        'common.sending': 'Sending...',
        'common.buy': 'Buy',
        'common.unit_som': 'UZS',
        'success.title': '✅ Success',
        'error.title': '❌ Error',
    }
};

let currentLang = 'uz';

function detectLanguage() {
    const saved = localStorage.getItem('starpay_lang');
    if (saved && TRANSLATIONS[saved]) return saved;
    const tgLang = (tg && tg.initDataUnsafe?.user?.language_code) || '';
    if (tgLang.startsWith('ru')) return 'ru';
    if (tgLang.startsWith('en')) return 'en';
    return 'uz';
}

function t(key) {
    return TRANSLATIONS[currentLang]?.[key] || TRANSLATIONS['uz']?.[key] || key;
}

function setLanguage(lang) {
    if (!TRANSLATIONS[lang]) return;
    currentLang = lang;
    localStorage.setItem('starpay_lang', lang);
    document.documentElement.lang = lang;
    applyTranslations();
}

function applyTranslations() {
    const langBtns = document.querySelectorAll('#langBtn, .lang-badge-pill');
    langBtns.forEach(btn => {
        btn.textContent = currentLang.toUpperCase();
    });

    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        let text = t(key);
        const args = el.getAttribute('data-i18n-args');
        if (args) {
            try {
                const parsed = JSON.parse(args);
                for (const [k, v] of Object.entries(parsed)) {
                    text = text.replace('{' + k + '}', String(v));
                }
            } catch (e) {}
        }
        el.textContent = text;
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        el.title = t(key);
    });

    if (typeof renderGifts === 'function') {
        renderGifts();
    }
}

function toggleLanguage() {
    const langs = ['uz', 'ru', 'en'];
    const idx = langs.indexOf(currentLang);
    const next = langs[(idx + 1) % langs.length];
    setLanguage(next);
    if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
}

currentLang = detectLanguage();
document.documentElement.lang = currentLang;

function openTransactionsModal() {
    const modal = document.getElementById('transactionsModalOverlay');
    if (modal) {
        modal.classList.add('open');
        if (typeof fetchModalTransactions === 'function') {
            fetchModalTransactions();
        }
    }
}

function openOrders() {
    openTransactionsModal();
}

/* =========================================
   Bottom Dock Fast Capsule Navigation
   ========================================= */
function initDockNavigation() {
    const dock = document.querySelector('.bottom-dock-nav');
    if (!dock) return;

    const tabs = Array.from(dock.querySelectorAll('.dock-tab-btn'));
    if (!tabs.length) return;

    // Detect current page filename from URL accurately (ignoring query/hashes/trailing slash)
    let currentPath = (window.location.pathname.split('/').filter(Boolean).pop() || 'index.html').toLowerCase();
    if (!currentPath.endsWith('.html')) {
        currentPath = currentPath ? (currentPath + '.html') : 'index.html';
    }

    let activeIdx = tabs.findIndex(t => {
        const href = (t.getAttribute('href') || '').toLowerCase();
        return href.includes(currentPath);
    });

    if (activeIdx !== -1) {
        tabs.forEach((t, i) => {
            if (i === activeIdx) {
                t.classList.add('active');
            } else {
                t.classList.remove('active');
            }
        });
    }

    // Handle tab clicks with instant feedback & haptic
    tabs.forEach((tab) => {
        tab.addEventListener('click', function(e) {
            if (tab.classList.contains('active')) {
                e.preventDefault();
                return;
            }

            // Haptic Feedback
            try {
                if (window.Telegram?.WebApp?.HapticFeedback) {
                    window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
                }
            } catch(err) {}

            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
        });
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        initDockNavigation();
        initSplashScreen();
    });
} else {
    initDockNavigation();
    initSplashScreen();
}

/* =========================================
   App Launch Splash Loading Screen (Disabled on tab navigation)
   ========================================= */
function initSplashScreen() {
    const splash = document.getElementById('appSplashScreen');
    if (splash) {
        splash.remove();
    }
    const loader = document.getElementById('loaderOverlay');
    if (loader) {
        loader.remove();
    }
}

/* =========================================
   Telegram Channel Subscription Gate Module
   Blocks users who are not subscribed or leave the channel
   ========================================= */

let _csSubscribed = null;
let _csRequiredChannel = '@CoinStatUz';
let _csRequiredChannelUrl = 'https://t.me/CoinStatUz';
let _csCheckingSub = false;

function injectChannelGateStyles() {
    if (document.getElementById('cs-sub-gate-styles')) return;
    const style = document.createElement('style');
    style.id = 'cs-sub-gate-styles';
    style.textContent = `
        .cs-sub-gate-overlay {
            position: fixed;
            inset: 0;
            background: rgba(8, 9, 14, 0.96);
            backdrop-filter: blur(22px);
            -webkit-backdrop-filter: blur(22px);
            z-index: 9999999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 18px;
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            transition: opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1), visibility 0.3s ease;
        }
        .cs-sub-gate-overlay.active {
            opacity: 1;
            visibility: visible;
            pointer-events: auto;
        }
        .cs-sub-gate-card {
            background: linear-gradient(180deg, #181926 0%, #0d0e16 100%);
            border: 1.5px solid rgba(251, 191, 36, 0.5);
            border-radius: 30px;
            padding: 32px 22px 24px;
            max-width: 360px;
            width: 100%;
            text-align: center;
            box-shadow: 0 25px 70px rgba(0, 0, 0, 0.85), 0 0 50px rgba(251, 191, 36, 0.22);
            transform: scale(0.88);
            transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            overflow: hidden;
            box-sizing: border-box;
        }
        .cs-sub-gate-overlay.active .cs-sub-gate-card {
            transform: scale(1);
        }
        .cs-sub-gate-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 50%;
            transform: translateX(-50%);
            width: 220px;
            height: 120px;
            background: radial-gradient(ellipse at top, rgba(251, 191, 36, 0.25) 0%, transparent 70%);
            pointer-events: none;
        }
        .cs-sub-icon-wrap {
            width: 78px;
            height: 78px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(251, 191, 36, 0.2) 0%, rgba(251, 191, 36, 0.05) 70%);
            border: 1.5px solid rgba(251, 191, 36, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 38px;
            margin: 0 auto 16px;
            box-shadow: 0 0 30px rgba(251, 191, 36, 0.3);
            animation: csSubPulse 2.2s infinite ease-in-out;
        }
        @keyframes csSubPulse {
            0%, 100% { transform: scale(1); box-shadow: 0 0 25px rgba(251, 191, 36, 0.25); }
            50% { transform: scale(1.06); box-shadow: 0 0 40px rgba(251, 191, 36, 0.45); }
        }
        .cs-sub-title {
            font-size: 19px;
            font-weight: 900;
            color: #ffffff;
            margin-bottom: 8px;
            letter-spacing: -0.4px;
        }
        .cs-sub-desc {
            font-size: 13px;
            color: #94a3b8;
            line-height: 1.55;
            margin-bottom: 22px;
        }
        .cs-sub-channel-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(251, 191, 36, 0.12);
            border: 1px solid rgba(251, 191, 36, 0.3);
            color: #fbbf24;
            font-size: 12.5px;
            font-weight: 800;
            padding: 5px 14px;
            border-radius: 999px;
            margin-bottom: 18px;
        }
        .cs-sub-join-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            width: 100%;
            background: linear-gradient(135deg, #38bdf8 0%, #2563eb 100%);
            color: #ffffff;
            border: none;
            border-radius: 16px;
            padding: 14px;
            font-size: 14px;
            font-weight: 900;
            text-decoration: none;
            cursor: pointer;
            box-shadow: 0 8px 24px rgba(37, 99, 235, 0.45);
            transition: transform 0.15s ease;
            margin-bottom: 10px;
            box-sizing: border-box;
        }
        .cs-sub-join-btn:active {
            transform: scale(0.97);
        }
        .cs-sub-verify-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            width: 100%;
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 16px;
            padding: 13px;
            font-size: 13.5px;
            font-weight: 800;
            cursor: pointer;
            transition: all 0.2s ease;
            box-sizing: border-box;
        }
        .cs-sub-verify-btn:active {
            background: rgba(255, 255, 255, 0.16);
            transform: scale(0.98);
        }
        .cs-sub-msg {
            font-size: 12px;
            font-weight: 700;
            color: #f87171;
            margin-top: 12px;
            display: none;
            line-height: 1.4;
            animation: csSubShake 0.4s ease-in-out;
        }
        @keyframes csSubShake {
            0%, 100% { transform: translateX(0); }
            20%, 60% { transform: translateX(-6px); }
            40%, 80% { transform: translateX(6px); }
        }
    `;
    document.head.appendChild(style);
}

function injectChannelGateHTML() {
    if (document.getElementById('csSubGateOverlay')) return;
    const overlay = document.createElement('div');
    overlay.id = 'csSubGateOverlay';
    overlay.className = 'cs-sub-gate-overlay';
    overlay.innerHTML = `
        <div class="cs-sub-gate-card">
            <div class="cs-sub-icon-wrap">📢</div>
            <div class="cs-sub-title">Kanalimizga obuna bo'ling!</div>
            <div class="cs-sub-desc">
                CoinStat UZ xizmatlaridan foydalanish va xarid qilish uchun rasmiy kanalimizga a'zo bo'lishingiz shart.
            </div>
            <div class="cs-sub-channel-pill" id="csSubChannelPill">
                📢 @CoinStatUz
            </div>
            <button type="button" class="cs-sub-join-btn" onclick="openRequiredChannelLink()">
                🚀 Kanalga a'zo bo'lish
            </button>
            <button type="button" class="cs-sub-verify-btn" id="csSubVerifyBtn" onclick="verifySubscriptionManually()">
                ✅ A'zolikni tekshirish
            </button>
            <div class="cs-sub-msg" id="csSubMsg"></div>
        </div>
    `;
    document.body.appendChild(overlay);
}

function openRequiredChannelLink() {
    triggerHaptic('medium');
    const url = 'https://t.me/CoinStatUz';
    if (tg && typeof tg.openTelegramLink === 'function') {
        tg.openTelegramLink(url);
    } else {
        window.open(url, '_blank');
    }
}

async function verifySubscriptionManually() {
    const btn = document.getElementById('csSubVerifyBtn');
    const msg = document.getElementById('csSubMsg');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Tekshirilmoqda...';
    }
    if (msg) {
        msg.style.display = 'none';
        msg.textContent = '';
    }

    triggerHaptic('light');
    const isSub = await fetchSubscriptionStatus(true);

    if (btn) {
        btn.disabled = false;
        btn.textContent = "✅ A'zolikni tekshirish";
    }

    if (isSub) {
        triggerHaptic('success');
        closeSubscriptionGate();
    } else {
        triggerHaptic('error');
        if (msg) {
            msg.textContent = "❌ Siz hali kanalga a'zo bo'lmadingiz! Iltimos, yuqoridagi tugma orqali kanalga kiring va 'Qo'shilish' tugmasini bosing.";
            msg.style.display = 'block';
        }
    }
}

function closeSubscriptionGate() {
    const overlay = document.getElementById('csSubGateOverlay');
    if (overlay) {
        overlay.classList.remove('active');
    }
}

function showSubscriptionGate() {
    injectChannelGateStyles();
    injectChannelGateHTML();
    const overlay = document.getElementById('csSubGateOverlay');
    if (overlay) {
        overlay.classList.add('active');
    }
}

async function fetchSubscriptionStatus(force = false) {
    const userId = getUserId();
    if (!userId) {
        return true;
    }

    // Use short session cache (30s) unless forced
    const cacheKey = 'cs_sub_cache_' + userId;
    const now = Date.now();
    if (!force) {
        const cached = sessionStorage.getItem(cacheKey);
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                if (parsed.expires > now) {
                    _csSubscribed = parsed.subscribed;
                    return _csSubscribed;
                }
            } catch(e) {}
        }
    }

    if (_csCheckingSub) return _csSubscribed !== false;
    _csCheckingSub = true;

    try {
        const apiBase = (typeof getApiBase === 'function' ? getApiBase() : (window.API_BASE || '')) || '';
        const endpoint = apiBase.replace(/\/$/, '') + '/api/check-sub?telegram_id=' + userId;
        const res = await fetch(endpoint, {
            headers: {
                'X-Telegram-Init-Data': tg?.initData || '',
            }
        });
        const data = await res.json();
        _csCheckingSub = false;

        if (data && data.ok) {
            _csSubscribed = Boolean(data.subscribed);
            _csRequiredChannel = '@CoinStatUz';
            _csRequiredChannelUrl = 'https://t.me/CoinStatUz';

            const pill = document.getElementById('csSubChannelPill');
            if (pill) pill.textContent = '📢 @CoinStatUz';

            sessionStorage.setItem(cacheKey, JSON.stringify({
                subscribed: _csSubscribed,
                expires: now + (_csSubscribed ? 30000 : 5000)
            }));

            return _csSubscribed;
        }
    } catch(err) {
        _csCheckingSub = false;
    }

    return true; // fail-open for network errors so legitimate users aren't trapped if offline
}

async function checkSubscriptionGateAuto() {
    if (_csSubscribed === false) {
        // If user was blocked, re-verify on return from Telegram
        const isSub = await fetchSubscriptionStatus(true);
        if (isSub) {
            closeSubscriptionGate();
            triggerHaptic('success');
        }
    } else {
        const isSub = await fetchSubscriptionStatus(false);
        if (!isSub) {
            showSubscriptionGate();
        }
    }
}

function initChannelSubscriptionGate() {
    injectChannelGateStyles();
    injectChannelGateHTML();

    // Initial check
    setTimeout(async () => {
        const isSub = await fetchSubscriptionStatus(false);
        if (!isSub) {
            showSubscriptionGate();
        }
    }, 400);
}



function copyUserId() {
    const el = document.getElementById('profileHubUserId') || document.getElementById('profileUserId');
    if (!el) return;
    let txt = el.textContent.trim();
    if (txt.startsWith('ID:')) txt = txt.replace(/^ID:\s*/, '');
    if (txt.startsWith('@')) txt = txt.substring(1);
    if (!txt || txt === '—') return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(() => {
            if (window.Telegram?.WebApp?.HapticFeedback) {
                try { window.Telegram.WebApp.HapticFeedback.notificationOccurred('success'); } catch(e) {}
            }
            if (typeof showToast === 'function') showToast(t('common.copied') || 'Nusxa olindi!');
        }).catch(() => {});
    }
}
