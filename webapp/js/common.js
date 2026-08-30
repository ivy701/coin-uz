// StarPayUz - Common JavaScript Functions

const STARS_MIN = 50;
const STARS_MAX = 1000000;

const tg = window.Telegram?.WebApp || (typeof tg !== 'undefined' ? tg : null);
if (tg) {
    try {
        tg.expand();
        tg.ready();
        tg.setHeaderColor('#000000');
        tg.setBackgroundColor('#000000');
    } catch(e){}
}

let userBalance = 0;

// API base — can be overridden per-page via window.API_BASE
// e.g. in stars.html:    <script>window.API_BASE = 'https://web-production-49c65.up.railway.app';</script>
function getApiBase() {
    if (typeof window.API_BASE !== 'undefined' && window.API_BASE && window.API_BASE.trim() !== '') {
        return window.API_BASE.replace(/\/$/, '');
    }
    if (typeof window !== 'undefined' && window.location && window.location.protocol && window.location.protocol.startsWith('http')) {
        return window.location.origin;
    }
    return '';
}










// Initialize animation setting immediately & Auto-detect weak devices
initAnimationsSetting();

document.addEventListener('DOMContentLoaded', function () {
    initAnimationsSetting();
    initTheme();
    fillUsernameFromTelegram();
    setupUserProfileHeader();
    loadUserBalance();
    applyTranslations();
    hideLoader();
    initInstantNavigation();

    // Optimized battery-friendly balance auto-sync (every 8 seconds, only when tab is visible)
    setInterval(() => {
        if (!document.hidden) {
            loadUserBalance();
        }
    }, 8000);

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) loadUserBalance();
    });
});

// Instant Page Navigation & Cache Accelerator (0ms Switching)
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
        setTimeout(prefetchPages, 300);
    }

    const handleFastInteraction = (e) => {
        const target = e.target.closest('a') || e.target.closest('.dock-tab-btn') || e.target.closest('.service-quad-card') || e.target.closest('.service-card') || e.target.closest('.back-pill-btn');
        if (!target) return;
        const href = target.getAttribute('href') || target.getAttribute('onclick');
        if (href && typeof href === 'string') {
            const match = href.match(/([a-zA-Z0-9_-]+\.html)/);
            if (match && match[1]) {
                const link = document.createElement('link');
                link.rel = 'prefetch';
                link.as = 'document';
                link.href = match[1];
                document.head.appendChild(link);
            }
        }
    };

    document.addEventListener('touchstart', handleFastInteraction, { passive: true });
    document.addEventListener('mouseover', handleFastInteraction, { passive: true });
}

function autoDetectLowEndDevice() {
    const savedSetting = localStorage.getItem('coinstat_disable_animations');
    if (savedSetting === null) {
        // Automatically check if phone has weak CPU or low RAM
        const isLowCore = navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4;
        const isLowRam = navigator.deviceMemory && navigator.deviceMemory <= 3;
        const isOldAndroid = /Android\s([4-9]\.|10\.)/i.test(navigator.userAgent);
        if (isLowCore || isLowRam || isOldAndroid) {
            localStorage.setItem('coinstat_disable_animations', 'true');
            return true;
        }
    }
    return savedSetting === 'true';
}

// Freeze animated WebP and GIF images to static snapshot in Lite mode
function freezeAnimatedImages() {
    try {
        document.querySelectorAll('img').forEach(img => {
            const rawSrc = img.getAttribute('src') || img.src || '';
            if (rawSrc && (rawSrc.includes('.webp') || rawSrc.includes('.gif'))) {
                if (img.dataset.originalSrc) return; // already frozen

                const doFreeze = () => {
                    try {
                        if (img.naturalWidth === 0 || img.naturalHeight === 0) return;
                        const canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth;
                        canvas.height = img.naturalHeight;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0);
                        const staticDataUrl = canvas.toDataURL('image/png');
                        img.dataset.originalSrc = rawSrc;
                        img.src = staticDataUrl;
                    } catch(err) {
                        // ignore cross-origin security
                    }
                };

                if (img.complete && img.naturalWidth > 0) {
                    doFreeze();
                } else {
                    img.addEventListener('load', doFreeze, { once: true });
                }
            }
        });
    } catch(e){}
}

function unfreezeAnimatedImages() {
    try {
        document.querySelectorAll('img').forEach(img => {
            if (img.dataset.originalSrc) {
                img.src = img.dataset.originalSrc;
                delete img.dataset.originalSrc;
            }
        });
    } catch(e){}
}

