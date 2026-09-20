import asyncio
import html
import logging
import re
import aiohttp
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# === KEYS & CONFIG ===
# Отримуємо токен безпечно зі змінної середовища Railway (або використовуємо запасний)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8985383934:AAETY_Sx7prHAJf6xfH382Rw20aYMbXFapc")
ADMIN_ID = 0  # Enter your numeric Telegram ID if needed

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

# Storage
user_data_store = {}
monitored_usernames = {}
global_stats = {
    "total_checked": 0,
    "total_available": 0,
    "unique_users": set(),
}

# --- TRANSLATIONS ---
TEXTS = {
    "en": {
        "welcome": "👋 <b>Welcome, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — Your ultimate service for checking, generating, and tracking Telegram handles.\n\n👇 <i>Select an option from the menu below:</i>",
        "main_title": "🏠 <b>Main Menu</b>\n═════════════════════\nSelect a tool to manage usernames:",
        "btn_single": "🔍 Single Check",
        "btn_gen": "🎲 Idea Generator",
        "btn_bulk": "⚡ Bulk Search",
        "btn_var": "🧩 Variations",
        "btn_saved": "📌 Favorites",
        "btn_mon": "🔔 Monitoring",
        "btn_hist": "📜 History",
        "btn_stats": "📈 Statistics",
        "btn_settings": "⚙️ Settings",
        "btn_help": "ℹ️ Help & FAQ",
        "btn_back": "« Back to Menu",
        "btn_save": "📌 Save to Favorites",
        "btn_add_mon": "🔔 Monitor Availability",
        "single_prompt": "🔍 <b>Single Username Search</b>\n─────────────────────\nEnter the handle you want to check:\n<i>(e.g., <code>coolname</code> or <code>@coolname</code>)</i>",
        "checking": "🔄 <i>Processing request...</i>",
        "free_res": "🎯 <b>Check Results</b>\n─────────────────────\nUsername: <code>@{u}</code>\nStatus: 🟢 <b>AVAILABLE</b>\n\n✨ You can register it right now!",
        "taken_res": "🎯 <b>Check Results</b>\n─────────────────────\nUsername: <code>@{u}</code>\nStatus: 🔴 <b>TAKEN</b>\n\n💡 You can enable monitoring to track if it drops.",
        "invalid": "⚠️ Invalid username format or connection error.",
        "gen_prompt": "🎲 <b>Brand Idea Generator</b>\n─────────────────────\nEnter a base word or brand name:\n<i>(e.g., <code>crypto</code>, <code>studio</code>, <code>alex</code>)</i>",
        "gen_loading": "🎲 <i>Generating & testing ideas...</i>",
        "gen_found": "💡 <b>Available Ideas Found:</b>\n─────────────────────\n\n{items}\n\n<i>Click on a username to copy!</i>",
        "gen_none": "😔 No free combinations found for this keyword. Try another word!",
        "bulk_prompt": "⚡ <b>Bulk Search</b>\n─────────────────────\nSend a list of usernames separated by spaces or lines:\n<i>(Max 8 at a time)</i>",
        "bulk_checking": "⚡ <i>Checking {count} handles...</i>",
        "bulk_res": "📊 <b>Bulk Search Results:</b>\n─────────────────────\n\n{items}",
        "var_prompt": "🧩 <b>Variations Search</b>\n─────────────────────\nEnter a base name to test symbol/number variations:",
        "var_res": "📐 <b>Variations for</b> <code>@{u}</code>:\n─────────────────────\n\n{items}",
        "saved_empty": "📌 <b>Favorite Handles</b>\n─────────────────────\nYour list is empty.",
        "saved_list": "📌 <b>Your Saved Handles:</b>\n─────────────────────\n\n{items}",
        "saved_added": "✅ Added to favorites!",
        "saved_exists": "Already in your favorites!",
        "mon_prompt": "🔔 <b>Handle Monitoring</b>\n─────────────────────\nEnter a taken username to track:\n<i>(The bot will alert you as soon as it becomes available)</i>",
        "mon_added": "🔔 <b>Monitoring Activated!</b>\n─────────────────────\nNow tracking: <code>@{u}</code>",
        "mon_cb_added": "🔔 Tracking enabled for @{u}!",
        "hist_empty": "📜 <b>Search History</b>\n─────────────────────\nNo recent searches.",
        "hist_list": "📜 <b>Recent Searches:</b>\n─────────────────────\n\n{items}",
        "stats_title": "📈 <b>System Statistics</b>\n═════════════════════\n<b>Your Stats:</b>\n ▫️ Checks: <b>{user_checks}</b>\n ▫️ Found Available: <b>{user_free}</b>\n\n<b>Global Stats:</b>\n ▫️ Total Checks: <b>{total_checks}</b>\n ▫️ Total Free Found: <b>{total_free}</b>\n ▫️ Active Users: <b>{users}</b>",
        "settings_title": "⚙️ <b>Settings</b>\n─────────────────────\n ▫️ Current Language: <b>{lang}</b>\n ▫️ Mode: <b>Detailed</b>\n ▫️ Notifications: <b>Enabled 🔔</b>\n\n👇 <i>Choose a language:</i>",
        "help_text": "ℹ️ <b>Help & Information</b>\n═════════════════════\n1. <b>Single Check:</b> Instantly check if a handle is free.\n2. <b>Generator:</b> Auto-generate catchy handle ideas.\n3. <b>Bulk Search:</b> Batch check up to 8 usernames at once.\n4. <b>Monitoring:</b> Get notified when a taken handle frees up.",
        "alert_text": "🔔 <b>AVAILABILITY ALERT!</b>\n═════════════════════\nThe handle <code>@{u}</code> has just become <b>AVAILABLE</b>!\n\n⚡ Claim it quickly before someone else does!",
        "free_word": "Free",
        "taken_word": "Taken",
    },
    "ua": {
        "welcome": "👋 <b>Вітаємо, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — ваш сервіс для перевірки, підбору та моніторингу юзернеймів.\n\n👇 <i>Оберіть потрібний розділ:</i>",
        "main_title": "🏠 <b>Головне Меню</b>\n═════════════════════\nОберіть інструмент:",
        "btn_single": "🔍 Перевірити один",
        "btn_gen": "🎲 Генератор ідей",
        "btn_bulk": "⚡ Масовий чек",
        "btn_var": "🧩 Варіації",
        "btn_saved": "📌 Обране",
        "btn_mon": "🔔 Моніторинг",
        "btn_hist": "📜 Історія",
        "btn_stats": "📈 Статистика",
        "btn_settings": "⚙️ Налаштування",
        "btn_help": "ℹ️ Довідка",
        "btn_back": "« Повернутися в меню",
        "btn_save": "📌 Зберегти в обране",
        "btn_add_mon": "🔔 Поставити на моніторинг",
        "single_prompt": "🔍 <b>Пошук юзернейма</b>\n─────────────────────\nВведіть юзернейм для перевірки:\n<i>(наприклад: <code>coolname</code> або <code>@coolname</code>)</i>",
        "checking": "🔄 <i>Обробка запиту...</i>",
        "free_res": "🎯 <b>Результати перевірки</b>\n─────────────────────\nЮзернейм: <code>@{u}</code>\nСтатус: 🟢 <b>ВІЛЬНИЙ</b>\n\n✨ Ви можете зареєструвати його зараз!",
        "taken_res": "🎯 <b>Результати перевірки</b>\n─────────────────────\nЮзернейм: <code>@{u}</code>\nСтатус: 🔴 <b>ЗАЙНЯТИЙ</b>\n\n💡 Увімкніть моніторинг, щоб стежити за звільненням.",
        "invalid": "⚠️ Некоректний формат або помилка мережі.",
        "gen_prompt": "🎲 <b>Генератор ідей</b>\n─────────────────────\nВведіть базoве слово або бренд:",
        "gen_loading": "🎲 <i>Генеруємо варіанти...</i>",
        "gen_found": "💡 <b>Знайдені вільні варіанти:</b>\n─────────────────────\n\n{items}\n\n<i>Торкніться імені, щоб скопіювати!</i>",
        "gen_none": "😔 Вільних комбінацій не знайдено. Спробуйте інше слово!",
        "bulk_prompt": "⚡ <b>Масовий чек</b>\n─────────────────────\nНадішліть список юзернеймів:\n<i>(Максимум 8 за раз)</i>",
        "bulk_checking": "⚡ <i>Перевіряємо {count} юзернеймів...</i>",
        "bulk_res": "📊 <b>Результати масової перевірки:</b>\n─────────────────────\n\n{items}",
        "var_prompt": "🧩 <b>Пошук варіацій</b>\n─────────────────────\nВведіть ім'я для підбору варіацій:",
        "var_res": "📐 <b>Варіації для</b> <code>@{u}</code>:\n─────────────────────\n\n{items}",
        "saved_empty": "📌 <b>Обране</b>\n─────────────────────\nСписок порожній.",
        "saved_list": "📌 <b>Ваші збережені юзернейми:</b>\n─────────────────────\n\n{items}",
        "saved_added": "✅ Додано в обране!",
        "saved_exists": "Вже є у вашому обраному!",
        "mon_prompt": "🔔 <b>Моніторинг</b>\n─────────────────────\nВведіть зайнятий юзернейм:",
        "mon_added": "🔔 <b>Моніторинг увімкнено!</b>\n─────────────────────\nСтежимо за: <code>@{u}</code>",
        "mon_cb_added": "🔔 Стеження для @{u} увімкнено!",
        "hist_empty": "📜 <b>Історія</b>\n─────────────────────\nПорожньо.",
        "hist_list": "📜 <b>Останні перевірки:</b>\n─────────────────────\n\n{items}",
        "stats_title": "📈 <b>Статистика системи</b>\n═════════════════════\n<b>Ваші дані:</b>\n ▫️ Перевірок: <b>{user_checks}</b>\n ▫️ Вільних: <b>{user_free}</b>\n\n<b>Загальні дані:</b>\n ▫️ Усього перевірок: <b>{total_checks}</b>\n ▫️ Усього вільних: <b>{total_free}</b>\n ▫️ Користувачів: <b>{users}</b>",
        "settings_title": "⚙️ <b>Налаштування</b>\n─────────────────────\n ▫️ Поточна мова: <b>{lang}</b>\n ▫️ Режим: <b>Детальний</b>\n ▫️ Сповіщення: <b>Увімкнено 🔔</b>\n\n👇 <i>Оберіть мову:</i>",
        "help_text": "ℹ️ <b>Довідка</b>\n═════════════════════\n1. <b>Пошук:</b> Швидка перевірка доступності.\n2. <b>Генератор:</b> Підбір назв.\n3. <b>Масовий чек:</b> Перевірка до 8 імен.\n4. <b>Моніторинг:</b> Сповіщення про звільнення.",
        "alert_text": "🔔 <b>ЮЗЕРНЕЙМ ЗВІЛЬНИВСЯ!</b>\n═════════════════════\nЮзернейм <code>@{u}</code> тепер <b>ВІЛЬНИЙ</b>!\n\n⚡ Поспішайте забрати його!",
        "free_word": "Вільний",
        "taken_word": "Зайнятий",
    },
    "de": {
        "welcome": "👋 <b>Willkommen, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — Ihr Tool zum Überprüfen, Generieren und Verfolgen von Telegram-Benutzernamen.\n\n👇 <i>Wählen Sie eine Option:</i>",
        "main_title": "🏠 <b>Hauptmenü</b>\n═════════════════════\nWählen Sie ein Werkzeug:",
        "btn_single": "🔍 Einzelprüfung",
        "btn_gen": "🎲 Generator",
        "btn_bulk": "⚡ Massenprüfung",
        "btn_var": "🧩 Variationen",
        "btn_saved": "📌 Favoriten",
        "btn_mon": "🔔 Überwachung",
        "btn_hist": "📜 Verlauf",
        "btn_stats": "📈 Statistiken",
        "btn_settings": "⚙️ Einstellungen",
        "btn_help": "ℹ️ Hilfe",
        "btn_back": "« Zurück zum Menü",
        "btn_save": "📌 Speichern",
        "btn_add_mon": "🔔 Überwachen",
        "single_prompt": "🔍 <b>Benutzernamensuche</b>\n─────────────────────\nGeben Sie den Benutzernamen ein:",
        "checking": "🔄 <i>Überprüfe...</i>",
        "free_res": "🎯 <b>Ergebnis</b>\n─────────────────────\nName: <code>@{u}</code>\nStatus: 🟢 <b>VERFÜGBAR</b>",
        "taken_res": "🎯 <b>Ergebnis</b>\n─────────────────────\nName: <code>@{u}</code>\nStatus: 🔴 <b>BELEGT</b>",
        "invalid": "⚠️ Ungültiges Format oder Verbindungsfehler.",
        "gen_prompt": "🎲 <b>Ideengenerator</b>\n─────────────────────\nGeben Sie ein Wort ein:",
        "gen_loading": "🎲 <i>Generiere...</i>",
        "gen_found": "💡 <b>Verfügbare Ideen:</b>\n─────────────────────\n\n{items}",
        "gen_none": "😔 Keine freien Kombinationen gefunden.",
        "bulk_prompt": "⚡ <b>Massenprüfung</b>\n─────────────────────\nGeben Sie eine Liste ein (Max 8):",
        "bulk_checking": "⚡ <i>Prüfe {count} Namen...</i>",
        "bulk_res": "📊 <b>Ergebnisse:</b>\n─────────────────────\n\n{items}",
        "var_prompt": "🧩 <b>Variationen</b>\n─────────────────────\nGeben Sie einen Namen ein:",
        "var_res": "📐 <b>Variationen für</b> <code>@{u}</code>:\n─────────────────────\n\n{items}",
        "saved_empty": "📌 <b>Favoriten</b>\n─────────────────────\nListe ist leer.",
        "saved_list": "📌 <b>Gespeicherte Namen:</b>\n─────────────────────\n\n{items}",
        "saved_added": "✅ Gespeichert!",
        "saved_exists": "Bereits gespeichert!",
        "mon_prompt": "🔔 <b>Überwachung</b>\n─────────────────────\nGeben Sie einen belegten Namen ein:",
        "mon_added": "🔔 <b>Aktiviert!</b>\n─────────────────────\nVerfolge: <code>@{u}</code>",
        "mon_cb_added": "🔔 Überwachung für @{u} gestartet!",
        "hist_empty": "📜 <b>Verlauf</b>\n─────────────────────\nLeer.",
        "hist_list": "📜 <b>Verlauf:</b>\n─────────────────────\n\n{items}",
        "stats_title": "📈 <b>Statistiken</b>\n═════════════════════\nPrüfungen: <b>{user_checks}</b>\nFrei gefunden: <b>{user_free}</b>",
        "settings_title": "⚙️ <b>Einstellungen</b>\n─────────────────────\nSprache: <b>{lang}</b>\n\n👇 <i>Sprache wählen:</i>",
        "help_text": "ℹ️ <b>Hilfe</b>\n═════════════════════\nÜberprüfen Sie Verfügbarkeiten und verfogen Sie freie Namen.",
        "alert_text": "🔔 <b>BENUTZERNAME FREI!</b>\n═════════════════════\n<code>@{u}</code> ist jetzt <b>VERFÜGBAR</b>!",
        "free_word": "Frei",
        "taken_word": "Belegt",
    },
    "zh": {
        "welcome": "👋 <b>欢迎, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — 您的 Telegram 用户名检测、生成与监控工具。\n\n👇 <i>请在下方选择功能:</i>",
        "main_title": "🏠 <b>主菜单</b>\n═════════════════════\n请选择工具:",
        "btn_single": "🔍 单个检测",
        "btn_gen": "🎲 灵感生成",
        "btn_bulk": "⚡ 批量检测",
        "btn_var": "🧩 变体匹配",
        "btn_saved": "📌 收藏夹",
        "btn_mon": "🔔 释放监控",
        "btn_hist": "📜 历史记录",
        "btn_stats": "📈 数据统计",
        "btn_settings": "⚙️ 设置",
        "btn_help": "ℹ️ 帮助指南",
        "btn_back": "« 返回主菜单",
        "btn_save": "📌 保存到收藏夹",
        "btn_add_mon": "🔔 开启释放监控",
        "single_prompt": "🔍 <b>用户名查询</b>\n─────────────────────\n请输入要查询的用户名:\n<i>(例如: <code>coolname</code> 或 <code>@coolname</code>)</i>",
        "checking": "🔄 <i>正在查询中...</i>",
        "free_res": "🎯 <b>查询结果</b>\n─────────────────────\n用户名: <code>@{u}</code>\n状态: 🟢 <b>未被占用 (可注册)</b>",
        "taken_res": "🎯 <b>查询结果</b>\n─────────────────────\n用户名: <code>@{u}</code>\n状态: 🔴 <b>已被占用</b>",
        "invalid": "⚠️ 用户名格式错误或网络连接超时。",
        "gen_prompt": "🎲 <b>品牌灵感生成</b>\n─────────────────────\请输入基础词汇或品牌名:",
        "gen_loading": "🎲 <i>正在生成并匹配...</i>",
        "gen_found": "💡 <b>找到可用的用户名:</b>\n─────────────────────\n\n{items}",
        "gen_none": "😔 未找到可用组合，请尝试其他词汇！",
        "bulk_prompt": "⚡ <b>批量检测</b>\n─────────────────────\n发送用户名列表 (最多 8 个):",
        "bulk_checking": "⚡ <i>正在检测 {count} 个用户名...</i>",
        "bulk_res": "📊 <b>批量检测结果:</b>\n─────────────────────\n\n{items}",
        "var_prompt": "🧩 <b>变体查询</b>\n─────────────────────\n请输入基础名称:",
        "var_res": "📐 <b><code>@{u}</code> 的变体结果:</b>\n─────────────────────\n\n{items}",
        "saved_empty": "📌 <b>收藏夹</b>\n─────────────────────\n暂无保存的用户名。",
        "saved_list": "📌 <b>您的收藏夹:</b>\n─────────────────────\n\n{items}",
        "saved_added": "✅ 已添加到收藏夹！",
        "saved_exists": "已在收藏夹中！",
        "mon_prompt": "🔔 <b>释放监控</b>\n─────────────────────\n请输入已被占用的用户名:",
        "mon_added": "🔔 <b>监控已开启！</b>\n─────────────────────\n正在监控: <code>@{u}</code>",
        "mon_cb_added": "🔔 已开启对 @{u} 的监控！",
        "hist_empty": "📜 <b>历史记录</b>\n─────────────────────\n暂无记录。",
        "hist_list": "📜 <b>最近查询:</b>\n─────────────────────\n\n{items}",
        "stats_title": "📈 <b>系统统计</b>\n═════════════════════\n查询次数: <b>{user_checks}</b>\n发现可用: <b>{user_free}</b>",
        "settings_title": "⚙️ <b>设置</b>\n─────────────────────\n当前语言: <b>{lang}</b>\n\n👇 <i>选择语言:</i>",
        "help_text": "ℹ️ <b>帮助指南</b>\n═════════════════════\n轻松查询、生成与监控 Telegram 用户名。",
        "alert_text": "🔔 <b>用户名已释放！</b>\n═════════════════════\n用户名 <code>@{u}</code> 现在<b>可以注册</b>了！",
        "free_word": "未占用",
        "taken_word": "已占用",
    },
}

