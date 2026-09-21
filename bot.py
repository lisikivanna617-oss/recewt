import asyncio
import html
import io
import logging
import os
import random
import re
import uuid
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    BufferedInputFile,
)
from aiogram.exceptions import TelegramBadRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# Отримання токена зі змінних оточення Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("BOT_TOKEN не знайдено у Variables Railway!")

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

ADMIN_ID = 5619415334
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

# Збереження даних користувачів та кеш
user_data_store = {}
search_results_cache = {}
global_checked_usernames = set()

TEXTS = {
    "en": {
        "welcome": "👋 <b>Welcome to USERNAME FIX, {name}!</b>\n═════════════════════\nAutomated Telegram Username Finder, Generator & Monitor.\n\nDefault language set to <b>English 🇬🇧</b>. You can change it anytime in settings.\n\n👇 <i>Choose an action below:</i>",
        "btn_auto_search": "🔍 Auto-Search",
        "btn_prefix_search": "🔤 Prefix (@app*)",
        "btn_suffix_search": "🔚 Suffix (*bot)",
        "btn_exact_search": "🎯 Exact Check",
        "btn_smart_variations": "🧠 Smart Variations",
        "btn_categories": "🏷 Categories",
        "btn_profile": "👤 Profile & Saved",
        "btn_mon": "🔔 Monitor",
        "btn_settings": "🌍 Language Settings",
        "btn_help": "ℹ️ Help",
        "btn_back": "« Back to Menu",
        "btn_export_txt": "📦 Export TXT",
        "btn_clear_history": "🗑 Clear History",
        "search_prompt": "🔍 <b>Auto-Search Usernames</b>\n─────────────────────\nSelect the desired username length (5 to 12 chars):",
        "type_prompt": "⚙️ <b>Character Filter</b>\n─────────────────────\nSelect username composition:",
        "btn_letters": "Letters Only 🔤",
        "btn_numbers": "Letters + Numbers 🔢",
        "prefix_prompt": "🔤 <b>Prefix Search</b>\n─────────────────────\nSend your prefix (e.g., <code>app</code> to search for <code>@app...</code>):",
        "suffix_prompt": "🔚 <b>Suffix Search</b>\n─────────────────────\nSend your suffix (e.g., <code>dev</code> to search for <code>@...dev</code>):",
        "exact_prompt": "🎯 <b>Exact Search</b>\n─────────────────────\nSend the exact username you want to check (e.g. <code>@username</code>):",
        "smart_prompt": "🧠 <b>Smart Variations Generator</b>\n─────────────────────\nSend a base name (e.g., <code>falbercht</code>) to generate variations:",
        "categories_prompt": "🏷 <b>Select Category</b>\n─────────────────────\nChoose a topic to generate specialized usernames:",
        "cat_gaming": "🎮 Gaming",
        "cat_f1": "🏎 Formula 1",
        "cat_tech": "💻 Tech & Dev",
        "cat_brand": "💼 Brand & HQ",
        "cat_personal": "⭐ Personal",
        "searching": "🔍 Scanning Telegram network... Please wait ⏳",
        "search_results": "🎉 <b>Found Available Usernames</b>\n🆔 <b>Search ID:</b> <code>#{search_id}</code>\n─────────────────────\n{results}",
        "search_none": "❌ No free usernames found in this batch. Try again!",
        "btn_more": "🔄 Search Again / More",
        "mon_prompt": "🔔 <b>Monitoring</b>\n─────────────────────\nSend a taken username to track status changes:",
        "mon_success": "✅ <b>Monitoring active for <code>{username}</code>!</b>\nYou will be notified as soon as it becomes available.",
        "profile_text": "👤 <b>User Profile</b>\n─────────────────────\n🆔 <b>User ID:</b> <code>{user_id}</code>\n🌍 <b>Language:</b> {lang}\n📊 <b>Total Checks Performed:</b> {checks}\n⭐ <b>Saved Usernames:</b> {saved_count}\n🔔 <b>Active Monitors:</b> {mon_count}",
        "saved_title": "⭐ <b>Your Saved Usernames:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ No saved usernames yet.",
        "history_empty": "📜 Search history is empty.",
        "history_cleared": "🗑 Search history successfully cleared!",
        "saved_success": "✅ Username <b>{username}</b> saved!",
        "help_text": "ℹ️ <b>Help & Features</b>\n═════════════════════\n• <b>Auto-Search:</b> Scan random free usernames.\n• <b>Prefix/Suffix:</b> Search usernames with specific start or end.\n• <b>Exact Check:</b> Direct single username verification.\n• <b>Smart Variations:</b> Generate prefixes, suffixes, and tags.\n• <b>Categories:</b> Topic-specific generators (Gaming, F1, Tech, etc.).\n• <b>Export TXT:</b> Download results as a text file.",
        "lang_changed": "Language successfully changed! ✅",
        "admin_demo_start": "🧪 <b>Admin Demo Mode Triggered</b>\nRunning batch scan of 20 test usernames...",
    },
    "ua": {
        "welcome": "👋 <b>Ласкаво просимо до USERNAME FIX, {name}!</b>\n═════════════════════\nАвтоматизований пошук, генерація та моніторинг юзернеймів Telegram.\n\nМова за замовчуванням: <b>English 🇬🇧</b>. Ви можете змінити її в налаштуваннях.\n\n👇 <i>Оберіть дію нижче:</i>",
        "btn_auto_search": "🔍 Авто-пошук",
        "btn_prefix_search": "🔤 Префікс (@app*)",
        "btn_suffix_search": "🔚 Суфікс (*bot)",
        "btn_exact_search": "🎯 Точна перевірка",
        "btn_smart_variations": "🧠 Розумні варіації",
        "btn_categories": "🏷 Категорії",
        "btn_profile": "👤 Профіль та Збережені",
        "btn_mon": "🔔 Моніторинг",
        "btn_settings": "🌍 Налаштування мови",
        "btn_help": "ℹ️ Довідка",
        "btn_back": "« Назад у меню",
        "btn_export_txt": "📦 Експорт TXT",
        "btn_clear_history": "🗑 Очистити історію",
        "search_prompt": "🔍 <b>Авто-пошук юзернеймів</b>\n─────────────────────\nОберіть бажану довжину (від 5 до 12 символів):",
        "type_prompt": "⚙️ <b>Фільтр символів</b>\n─────────────────────\nОберіть склад юзернейму:",
        "btn_letters": "Лише букви 🔤",
        "btn_numbers": "Букви + Циفري 🔢",
        "prefix_prompt": "🔤 <b>Пошук за префіксом</b>\n─────────────────────\nВведіть початок (наприклад, <code>app</code> для пошуку <code>@app...</code>):",
        "suffix_prompt": "🔚 <b>Пошук за закінченням</b>\n─────────────────────\nВведіть закінчення (наприклад, <code>dev</code> для пошуку <code>@...dev</code>):",
        "exact_prompt": "🎯 <b>Точний пошук</b>\n─────────────────────\nВведіть конкретний юзернейм для перевірки (наприклад, <code>@username</code>):",
        "smart_prompt": "🧠 <b>Розумні варіації</b>\n─────────────────────\nВведіть базове ім'я (наприклад, <code>falbercht</code>):",
        "categories_prompt": "🏷 <b>Оберіть категорію</b>\n─────────────────────\nОберіть тематику для генерації юзернеймів:",
        "cat_gaming": "🎮 Геймінг",
        "cat_f1": "🏎 Формула 1",
        "cat_tech": "💻 Технології & Dev",
        "cat_brand": "💼 Бренди & HQ",
        "cat_personal": "⭐ Особисті",
        "searching": "🔍 Скануємо мережу Telegram... Зачекайте ⏳",
        "search_results": "🎉 <b>Знайдені вільні юзернейми</b>\n🆔 <b>Search ID:</b> <code>#{search_id}</code>\n─────────────────────\n{results}",
        "search_none": "❌ Вільних юзернеймів не знайдено. Спробуйте ще раз!",
        "btn_more": "🔄 Повторити пошук",
        "mon_prompt": "🔔 <b>Моніторинг</b>\n─────────────────────\nВведіть зайнятий юзернейм для відстеження:",
        "mon_success": "✅ <b>Моніторинг для <code>{username}</code> активовано!</b>\nМи повідомимо вас, коли він звільниться.",
        "profile_text": "👤 <b>Профіль користувача</b>\n─────────────────────\n🆔 <b>User ID:</b> <code>{user_id}</code>\n🌍 <b>Мова:</b> {lang}\n📊 <b>Усього перевірок:</b> {checks}\n⭐ <b>Збережених юзерів:</b> {saved_count}\n🔔 <b>Активних моніторингів:</b> {mon_count}",
        "saved_title": "⭐ <b>Ваші збережені юзернейми:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ Збережених юзернеймів немає.",
        "history_empty": "📜 Історія пошуку порожня.",
        "history_cleared": "🗑 Історію пошуку успішно очищено!",
        "saved_success": "✅ Юзернейм <b>{username}</b> збережено!",
        "help_text": "ℹ️ <b>Довідка та функції</b>\n═════════════════════\n• <b>Авто-пошук:</b> Пошук випадкових вільних юзерів.\n• <b>Префікс/Суфікс:</b> Пошук за початком або закінченням.\n• <b>Точна перевірка:</b> Пряма перевірка юзернейму.\n• <b>Розумні варіації:</b> Генерація з приставками та тегами.\n• <b>Категорії:</b> Генерація під обрану тематику.\n• <b>Експорт TXT:</b> Завантаження списку результатів у файл.",
        "lang_changed": "Мову успішно змінено! ✅",
        "admin_demo_start": "🧪 <b>Запущено тестовий режим адміна</b>\nСканування пачки з 20 юзернеймів...",
    },
    "de": {
        "welcome": "👋 <b>Willkommen bei USERNAME FIX, {name}!</b>\n═════════════════════\nAutomatisierte Telegram Benutzernamen-Suche & Überwachung.\n\nStandard-Sprache: <b>English 🇬🇧</b>.\n\n👇 <i>Wählen Sie eine Option:</i>",
        "btn_auto_search": "🔍 Auto-Suche",
        "btn_prefix_search": "🔤 Präfix (@app*)",
        "btn_suffix_search": "🔚 Suffix (*bot)",
        "btn_exact_search": "🎯 Exakte Prüfung",
        "btn_smart_variations": "🧠 Smarte Variationen",
        "btn_categories": "🏷 Kategorien",
        "btn_profile": "👤 Profil & Gespeichert",
        "btn_mon": "🔔 Überwachen",
        "btn_settings": "🌍 Spracheinstellungen",
        "btn_help": "ℹ️ Hilfe",
        "btn_back": "« Zurück zum Menü",
        "btn_export_txt": "📦 TXT Exportieren",
        "btn_clear_history": "🗑 Verlauf löschen",
        "search_prompt": "🔍 <b>Auto-Suche</b>\nWählen Sie die Länge (5 bis 12 Zeichen):",
        "type_prompt": "⚙️ <b>Zeichenfilter</b>:",
        "btn_letters": "Nur Buchstaben 🔤",
        "btn_numbers": "Buchstaben + Zahlen 🔢",
        "prefix_prompt": "🔤 Präfix eingeben (z.B. <code>app</code>):",
        "suffix_prompt": "🔚 Suffix eingeben (z.B. <code>dev</code>):",
        "exact_prompt": "🎯 Benutzernamen eingeben (z.B. <code>@username</code>):",
        "smart_prompt": "🧠 Basisnamen eingeben (z.B. <code>falbercht</code>):",
        "categories_prompt": "🏷 Kategorie wählen:",
        "cat_gaming": "🎮 Gaming",
        "cat_f1": "🏎 Formel 1",
        "cat_tech": "💻 Tech & Dev",
        "cat_brand": "💼 Marke & HQ",
        "cat_personal": "⭐ Persönlich",
        "searching": "🔍 Suche läuft... Bitte warten ⏳",
        "search_results": "🎉 <b>Freie Benutzernamen gefunden</b>\n🆔 <b>Search ID:</b> <code>#{search_id}</code>\n─────────────────────\n{results}",
        "search_none": "❌ Keine freien Namen gefunden.",
        "btn_more": "🔄 Erneut suchen",
        "mon_prompt": "🔔 Besetzten Benutzernamen eingeben:",
        "mon_success": "✅ <b>Überwachung für <code>{username}</code> gestartet!</b>",
        "profile_text": "👤 <b>Benutzerprofil</b>\n🆔 ID: <code>{user_id}</code>\n🌍 Sprache: {lang}\n📊 Prüfungen: {checks}",
        "saved_title": "⭐ <b>Gespeicherte Namen:</b>\n{list}",
        "saved_empty": "⭐ Keine gespeicherten Namen.",
        "history_empty": "📜 Verlauf ist leer.",
        "history_cleared": "🗑 Verlauf gelöscht!",
        "saved_success": "✅ <b>{username}</b> gespeichert!",
        "help_text": "ℹ️ <b>Hilfe</b>\nAutomatische Suche und Überwachung von Telegram-Benutzernamen.",
        "lang_changed": "Sprache geändert! ✅",
        "admin_demo_start": "🧪 Admin-Testmodus gestartet...",
    },
    "zh": {
        "welcome": "👋 <b>欢迎使用 USERNAME FIX, {name}!</b>\n═════════════════════\n Telegram 用户名自动搜索、生成与监控。\n\n默认语言：<b>English 🇬🇧</b>。\n\n👇 <i>请选择操作：</i>",
        "btn_auto_search": "🔍 自动搜索",
        "btn_prefix_search": "🔤 前缀搜索 (@app*)",
        "btn_suffix_search": "🔚 后缀搜索 (*bot)",
        "btn_exact_search": "🎯 精确检测",
        "btn_smart_variations": "🧠 智能变体",
        "btn_categories": "🏷 分类搜索",
        "btn_profile": "👤 个人资料与保存",
        "btn_mon": "🔔 监控",
        "btn_settings": "🌍 语言设置",
        "btn_help": "ℹ️ 帮助",
        "btn_back": "« 返回菜单",
        "btn_export_txt": "📦 导出 TXT",
        "btn_clear_history": "🗑 清除历史",
        "search_prompt": "🔍 <b>自动搜索</b>\n选择字符长度 (5 到 12):",
        "type_prompt": "⚙️ <b>字符过滤</b>:",
        "btn_letters": "仅字母 🔤",
        "btn_numbers": "字母 + 数字 🔢",
        "prefix_prompt": "🔤 输入前缀 (例如 <code>app</code>):",
        "suffix_prompt": "🔚 输入后缀 (例如 <code>dev</code>):",
        "exact_prompt": "🎯 输入要检测的用户名 (例如 <code>@username</code>):",
        "smart_prompt": "🧠 输入基础名称 (例如 <code>falbercht</code>):",
        "categories_prompt": "🏷 选择主题分类:",
        "cat_gaming": "🎮 游戏",
        "cat_f1": "🏎 赛车 F1",
        "cat_tech": "💻 科技与开发",
        "cat_brand": "💼 品牌总部",
        "cat_personal": "⭐ 个人",
        "searching": "🔍 正在扫描... 请稍候 ⏳",
        "search_results": "🎉 <b>找到可用用户名</b>\n🆔 <b>Search ID:</b> <code>#{search_id}</code>\n─────────────────────\n{results}",
        "search_none": "❌ 未找到可用用户名，请重试！",
        "btn_more": "🔄 再次搜索",
        "mon_prompt": "🔔 输入要监控的用户名:",
        "mon_success": "✅ <b>已对 <code>{username}</code> 启动监控！</b>",
        "profile_text": "👤 <b>个人资料</b>\n🆔 用户 ID: <code>{user_id}</code>\n🌍 语言: {lang}\n📊 总检测数: {checks}",
        "saved_title": "⭐ <b>已保存的用户名:</b>\n{list}",
        "saved_empty": "⭐ 暂无保存的用户名。",
        "history_empty": "📜 搜索历史为空。",
        "history_cleared": "🗑 历史记录已清除！",
        "saved_success": "✅ <b>{username}</b> 保存成功！",
        "help_text": "ℹ️ <b>帮助</b>\n自动检测与生成 Telegram 可用用户名。",
        "lang_changed": "语言更改成功！ ✅",
        "admin_demo_start": "🧪 管理员测试模式已启动...",
    }
}

