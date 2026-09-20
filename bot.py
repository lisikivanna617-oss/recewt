import asyncio
import html
import logging
import random
import re
import aiohttp
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
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

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

user_data_store = {}
monitored_usernames = {}
global_stats = {
    "total_checked": 0,
    "total_available": 0,
    "unique_users": set(),
}

# --- TRANSLATIONS (Default: English) ---
TEXTS = {
    "en": {
        "welcome": "👋 <b>Welcome, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — automated Telegram username finder & monitor.\n\n👇 <i>Select an option below:</i>",
        "btn_search": "🔍 Auto-Search Free",
        "btn_mon": "🔔 Monitor",
        "btn_settings": "Зміна мови 🌍",
        "btn_help": "ℹ️ Help",
        "btn_back": "« Back to Menu",
        "search_prompt": "🔍 <b>Auto-Search Usernames</b>\n─────────────────────\nSelect the desired username length (from 5 to 32 characters):",
        "searching": "🔍 Searching for free usernames of length <b>{length}</b>... Please wait ⏳",
        "search_results": "🎉 <b>Search Results (Length {length}):</b>\n─────────────────────\n{results}\n\n<i>Want more? Click below!</i>",
        "search_none": "❌ No free usernames found in this batch. Try again!",
        "mon_prompt": "🔔 <b>Monitoring</b>\n─────────────────────\nSend a taken username to track:",
        "settings_title": "⚙️ <b>Language Selection</b>\n─────────────────────\nChoose your interface language:",
        "help_text": "ℹ️ <b>Help</b>\n═════════════════════\nThis bot automatically generates and scans for available Telegram usernames based on your length criteria.",
        "lang_changed": "Language successfully changed to English! ✅",
    },
    "ua": {
        "welcome": "👋 <b>Вітаємо, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — автоматичний пошук та моніторинг вільних юзернеймів.\n\n👇 <i>Оберіть розділ:</i>",
        "btn_search": "🔍 Авто-пошук вільних",
        "btn_mon": "🔔 Моніторинг",
        "btn_settings": "Зміна мови 🌍",
        "btn_help": "ℹ️ Довідка",
        "btn_back": "« Повернутися в меню",
        "search_prompt": "🔍 <b>Авто-пошук юзернеймів</b>\n─────────────────────\nОберіть бажану кількість символів (від 5 до 32):",
        "searching": "🔍 Шукаємо вільні юзернейми довжиною <b>{length}</b>... Зачекайте⏳",
        "search_results": "🎉 <b>Результати пошуку (Довжина {length}):</b>\n─────────────────────\n{results}\n\n<i>Бажаєте ще? Натисніть нижче!</i>",
        "search_none": "❌ У цій спробі вільних юзернеймів не знайдено. Спробуйте ще раз!",
        "mon_prompt": "🔔 <b>Моніторинг</b>\n─────────────────────\nВведіть зайнятий юзернейм:",
        "settings_title": "⚙️ <b>Зміна мови</b>\n─────────────────────\nОберіть мову інтерфейсу:",
        "help_text": "ℹ️ <b>Довідка</b>\n═════════════════════\nБот автоматично генерує та перевіряє вільні Telegram юзернейми.",
        "lang_changed": "Мову успішно змінено на українську! ✅",
    },
    "de": {
        "welcome": "👋 <b>Willkommen, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — Automatisierte Benutzernamen-Suche.\n\n👇 <i>Wählen Sie eine Option:</i>",
        "btn_search": "🔍 Freie Suchen",
        "btn_mon": "🔔 Überwachen",
        "btn_settings": "Зміна мови 🌍",
        "btn_help": "ℹ️ Hilfe",
        "btn_back": "« Zurück zum Menü",
        "search_prompt": "🔍 <b>Benutzernamen-Suche</b>\n─────────────────────\nWählen Sie die Länge (5 bis 32 Zeichen):",
        "searching": "🔍 Suche nach freien Namen mit Länge <b>{length}</b>...",
        "search_results": "🎉 <b>Ergebnisse (Länge {length}):</b>\n─────────────────────\n{results}",
        "search_none": "❌ Keine freien Benutzernamen gefunden.",
        "mon_prompt": "🔔 <b>Überwachung</b>\n─────────────────────\nBesetzten Benutzernamen eingeben:",
        "settings_title": "⚙️ <b>Sprache ändern</b>\n─────────────────────\nWählen Sie Ihre Sprache:",
        "help_text": "ℹ️ <b>Hilfe</b>\n═════════════════════\nAutomatische Suche nach verfügbaren Telegram-Namen.",
        "lang_changed": "Sprache zu Deutsch geändert! ✅",
    },
    "zh": {
        "welcome": "👋 <b>欢迎, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — 自动用户名搜索与监控。\n\n👇 <i>请选择：</i>",
        "btn_search": "🔍 自动搜索空闲",
        "btn_mon": "🔔 监控",
        "btn_settings": "Зміна мови 🌍",
        "btn_help": "ℹ️ 帮助",
        "btn_back": "« 返回菜单",
        "search_prompt": "🔍 <b>自动搜索用户名</b>\n─────────────────────\n选择字符长度（5 到 32）：",
        "searching": "🔍 正在搜索长度为 <b>{length}</b> 的空闲用户名...",
        "search_results": "🎉 <b>搜索结果 (长度 {length}):</b>\n─────────────────────\n{results}",
        "search_none": "❌ 未找到空闲用户名，请重试！",
        "mon_prompt": "🔔 <b>监控</b>\n─────────────────────\n输入要监控的用户名：",
        "settings_title": "⚙️ <b>语言选择</b>\n─────────────────────\n请选择您的语言：",
        "help_text": "ℹ️ <b>帮助</b>\n═════════════════════\n自动为您生成并检测可用的 Telegram 用户名。",
        "lang_changed": "语言已更改为中文！ ✅",
    }
}

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "en",  # Default language is English
            "saved": [],
            "history": [],
            "checked_count": 0,
            "available_count": 0,
        }
    global_stats["unique_users"].add(user_id)
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
    monitor_username = State()

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_search"), callback_data="menu:search")],
            [InlineKeyboardButton(text=t(user_id, "btn_mon"), callback_data="menu:monitor")],
            [
                InlineKeyboardButton(text=t(user_id, "btn_settings"), callback_data="menu:settings"),
                InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="menu:help"),
            ],
        ]
    )

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")]]
    )

