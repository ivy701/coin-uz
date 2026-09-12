import os
from dotenv import load_dotenv

load_dotenv()

# Bot settings
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Telethon (User Client for sending gifts)
# Optional - if not set, gift sending will be disabled
try:
    API_ID = int(os.getenv("API_ID", "0") or "0")
except (ValueError, TypeError):
    API_ID = 0

API_HASH = os.getenv("API_HASH", "")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")  # Your phone number for user account
SESSION_NAME = os.getenv("SESSION_NAME", "starpay_session")
TELETHON_SESSION_STRING = os.getenv("TELETHON_SESSION_STRING", "")  # String session for Railway

# Fragment API settings
FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")
FRAGMENT_API_URL = os.getenv("FRAGMENT_API_URL", "https://fragment-api.uz/api/v1")

# Shop settings
SHOP_ID = os.getenv("SHOP_ID")
SHOP_KEY = os.getenv("SHOP_KEY")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")

# Web App
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://web-production-4014a4.up.railway.app/app")

# Admin IDs (read from environment)
ADMINS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# Admin Panel URL
ADMIN_PANEL_URL = os.getenv("ADMIN_PANEL_URL", "http://localhost:8000")

# Premium Emoji IDs (for <tg-emoji> in messages and icon_custom_emoji_id on buttons)
CUSTOM_EMOJI_WALLET = os.getenv("CUSTOM_EMOJI_WALLET", "5769403330761593044")  # 👛 для кнопки/суммы
CUSTOM_EMOJI_MONEY = os.getenv("CUSTOM_EMOJI_MONEY", "5987880246865565644")    # 💰 баланс в тексте
CUSTOM_EMOJI_CHECK = os.getenv("CUSTOM_EMOJI_CHECK", "5843908536467198016")    # ✅ успех

# Channel notifications emoji IDs
EMOJI_STAR = os.getenv("EMOJI_STAR", "5312253613140121792")              # ⭐️
EMOJI_TARGET = os.getenv("EMOJI_TARGET", "5350460637182993292")          # 🎯
EMOJI_STARS_AMOUNT = os.getenv("EMOJI_STARS_AMOUNT", "5469741319330996757")  # 💫
EMOJI_CALENDAR = os.getenv("EMOJI_CALENDAR", "5967412305338568701")     # 📅
EMOJI_MONEY_CH = os.getenv("EMOJI_MONEY_CH", "4965219701572503640")     # 💰
EMOJI_ROCKET = os.getenv("EMOJI_ROCKET", "6147654280112248427")         # 🚀
EMOJI_GIFT = os.getenv("EMOJI_GIFT", "5417935058734458022")             # 🎁 (gift header)
EMOJI_HEART = os.getenv("EMOJI_HEART", "5244859778060031233")           # 💝
EMOJI_BEAR = os.getenv("EMOJI_BEAR", "5418143824209810742")             # 🧸
EMOJI_ROSE = os.getenv("EMOJI_ROSE", "5341393243961596728")             # 🌹
EMOJI_BOX = os.getenv("EMOJI_BOX", "5417905294611092330")               # 🎁 (box)
EMOJI_BOUQUET = os.getenv("EMOJI_BOUQUET", "5341696099285512104")       # 💐
EMOJI_CAKE = os.getenv("EMOJI_CAKE", "5417873163960751611")             # 🎂
EMOJI_ROCKET_GIFT = os.getenv("EMOJI_ROCKET_GIFT", "5343573506799995914")  # 🚀 (gift)
EMOJI_DIAMOND = os.getenv("EMOJI_DIAMOND", "5343915364721923982")       # 💎
EMOJI_TROPHY = os.getenv("EMOJI_TROPHY", "5341354194118942558")         # 🏆
EMOJI_RING = os.getenv("EMOJI_RING", "5345797174577897195")             # 💍

# Orders notification channel
CHANNEL_ORDERS = os.getenv("CHANNEL_ORDERS", "@coinstatuz_org")
CUSTOM_EMOJI_DOWN = os.getenv("CUSTOM_EMOJI_DOWN", "5229212516415978792")      # ⬇️
CUSTOM_EMOJI_UP = os.getenv("CUSTOM_EMOJI_UP", "5229113938326599381")          # ⬆️
CUSTOM_EMOJI_ID = os.getenv("CUSTOM_EMOJI_ID", "5818885490065017876")          # 🆔
CUSTOM_EMOJI_CARD = os.getenv("CUSTOM_EMOJI_CARD", "5927169041595634481")      # 💳
CUSTOM_EMOJI_USER = os.getenv("CUSTOM_EMOJI_USER", "5260399854500191689")      # 👤
CUSTOM_EMOJI_CLOCK = os.getenv("CUSTOM_EMOJI_CLOCK", "5316591603123502631")    # ⏰
CUSTOM_EMOJI_WARN = os.getenv("CUSTOM_EMOJI_WARN", "5881702736843511327")      # ⚠️ в карте
CUSTOM_EMOJI_WARN2 = os.getenv("CUSTOM_EMOJI_WARN2", "5316554554735607106")    # ⚠️ timeout

# Allowed usernames (for access control) - comma separated
ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "*").split(",")
# Пример: ALLOWED_USERNAMES=admin,user1,user2 — или ALLOWED_USERNAMES=* для всех

# Stars limits (Fragment API minimum is 50)
STARS_MIN_AMOUNT = 50
STARS_MAX_AMOUNT = 1_000_000