async def is_subscribed(user_id: int) -> bool:
    """Перевірка підписки вимкнена — доступ відкрито для всіх."""
    return True

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "en",
            "saved": [],
            "history": [],
            "monitored": [],
            "checks_count": 0,
            "temp_length": 5,
            "temp_use_numbers": True,
        }
    return user_data_store[user_id]

def t(user_id: int, key: str, **kwargs) -> str:
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    if lang not in TEXTS:
        lang = "en"
    template = TEXTS[lang].get(key, TEXTS["en"].get(key, ""))
    return template.format(**kwargs)

class BotStates(StatesGroup):
    auto_search = State()
    prefix_search = State()
    suffix_search = State()
    exact_search = State()
    smart_variations = State()
    monitor_username = State()
    waiting_feedback = State()

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(user_id, "btn_auto_search"), callback_data="menu:auto"),
                InlineKeyboardButton(text=t(user_id, "btn_exact_search"), callback_data="menu:exact"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_prefix_search"), callback_data="menu:prefix"),
                InlineKeyboardButton(text=t(user_id, "btn_suffix_search"), callback_data="menu:suffix"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_smart_variations"), callback_data="menu:smart"),
                InlineKeyboardButton(text=t(user_id, "btn_categories"), callback_data="menu:categories"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_profile"), callback_data="menu:profile"),
                InlineKeyboardButton(text=t(user_id, "btn_mon"), callback_data="menu:monitor"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_settings"), callback_data="menu:settings"),
                InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="menu:help"),
            ]
        ]
    )

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")]]
    )