def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    # Клавіатура для вибору довжини від 5 до 12 (або інші популярні) + кнопка назад
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

# Генератор випадкових юзернеймів заданої довжини
async def generate_and_find_free(length: int, count: int = 5) -> list:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789_"
    free_found = []
    attempts = 0
    while len(free_found) < count and attempts < 30:
        attempts += 1
        # Перший символ обов'язково літера
        first_char = random.choice("abcdefghijklmnopqrstuvwxyz")
        remaining = "".join(random.choice(chars) for _ in range(length - 1))
        candidate = first_char + remaining
        
        # Перевіряємо унікальність/валіदність
        if candidate in [f.lstrip("@") for f in free_found]:
            continue
            
        is_free = await check_single_username(candidate)
        if is_free is True:
            free_found.append(f"@{candidate}")
        await asyncio.sleep(0.3)
    return free_found

@dispatcher.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    name = html.escape(message.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

@dispatcher.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = t(user_id, "welcome", name=name)
        await callback.message.edit_text(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
    elif action == "search":
        await state.set_state(BotStates.auto_search)
        await callback.message.edit_text(t(user_id, "search_prompt"), reply_markup=length_keyboard(user_id), parse_mode="HTML")
    elif action == "monitor":
        await state.set_state(BotStates.monitor_username)
        await callback.message.edit_text(t(user_id, "mon_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "settings":
        await callback.message.edit_text(t(user_id, "settings_title"), reply_markup=settings_keyboard(user_id), parse_mode="HTML")
    elif action == "help":
        await callback.message.edit_text(t(user_id, "help_text"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    
    await callback.answer()

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

@dispatcher.callback_query(F.data.startswith("setlang:"))
async def set_lang_callback(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    get_user_profile(user_id)["lang"] = lang
    await callback.message.edit_text(t(user_id, "settings_title"), reply_markup=settings_keyboard(user_id), parse_mode="HTML")
    await callback.answer(t(user_id, "lang_changed"))

# Обробка вибору довжини для авто-пошуку
@dispatcher.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    await callback.message.edit_text(t(user_id, "searching", length=length), parse_mode="HTML")
    
    free_list = await generate_and_find_free(length, count=5)
    
    if not free_list:
        results_text = t(user_id, "search_none")
    else:
        results_text = "\n".join([f"▫️ <code>{item}</code>" for item in free_list])
    
    text = t(user_id, "search_results", length=length, results=results_text)
    await callback.message.edit_text(text, reply_markup=length_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

async def main():
    await dispatcher.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