# Products configuration
PRODUCTS = {
    "stars": {
        "name": "⭐ Stars olish",
        "emoji": "⭐",
        "color": "#FFD700",
        "min_amount": STARS_MIN_AMOUNT,
        "max_amount": STARS_MAX_AMOUNT,
        "packages": [
            {"amount": 50, "price": 9900},
            {"amount": 75, "price": 15000},
            {"amount": 100, "price": 20000},
            {"amount": 250, "price": 50000},
            {"amount": 500, "price": 100000},
        ]
    },
    "premium": {
        "name": "💎 Premium olish",
        "emoji": "💎",
        "color": "#00BFFF",
        "is_premium": True,
        "packages": [
            {"duration": 3, "price": 160000, "name": "3 oy"},
            {"duration": 6, "price": 225000, "name": "6 oy"},
            {"duration": 12, "price": 390000, "name": "12 oy"},
        ]
    },
    "phone": {
        "name": "📱 Nomer olish",
        "emoji": "📱",
        "color": "#808080",
        "info": "Virtual raqamlar"
    },
    "gift": {
        "name": "🎁 Gift olish",
        "emoji": "🎁",
        "color": "#FF69B4",
        "info": "Premium sovg'alar",
        "packages": [
            # Обычные подарки (Regular Gifts)
            {"id": "heart", "name": "Yurak", "price": 3000, "emoji": "💝", "stars": 1, "tier": "regular"},
            {"id": "bear", "name": "Ayiq", "price": 3000, "emoji": "🧸", "stars": 1, "tier": "regular"},
            {"id": "box", "name": "Quti", "price": 5000, "emoji": "🎁", "stars": 1, "tier": "regular"},
            {"id": "rose", "name": "Atirgul", "price": 5000, "emoji": "🌹", "stars": 1, "tier": "regular"},
            {"id": "cake", "name": "Tort", "price": 10000, "emoji": "🎂", "stars": 2, "tier": "regular"},
            {"id": "rocket", "name": "Raketa", "price": 10000, "emoji": "🚀", "stars": 2, "tier": "regular"},
            {"id": "champagne", "name": "Shampan", "price": 10000, "emoji": "🍾", "stars": 2, "tier": "regular"},
            {"id": "bouquet", "name": "Guldasta", "price": 10000, "emoji": "💐", "stars": 2, "tier": "regular"},
            {"id": "diamond", "name": "Olmos", "price": 20000, "emoji": "💎", "stars": 5, "tier": "regular"},
            {"id": "trophy", "name": "Kubok", "price": 20000, "emoji": "🏆", "stars": 5, "tier": "regular"},
            {"id": "ring", "name": "Uzuk", "price": 20000, "emoji": "💍", "stars": 5, "tier": "regular"},
            
            # Удалённые/Премиум подарки (Deluxe/Limited Gifts)
            {"id": "deluxe_rose", "name": "Deluxe Atirgul", "price": 50000, "emoji": "🌹✨", "stars": 25, "tier": "deluxe", "limited": True},
            {"id": "deluxe_heart", "name": "Deluxe Yurak", "price": 50000, "emoji": "💝✨", "stars": 25, "tier": "deluxe", "limited": True},
            {"id": "deluxe_cake", "name": "Deluxe Tort", "price": 75000, "emoji": "🎂✨", "stars": 50, "tier": "deluxe", "limited": True},
            {"id": "deluxe_diamond", "name": "Deluxe Olmos", "price": 100000, "emoji": "💎✨", "stars": 100, "tier": "deluxe", "limited": True},
            {"id": "golden_trophy", "name": "Oltin Kubok", "price": 150000, "emoji": "🏆✨", "stars": 250, "tier": "premium", "limited": True},
            {"id": "star_crown", "name": "Yulduz Toj", "price": 200000, "emoji": "👑✨", "stars": 500, "tier": "premium", "limited": True},
            {"id": "blue_gem", "name": "Ko'k Javohir", "price": 250000, "emoji": "💠", "stars": 1000, "tier": "premium", "limited": True},
            {"id": "fire_phoenix", "name": "Olovli Qanot", "price": 500000, "emoji": "🔥🦅", "stars": 2500, "tier": "exclusive", "limited": True},
            
            # Cheklangan sovg'alar (Limited Edition)
            {"id": "newyear_tree", "name": "Yangi yil archasi", "price": 10500, "emoji": "🎄", "stars": 50, "tier": "limited"},
            {"id": "newyear_bear", "name": "Yangi yil ayiqchasi", "price": 10500, "emoji": "🧸", "stars": 50, "tier": "limited"},
            {"id": "valentine_heart", "name": "Sevgi yuragi", "price": 10500, "emoji": "💜", "stars": 50, "tier": "limited"},
            {"id": "valentine_bear", "name": "Sevgi ayiqchasi", "price": 10500, "emoji": "🧸💜", "stars": 50, "tier": "limited"},
            {"id": "march8_bear", "name": "8-mart ayiqchasi", "price": 10500, "emoji": "🧸🌷", "stars": 50, "tier": "limited"},
            {"id": "patrick_bear", "name": "Sent-Patrik ayiqchasi", "price": 10500, "emoji": "🧸☘️", "stars": 50, "tier": "limited"},
            {"id": "april_bear", "name": "1-aprel ayiqchasi", "price": 10500, "emoji": "🧸🎉", "stars": 50, "tier": "limited"},
            {"id": "easter_bear", "name": "Pasxa ayiqchasi", "price": 10500, "emoji": "🧸🐣", "stars": 50, "tier": "limited"},
            {"id": "may_bear", "name": "1-may ayiqchasi", "price": 10500, "emoji": "🧸🌼", "stars": 50, "tier": "limited"},
        ]
    }
}