def categories_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "cat_gaming"), callback_data="cat:gaming")],
            [InlineKeyboardButton(text=t(user_id, "cat_f1"), callback_data="cat:f1")],
            [InlineKeyboardButton(text=t(user_id, "cat_tech"), callback_data="cat:tech")],
            [InlineKeyboardButton(text=t(user_id, "cat_brand"), callback_data="cat:brand")],
            [InlineKeyboardButton(text=t(user_id, "cat_personal"), callback_data="cat:personal")],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 13):
        row.append(InlineKeyboardButton(text=str(length), callback_data=f"len:{length}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def type_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_letters"), callback_data="type:letters")],
            [InlineKeyboardButton(text=t(user_id, "btn_numbers"), callback_data="type:numbers")],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

def settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en"),
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang:ua"),
            ],
            [
                InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="setlang:de"),
                InlineKeyboardButton(text="🇨🇳 中文", callback_data="setlang:zh"),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logging.warning(f"TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"Error editing message: {e}")

async def check_single_username(username: str) -> bool | None:
    """Перевірка статусу юзернейму через Web Endpoint t.me."""
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return None
    url = f"https://t.me/{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as resp:
                text = await resp.text()
                if "tgme_page_extra" in text or "tgme_page_title" in text:
                    if "If you have Telegram, you can contact" in text or "View in Telegram" in text or "tgme_user" in text or "tgme_channel" in text:
                        return False
                if "If you have Telegram, you can set up" in text or "is available on Telegram" in text:
                    return True
                if resp.status == 200 and "tgme_page" in text and "tgme_page_photo" not in text:
                    return True
    def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "en",
            "saved": [],
            "history": [],
            "monitored": [],
            "checks_count": 0,
            "temp_length": 5,
            "temp_use_numbers": True,
        }
    return user_data_store[user_id]