LANG_NAMES = {
    "en": "English 🇬🇧",
    "ua": "Українська 🇺🇦",
    "de": "Deutsch 🇩🇪",
    "zh": "中文 🇨🇳",
}

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "ua",  # Ставимо українську за замовчуванням
            "saved": [],
            "history": [],
            "checked_count": 0,
            "available_count": 0,
        }
    global_stats["unique_users"].add(user_id)
    return user_data_store[user_id]

def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_user_profile(user_id).get("lang", "ua")
    template = TEXTS.get(lang, TEXTS["ua"]).get(key, TEXTS["ua"].get(key, ""))
    return template.format(**kwargs)

# --- STATES ---
class BotStates(StatesGroup):
    single_search = State()
    generator_keyword = State()
    bulk_search = State()
    variation_search = State()
    monitor_username = State()
    broadcast_admin = State()

# --- KEYBOARDS ---
def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=t(user_id, "btn_single"), callback_data="menu:single"),
            InlineKeyboardButton(text=t(user_id, "btn_gen"), callback_data="menu:generator"),
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_bulk"), callback_data="menu:bulk"),
            InlineKeyboardButton(text=t(user_id, "btn_var"), callback_data="menu:variations"),
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_saved"), callback_data="menu:saved"),
            InlineKeyboardButton(text=t(user_id, "btn_mon"), callback_data="menu:monitor"),
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_hist"), callback_data="menu:history"),
            InlineKeyboardButton(text=t(user_id, "btn_stats"), callback_data="menu:stats"),
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_settings"), callback_data="menu:settings"),
            InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="menu:help"),
        ],
    ]
    if user_id == ADMIN_ID and ADMIN_ID != 0:
        buttons.append([InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")]]
    )

# --- HTTP USERNAME CHECKER ---
async def check_single_username(username: str) -> bool | None:
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return None
    url = f"https://t.me/{username}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                text = await resp.text()
                if "tgme_page_extra" in text or "tgme_page_title" in text:
                    if "If you have Telegram, you can contact" in text or "View in Telegram" in text:
                        return False
                return True
    except Exception:
        return None

# --- BACKGROUND MONITOR TASK ---
async def monitoring_worker():
    while True:
        await asyncio.sleep(60)
        if not monitored_usernames:
            continue
        for username, user_ids in list(monitored_usernames.items()):
            is_free = await check_single_username(username)
            if is_free is True:
                for uid in user_ids:
                    try:
                        alert = t(uid, "alert_text", u=username)
                        await bot.send_message(uid, alert, parse_mode="HTML")
                    except Exception:
                        pass
                del monitored_usernames[username]

# --- HANDLERS ---
@dispatcher.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    name = html.escape(message.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

# Головна функція для запуску
async def main():
    asyncio.create_task(monitoring_worker())
    await dispatcher.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
