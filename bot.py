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

# Отримання токена зі змінних оточення Railway (Variables)
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("BOT_TOKEN не знайдено у Variables Railway!")

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

# Налаштування каналу для обов'язкової підписки
CHANNEL_USERNAME = "@usernamingFix"
CHANNEL_URL = "https://t.me/usernamingFix"

ADMIN_ID = 5619415334
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

# Збереження даних користувачів та кєш
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
        "sub_required": "🚀 <b>Subscription Required!</b>\nPlease subscribe to our official channel to use the bot:\n{channel}",
        "btn_sub": "📢 Subscribe to Channel",
        "btn_check_sub": "✅ Verify Subscription",
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
        "btn_numbers": "Букви + Цифри 🔢",
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
        "sub_required": "🚀 <b>Обов'язкова підписка!</b>\nДля використання бота підпишіться на наш офіційний канал:\n{channel}",
        "btn_sub": "📢 Підписатися на канал",
        "btn_check_sub": "✅ Перевірити підписку",
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
        "sub_required": "🚀 <b>Abonnement erforderlich!</b>\nKanal abonnieren: {channel}",
        "btn_sub": "📢 Kanal Abonnieren",
        "btn_check_sub": "✅ Überprüfen",
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
        "sub_required": "🚀 <b>必须关注频道！</b>\n请先关注官方频道：{channel}",
        "btn_sub": "📢 关注频道",
        "btn_check_sub": "✅ 检查关注",
        "admin_demo_start": "🧪 管理员测试模式已启动...",
    }
}

async def is_subscribed(user_id: int) -> bool:
    """Перевірка підписки на обов'язковий канал."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.warning(f"Не вдалося перевірити підписку для {user_id}: {e}")
        return True

def sub_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_sub"), url=CHANNEL_URL)],
            [InlineKeyboardButton(text=t(user_id, "btn_check_sub"), callback_data="check_sub")]
        ]
    )

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "en",  # За замовчуванням встановили англійську мову
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

async def safe_edit_text(callback: Callback)