def t(user_id: int, key: str, **kwargs) -> str:
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    if lang not in TEXTS:
        lang = "en"
    template = TEXTS[lang].get(key, TEXTS["en"].get(key, ""))
    return template.format(**kwargs)

class BotStates(StatesGroup):
    auto_search = State()
    prefix_search = State()
    suffix_search = State()
    exact_search = State()
    smart_variations = State()
    monitor_username = State()
    waiting_feedback = State()

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(user_id, "btn_auto_search"), callback_data="menu:auto"),
                InlineKeyboardButton(text=t(user_id, "btn_exact_search"), callback_data="menu:exact"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_prefix_search"), callback_data="menu:prefix"),
                InlineKeyboardButton(text=t(user_id, "btn_suffix_search"), callback_data="menu:suffix"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_smart_variations"), callback_data="menu:smart"),
                InlineKeyboardButton(text=t(user_id, "btn_categories"), callback_data="menu:categories"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_profile"), callback_data="menu:profile"),
                InlineKeyboardButton(text=t(user_id, "btn_mon"), callback_data="menu:monitor"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_settings"), callback_data="menu:settings"),
                InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="menu:help"),
            ]
        ]
    )

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")]]
    )

def categories_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "cat_gaming"), callback_data="cat:gaming")],
            [InlineKeyboardButton(text=t(user_id, "cat_f1"), callback_data="cat:f1")],
            [InlineKeyboardButton(text=t(user_id, "cat_tech"), callback_data="cat:tech")],
            [InlineKeyboardButton(text=t(user_id, "cat_brand"), callback_data="cat:brand")],
            [InlineKeyboardButton(text=t(user_id, "cat_personal"), callback_data="cat:personal")],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 13):
        row.append(InlineKeyboardButton(text=str(length), callback_data=f"len:{length}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def type_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_letters"), callback_data="type:letters")],
            [InlineKeyboardButton(text=t(user_id, "btn_numbers"), callback_data="type:numbers")],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

def settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en"),
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang:ua"),
            ],
            [
                InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="setlang:de"),
                InlineKeyboardButton(text="🇨🇳 中文", callback_data="setlang:zh"),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logging.warning(f"TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"Error editing message: {e}")

async def check_single_username(username: str) -> bool | None:
    """Перевірка статусу юзернейму через Web Endpoint t.me."""
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return None
    url = f"https://t.me/{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as resp:
                text = await resp.text()
                if "tgme_page_extra" in text or "tgme_page_title" in text:
                    if "If you have Telegram, you can contact" in text or "View in Telegram" in text or "tgme_user" in text or "tgme_channel" in text:
                        return False
                if "If you have Telegram, you can set up" in text or "is available on Telegram" in text:
                    return True
                if resp.status == 200 and "tgme_page" in text and "tgme_page_photo" not in text:
                    return True
                return False
    except Exception:
        return None

def analyze_username(username: str, lang: str = "en"):
    clean = username.lstrip("@")
    has_nums = bool(re.search(r"\d", clean))
    
    if lang == "ua":
        nums_str = "З цифрами 🔢" if has_nums else "Лише букви 🔤"
        letter_type = "Голосна" if clean[0].lower() in "aeiou" else "Приголосна"
    else:
        nums_str = "With numbers 🔢" if has_nums else "Letters only 🔤"
        letter_type = "Vowel" if clean[0].lower() in "aeiou" else "Consonant"
    
    length = len(clean)
    if length == 5 and not has_nums:
        rating = "5/5 ⭐⭐⭐⭐⭐"
        price = "100 - 300 TON ($250 - $700)"
    elif length == 6 and not has_nums:
        rating = "4.5/5 ⭐⭐⭐⭐✨"
        price = "30 - 90 TON ($70 - $200)"
    elif not has_nums:
        rating = "4/5 ⭐⭐⭐⭐"
        price = "10 - 30 TON ($25 - $70)"
    else:
        rating = "3/5 ⭐⭐⭐"
        price = "1 - 8 TON ($3 - $20)"
        
    return nums_str, letter_type, rating, price

async def generate_and_find_free(prefix: str = "", suffix: str = "", length: int = 5, use_numbers: bool = True, count: int = 2) -> list:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789_" if use_numbers else "abcdefghijklmnopqrstuvwxyz_"
    free_found = []
    attempts = 0
    
    while len(free_found) < count and attempts < 40:
        attempts += 1
        needed_len = length - len(prefix) - len(suffix)
        if needed_len < 0:
            needed_len = 2
            
        random_part = "".join(random.choice(chars) for _ in range(needed_len))
        candidate = f"{prefix}{random_part}{suffix}".lower()
        
        if not candidate[0].isalpha():
            candidate = "a" + candidate[1:]
            
        if candidate in global_checked_usernames:
            continue
            
        global_checked_usernames.add(candidate)
        is_free = await check_single_username(candidate)
        if is_free is True:
            free_found.append(f"@{candidate}")
        await asyncio.sleep(0.05)
    return free_found

def create_txt_export(results: list, search_id: str) -> BufferedInputFile:
    content = f"=== USERNAME FIX RESULTS (ID: #{search_id}) ===\n\n"
    for uname in results:
        content += f"Username: {uname}\n"
        content += f"Link: https://t.me/{uname.lstrip('@')}\n"
        content += "-" * 35 + "\n"
    return BufferedInputFile(content.encode("utf-8"), filename=f"usernames_{search_id}.txt")

@dp.message(Command("start", "старт"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    name = html.escape(message.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

@dp.message(Command("admin_demo"))
async def cmd_admin_demo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(t(message.from_user.id, "admin_demo_start"), parse_mode="HTML")
    results = await generate_and_find_free(length=6, count=5)
    formatted = "\n".join([f"• <code>{u}</code> ✅ Available" for u in results])
    await message.answer(f"🧪 <b>Demo Results:</b>\n\n{formatted}", parse_mode="HTML")

@dp.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = t(user_id, "welcome", name=name)
        await safe_edit_text(callback, text, reply_markup=main_keyboard(user_id))
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        await safe_edit_text(callback, t(user_id, "search_prompt"), reply_markup=length_keyboard(user_id))
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        await safe_edit_text(callback, t(user_id, "prefix_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "suffix":
        await state.set_state(BotStates.suffix_search)
        await safe_edit_text(callback, t(user_id, "suffix_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "exact":
        await state.set_state(BotStates.exact_search)
        await safe_edit_text(callback, t(user_id, "exact_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        await safe_edit_text(callback, t(user_id, "smart_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "categories":
        await safe_edit_text(callback, t(user_id, "categories_prompt"), reply_markup=categories_keyboard(user_id))
    elif action == "profile":
        profile = get_user_profile(user_id)
        text = t(
            user_id, "profile_text",
            user_id=user_id,
            lang=profile.get("lang", "en").upper(),
            checks=profile.get("checks_count", 0),
            saved_count=len(profile.get("saved", [])),
            mon_count=len(profile.get("monitored", []))
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t(user_id, "saved_title", list="").split(":")[0], callback_data="menu:view_saved")],
                [InlineKeyboardButton(text=t(user_id, "btn_clear_history"), callback_data="menu:clear_hist")],
                [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
            ]
        )
        await safe_edit_text(callback, text, reply_markup=markup)
    elif action == "view_saved":
        profile = get_user_profile(user_id)
        saved = profile.get("saved", [])
        if not saved:
            text = t(user_id, "saved_empty")
        else:
            items = [f"⭐ <code>{u}</code> — <a href='https://t.me/{u.lstrip('@')}'>Open</a>" for u in saved]
            text = t(user_id, "saved_title", list="\n".join(items))
        await safe_edit_text(callback, text, reply_markup=back_keyboard(user_id))
    elif action == "clear_hist":
        profile = get_user_profile(user_id)
        profile["history"] = []
        await callback.answer(t(user_id, "history_cleared"))
        await safe_edit_text(callback, t(user_id, "history_empty"), reply_markup=back_keyboard(user_id))
    elif action == "monitor":
        await state.set_state(BotStates.monitor_username)
        await safe_edit_text(callback, t(user_id, "mon_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "settings":
        await safe_edit_text(callback, "⚙️ <b>Select Language / Оберіть мову:</b>", reply_markup=settings_keyboard(user_id))
    elif action == "help":
        await safe_edit_text(callback, t(user_id, "help_text"), reply_markup=back_keyboard(user_id))
        
    await callback.answer()

@dp.callback_query(F.data.startswith("setlang:"))
async def set_lang_callback(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    get_user_profile(user_id)["lang"] = lang
    
    name = html.escape(callback.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await safe_edit_text(callback, text, reply_markup=main_keyboard(user_id))
    await callback.answer(t(user_id, "lang_changed"))

@dp.callback_query(F.data.startswith("cat:"))
async def category_selected_callback(callback: CallbackQuery):
    cat = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    suffixes = {
        "gaming": ["_gg", "play", "_game", "_esports"],
        "f1": ["_f1", "_gp", "racing", "_speed"],
        "tech": ["_dev", "_tech", "code", "_io"],
        "brand": ["_hq", "official", "_inc", "_co"],
        "personal": ["_me", "real", "_life", "_official"]
    }
    
    suf = random.choice(suffixes.get(cat, ["_app"]))
    await safe_edit_text(callback, t(user_id, "searching"))
    
    results = await generate_and_find_free(suffix=suf, length=7, count=2)
    await display_results(callback, user_id, results)

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    get_user_profile(user_id)["temp_length"] = length
    await safe_edit_text(callback, t(user_id, "type_prompt"), reply_markup=type_keyboard(user_id))
    await callback.answer()

@dp.callback_query(F.data.startswith("type:"))
async def type_selected_callback(callback: CallbackQuery):
    choice = callback.data.split(":")[1]
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    profile["temp_use_numbers"] = (choice == "numbers")
    length = profile.get("temp_length", 5)
    
    await safe_edit_text(callback, t(user_id, "searching"))
    results = await generate_and_find_free(length=length, use_numbers=profile["temp_use_numbers"], count=2)
    await display_results(callback, user_id, results)

async def display_results(callback: CallbackQuery, user_id: int, results: list):
    lang = get_user_profile(user_id).get("lang", "en")
    search_id = str(uuid.uuid4())[:6].upper()
    search_results_cache[search_id] = results
    
    profile = get_user_profile(user_id)
    profile["checks_count"] = profile.get("checks_count", 0) + len(results)
    
    if not results:
        text = t(user_id, "search_none")
        markup = main_keyboard(user_id)
    else:
        formatted = []
        buttons = []
        for uname in results:
            nums, l_type, rating, price = analyze_username(uname, lang)
            formatted.append(
                f"🔹 <code>{uname}</code>\n"
                f"   • Type: {nums} | {l_type}\n"
                f"   • Rating: {rating}\n"
                f"   • Est. Price: <b>{price}</b>"
            )
            buttons.append([
                InlineKeyboardButton(text=f"🔗 {uname}", url=f"https://t.me/{uname.lstrip('@')}"),
                InlineKeyboardButton(text=f"⭐ Save", callback_data=f"save:{uname}")
            ])
            
        text = t(user_id, "search_results", search_id=search_id, results="\n\n".join(formatted))
        buttons.append([InlineKeyboardButton(text=t(user_id, "btn_export_txt"), callback_data=f"export:{search_id}")])
        buttons.append([InlineKeyboardButton(text=t(user_id, "btn_more"), callback_data="menu:auto")])
        buttons.append([InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")])
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await safe_edit_text(callback, text, reply_markup=markup)

@dp.callback_query(F.data.startswith("save:"))
async def save_username_callback(callback: CallbackQuery):
    uname = callback.data.split(":")[1]
    user_id = callback.from_user.id
    saved = get_user_profile(user_id)["saved"]
    
    if uname not in saved:
        saved.append(uname)
        await callback.answer(t(user_id, "saved_success", username=uname))
    else:
        await callback.answer("Already saved!")

@dp.callback_query(F.data.startswith("export:"))
async def export_txt_callback(callback: CallbackQuery):
    search_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    results = search_results_cache.get(search_id, [])
    
    if not results:
        await callback.answer("Results expired!")
        return
        
    doc = create_txt_export(results, search_id)
    await callback.message.answer_document(doc, caption=f"📦 Exported results for Search #{search_id}")
    await callback.answer()

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    msg = await message.answer(t(user_id, "searching"), parse_mode="HTML")
    results = await generate_and_find_free(prefix=prefix, length=len(prefix) + 3, count=2)
    
    search_id = str(uuid.uuid4())[:6].upper()
    search_results_cache[search_id] = results
    
    if not results:
        await msg.edit_text(t(user_id, "search_none"), reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    formatted = [f"🔹 <code>{u}</code>\n   • Est. Price: <b>1-10 TON</b>" for u in results]
    text = t(user_id, "search_results", search_id=search_id, results="\n\n".join(formatted))
    
    buttons = [[InlineKeyboardButton(text=f"🔗 {u}", url=f"https://t.me/{u.lstrip('@')}") ] for u in results]
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_export_txt"), callback_data=f"export:{search_id}")])
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")])
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.message(BotStates.suffix_search)
async def process_suffix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    suffix = message.text.strip().lstrip("@")
    await state.clear()
    
    msg = await message.answer(t(user_id, "searching"), parse_mode="HTML")
    results = await generate_and_find_free(suffix=suffix, length=len(suffix) + 3, count=2)
    
    search_id = str(uuid.uuid4())[:6].upper()
    search_results_cache[search_id] = results
    
    if not results:
        await msg.edit_text(t(user_id, "search_none"), reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    formatted = [f"🔹 <code>{u}</code>\n   • Est. Price: <b>1-10 TON</b>" for u in results]
    text = t(user_id, "search_results", search_id=search_id, results="\n\n".join(formatted))
    
    buttons = [[InlineKeyboardButton(text=f"🔗 {u}", url=f"https://t.me/{u.lstrip('@')}")] for u in results]
    buttons.append([InlineKeyboar