function initAnimationsSetting() {
    const isLite = autoDetectLowEndDevice();
    if (isLite) {
        document.documentElement.classList.add('no-animations');
        if (document.body) document.body.classList.add('no-animations');
        try {
            document.querySelectorAll('video').forEach(v => {
                v.pause();
                v.currentTime = 0;
            });
        } catch(e){}
        freezeAnimatedImages();
    } else {
        document.documentElement.classList.remove('no-animations');
        if (document.body) document.body.classList.remove('no-animations');
        unfreezeAnimatedImages();
    }
}

function toggleAnimations(disable) {
    if (typeof disable === 'undefined') {
        const current = localStorage.getItem('coinstat_disable_animations') === 'true';
        disable = !current;
    }
    localStorage.setItem('coinstat_disable_animations', disable ? 'true' : 'false');
    initAnimationsSetting();
    return disable;
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
    const user = tg.initDataUnsafe?.user;
    const nameEl = document.getElementById('profileName');
    const idEl = document.getElementById('profileUserId');
    const placeholderEl = document.getElementById('avatarPlaceholder');
    const avatarImg = document.getElementById('avatarImg');

    const uid = getUserId();

    if (user) {
        if (nameEl) nameEl.textContent = (user.first_name || '') + (user.last_name ? ' ' + user.last_name : '');
        if (idEl) idEl.textContent = 'ID: ' + (user.id || uid || '—');
        if (placeholderEl && user.first_name) placeholderEl.textContent = user.first_name.charAt(0).toUpperCase();
        if (avatarImg && user.photo_url) {
            avatarImg.src = user.photo_url;
            avatarImg.style.display = 'block';
            if (placeholderEl) placeholderEl.style.display = 'none';
        }
    } else if (uid) {
        if (nameEl && !nameEl.textContent.trim()) nameEl.textContent = 'Foydalanuvchi';
        if (idEl) idEl.textContent = 'ID: ' + uid;
    } else {
        if (nameEl && !nameEl.textContent.trim()) nameEl.textContent = 'Foydalanuvchi';
        if (idEl) idEl.textContent = 'ID: —';
    }
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

let _initialBalRendered = false;

function setBalUI(val) {
    userBalance = Number(val) || 0;
    const formatted = userBalance.toLocaleString('uz-UZ');

    const balanceElement = document.getElementById('balance');
    if (balanceElement) {
        balanceElement.textContent = formatted;
    }

    const userBalanceStat = document.getElementById('userBalanceStat');
    if (userBalanceStat) {
        userBalanceStat.textContent = formatted;
    }

    document.querySelectorAll('.live-user-balance').forEach(el => {
        el.textContent = formatted;
    });

    updateStarsEquivalent(userBalance);
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
            try { localStorage.setItem('starpay_balance_' + userId, String(newBal)); } catch(e) {}
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
        'home.topup': '+ To\'ldirish',
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

        'gift.header_title': 'Telegram Sovg\'alari',
        'gift.header_subtitle': 'O\'zingiz yoki do\'stlaringiz uchun original Telegram sovg\'alarini xarid qiling!',
        'gift.cat_all': 'Barchasi (20)',
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
        'profile.gifts': 'Giftlarim',
        'profile.referrals': 'Takliflarim',
        'profile.section.transactions': 'TRANZAKSIYALAR',
        'profile.section.settings': 'SOZLAMALAR',
        'profile.lite_mode': 'Tezkor Rejim (Lite Mode)',
        'profile.lite_sub': 'Animatsiyalarni o\'chirib, tezlikni oshirish',
        'profile.support': 'Qo\'llab-quvvatlash',
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
        'home.topup': '+ Пополнить',
        'home.orders': 'Заказы',
        'home.spent': 'Потрачено',
        'home.balance_stat': 'Баланс',
        'home.lucky_spin': 'Lucky Spin',
        'home.promo_code': 'ПРОМОКОД',
        'home.spin_subtext': 'Выигрывайте подарки Telegram по промокоду!',
        'home.service_stars': 'Stars',
        'home.service_premium': 'Premium',
        'home.service_gifts': 'Подарки',
        'home.service_phone': 'Виртуальный Номер',

        'gift.header_title': 'Telegram Подарки',
        'gift.header_subtitle': 'Купите оригинальные подарки Telegram для себя или друзей!',
        'gift.cat_all': 'Все (20)',
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
        'profile.gifts': 'Мои подарки',
        'profile.referrals': 'Мои приглашения',
        'profile.section.transactions': 'ТРАНЗАКЦИИ',
        'profile.section.settings': 'НАСТРОЙКИ',
        'profile.lite_mode': 'Быстрый режим (Lite Mode)',
        'profile.lite_sub': 'Отключить анимации для ускорения',
        'profile.support': 'Поддержка',
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
        'home.topup': '+ Top Up',
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

        'gift.header_title': 'Telegram Gifts',
        'gift.header_subtitle': 'Purchase authentic Telegram gifts for yourself or friends!',
        'gift.cat_all': 'All (20)',
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
        'profile.gifts': 'My Gifts',
        'profile.referrals': 'My Referrals',
        'profile.section.transactions': 'TRANSACTIONS',
        'profile.section.settings': 'SETTINGS',
        'profile.lite_mode': 'Lite Mode (Ultra Fast)',
        'profile.lite_sub': 'Disable animations for maximum speed',
        'profile.support': 'Support',
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
   Bottom Dock Sliding Capsule Navigation
   ========================================= */
function initDockNavigation() {
    const dock = document.querySelector('.bottom-dock-nav');
    if (!dock) return;

    let glider = dock.querySelector('.dock-active-glider');
    if (!glider) {
        glider = document.createElement('div');
        glider.className = 'dock-active-glider';
        dock.prepend(glider);
    }

    const tabs = Array.from(dock.querySelectorAll('.dock-tab-btn'));
    if (!tabs.length) return;

    let activeIdx = tabs.findIndex(t => t.classList.contains('active'));
    if (activeIdx === -1) activeIdx = 0;

    const setGlider = (idx, animated = true) => {
        const targetTab = tabs[idx];
        if (!targetTab || !glider) return;
        
        const dockRect = dock.getBoundingClientRect();
        const tabRect = targetTab.getBoundingClientRect();
        
        const leftOffset = tabRect.left - dockRect.left;
        const width = tabRect.width;

        if (!animated) {
            glider.style.transition = 'none';
        } else {
            glider.style.transition = 'transform 0.35s cubic-bezier(0.34, 1.45, 0.64, 1), width 0.3s ease';
        }

        glider.style.width = width + 'px';
        glider.style.transform = `translateX(${leftOffset}px)`;
    };

    // Check if we came from another tab for seamless sliding entrance
    const prevIdxStr = sessionStorage.getItem('starpay_last_tab_idx');
    if (prevIdxStr !== null && !isNaN(parseInt(prevIdxStr, 10)) && parseInt(prevIdxStr, 10) !== activeIdx) {
        const prevIdx = parseInt(prevIdxStr, 10);
        if (prevIdx >= 0 && prevIdx < tabs.length) {
            setGlider(prevIdx, false);
            setTimeout(() => {
                setGlider(activeIdx, true);
            }, 30);
        } else {
            setGlider(activeIdx, false);
        }
    } else {
        setGlider(activeIdx, false);
        setTimeout(() => setGlider(activeIdx, true), 50);
    }

    sessionStorage.setItem('starpay_last_tab_idx', String(activeIdx));

    // Handle tab clicks with fluid sliding animation & haptic feedback
    tabs.forEach((tab, idx) => {
        const onclickAttr = tab.getAttribute('onclick') || '';
        const match = onclickAttr.match(/window\.location\.href\s*=\s*['"]([^'"]+)['"]/);
        const targetUrl = match ? match[1] : tab.getAttribute('href');

        tab.removeAttribute('onclick');

        tab.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();

            // Haptic Feedback
            try {
                if (window.Telegram?.WebApp?.HapticFeedback) {
                    window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
                }
            } catch(err) {}

            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            setGlider(idx, true);
            sessionStorage.setItem('starpay_last_tab_idx', String(idx));

            if (targetUrl) {
                setTimeout(() => {
                    window.location.href = targetUrl;
                }, 130);
            }
        });
    });

    window.addEventListener('resize', () => {
        const curActive = tabs.findIndex(t => t.classList.contains('active'));
        if (curActive !== -1) setGlider(curActive, false);
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
   App Launch Splash Loading Screen
   ========================================= */
function initSplashScreen() {
    let splash = document.getElementById('appSplashScreen');
    if (!splash) {
        splash = document.createElement('div');
        splash.className = 'app-splash-screen';
        splash.id = 'appSplashScreen';
        splash.innerHTML = `
            <div class="splash-icon-box">
                <img src="images/loader.webp" alt="CoinStat">
            </div>
            <div class="splash-brand-title">COINSTAT UZ</div>
            <div class="splash-dots-row">
                <div class="splash-dot"></div>
                <div class="splash-dot"></div>
                <div class="splash-dot"></div>
            </div>
            <div class="splash-loading-text">Yuklanmoqda...</div>
        `;
        document.body.prepend(splash);
    }

    const startTime = Date.now();
    const minDisplayTime = 750; // Smooth 750ms branding screen

    function dismissSplash() {
        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, minDisplayTime - elapsed);
        setTimeout(() => {
            splash.classList.add('fade-out');
            setTimeout(() => {
                splash.remove();
            }, 500);
        }, remaining);
    }

    if (document.readyState === 'complete') {
        dismissSplash();
    } else {
        window.addEventListener('load', dismissSplash);
        setTimeout(dismissSplash, 1500);
    }
}

