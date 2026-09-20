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
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 0

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
    "ua": {
        "welcome": "👋 <b>Вітаємо, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — ваш сервіс для перевірки, підбору та моніторингу юзернеймів.\n\n👇 <i>Оберіть потрібний розділ:</i>",
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
        "single_prompt": "🔍 <b>Пошук юзернейма</b>\n─────────────────────\nВведіть юзернейм для перевірки:\n<i>(наприклад: <code>coolname</code>)</i>",
        "gen_prompt": "🎲 <b>Генератор ідей</b>\n─────────────────────\nВведіть базове слово або бренд:",
        "bulk_prompt": "⚡ <b>Масовий чек</b>\n─────────────────────\nНадішліть список юзернеймів через пробіл або рядок:",
        "var_prompt": "🧩 <b>Пошук варіацій</b>\n─────────────────────\nВведіть ім'я для підбору варіацій:",
        "saved_empty": "📌 <b>Обране</b>\n─────────────────────\nСписок порожній.",
        "mon_prompt": "🔔 <b>Моніторинг</b>\n─────────────────────\nВведіть зайнятий юзернейм:",
        "hist_empty": "📜 <b>Історія</b>\n─────────────────────\nПорожньо.",
        "stats_title": "📈 <b>Статистика системи</b>\n═════════════════════\nПеревірок: <b>{user_checks}</b>\nВільних: <b>{user_free}</b>",
        "settings_title": "⚙️ <b>Налаштування</b>\n─────────────────────\nПоточна мова: <b>Українська 🇺🇦</b>",
        "help_text": "ℹ️ <b>Довідка</b>\n═════════════════════\nШвидка перевірка, генерація та моніторинг Telegram юзернеймів.",
        "alert_text": "🔔 <b>ЮЗЕРНЕЙМ ЗВІЛЬНИВСЯ!</b>\nЮзернейм <code>@{u}</code> тепер вільний!",
    }
}

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "ua",
            "saved": [],
            "history": [],
            "checked_count": 0,
            "available_count": 0,
        }
    global_stats["unique_users"].add(user_id)
    return user_data_store[user_id]

def t(user_id: int, key: str, **kwargs) -> str:
    lang = "ua"
    template = TEXTS["ua"].get(key, "")
    return template.format(**kwargs)

# --- STATES ---
class BotStates(StatesGroup):
    single_search = State()
    generator_keyword = State()
    bulk_search = State()
    variation_search = State()
    monitor_username = State()

# --- KEYBOARDS ---
def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
    )

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

@dispatcher.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = t(user_id, "welcome", name=name)
        await callback.message.edit_text(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
    elif action == "single":
        await state.set_state(BotStates.single_search)
        await callback.message.edit_text(t(user_id, "single_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "generator":
        await state.set_state(BotStates.generator_keyword)
        await callback.message.edit_text(t(user_id, "gen_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "bulk":
        await state.set_state(BotStates.bulk_search)
        await callback.message.edit_text(t(user_id, "bulk_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "variations":
        await state.set_state(BotStates.variation_search)
        await callback.message.edit_text(t(user_id, "var_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "saved":
        await callback.message.edit_text(t(user_id, "saved_empty"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "monitor":
        await state.set_state(BotStates.monitor_username)
        await callback.message.edit_text(t(user_id, "mon_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "history":
        await callback.message.edit_text(t(user_id, "hist_empty"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "stats":
        profile = get_user_profile(user_id)
        await callback.message.edit_text(t(user_id, "stats_title", user_checks=profile["checked_count"], user_free=profile["available_count"]), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "settings":
        await callback.message.edit_text(t(user_id, "settings_title"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "help":
        await callback.message.edit_text(t(user_id, "help_text"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    
    await callback.answer()

# --- MAIN ---
async def main():
    asyncio.create_task(monitoring_worker())
    await dispatcher.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
