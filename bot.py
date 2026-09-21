import asyncio
import html
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

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("BOT_TOKEN is missing!")

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

user_data_store = {}
search_results_cache = {}
global_checked_usernames = set()

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "en",
            "saved": [],
            "history": [],
            "checks_count": 0,
        }
    return user_data_store[user_id]

def add_to_history(user_id: int, usernames: list):
    profile = get_user_profile(user_id)
    for u in usernames:
        if u not in profile["history"]:
            profile["history"].insert(0, u)
    profile["history"] = profile["history"][:20]

class BotStates(StatesGroup):
    auto_search = State()
    prefix_search = State()
    smart_variations = State()

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    
    if lang == "ua":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Авто-пошук", callback_data="menu:auto"),
                InlineKeyboardButton(text="🔤 Префікс / Суфікс", callback_data="menu:prefix"),
            ],
            [
                InlineKeyboardButton(text="🧠 Розумні варіації", callback_data="menu:smart"),
                InlineKeyboardButton(text="👤 Профіль та Збережені", callback_data="menu:profile"),
            ],
            [
                InlineKeyboardButton(text="🌍 Мова", callback_data="menu:settings"),
                InlineKeyboardButton(text="ℹ️ Довідка", callback_data="menu:help"),
            ]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Auto-Search", callback_data="menu:auto"),
                InlineKeyboardButton(text="🔤 Prefix / Suffix", callback_data="menu:prefix"),
            ],
            [
                InlineKeyboardButton(text="🧠 Smart Variations", callback_data="menu:smart"),
                InlineKeyboardButton(text="👤 Profile & Saved", callback_data="menu:profile"),
            ],
            [
                InlineKeyboardButton(text="🌍 Language", callback_data="menu:settings"),
                InlineKeyboardButton(text="ℹ️ Help", callback_data="menu:help"),
            ]
        ])

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)
    text = "« Назад" if profile.get("lang") == "ua" else "« Back"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="menu:main")]])

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
    profile = get_user_profile(user_id)
    back_text = "« Назад" if profile.get("lang") == "ua" else "« Back"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Error editing message: {e}")

async def check_single_username(username: str) -> bool | None:
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return None
    url = f"https://t.me/{username}"
    # Додаємо більш реалістичні заголовки, щоб Telegram не блокував запити
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
                
                # Якщо на сторінці є блок про завантаження додатку або кнопка "Send Message" / "View in Telegram" — профіль зайнятий
                if "tgme_action_button_new" in text or "If you have Telegram" in text or "View in Telegram" in text:
                    return False
                
                # Якщо це канал/група і там є назва або публікації
                if "tgme_page_extra" in text or "tgme_page_title" in text:
                    # Але перевіримо, чи це часом не сторінка вільного юзернейму
                    if "is available on Telegram" in text or "you can set up" in text:
                        return True
                    return False

                # Головний маркер вільного юзернейму в Telegram
                if "is available on Telegram" in text or "you can set up" in text or "username is not taken" in text:
                    return True
                    
                # Додаткова перевірка: якщо немає специфічних блоків зайнятого акаунта, але сторінка виглядає пустою
                if "tgme_page" in text and "tgme_page_photo" not in text and "tgme_page_additional" not in text:
                    return True
                    
                return False
    except Exception:
        return None

async def generate_and_find_free(prefix: str = "", suffix: str = "", length: int = 5, count: int = 2) -> list:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789_"
    free_found = []
    attempts = 0
    while len(free_found) < count and attempts < 35:
        attempts += 1
        needed_len = max(2, length - len(prefix) - len(suffix))
        random_part = "".join(random.choice(chars) for _ in range(needed_len))
        candidate = f"{prefix}{random_part}{suffix}".lower()
        if not candidate[0].isalpha():
            candidate = "a" + candidate[1:]
        if candidate in global_checked_usernames:
            continue
        global_checked_usernames.add(candidate)
        if await check_single_username(candidate) is True:
            free_found.append(f"@{candidate}")
        await asyncio.sleep(0.05)
    return free_found

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    profile = get_user_profile(user_id)
    name = html.escape(message.from_user.first_name)
    
    if profile["lang"] == "ua":
        text = f"👋 <b>Ласкаво просимо, {name}!</b>\n\nОберіть дію в меню нижче:"
    else:
        text = f"👋 <b>Welcome, {name}!</b>\n\nChoose an action below:"
        
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

@dp.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    lang = profile["lang"]
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = f"👋 <b>Welcome, {name}!</b>" if lang == "en" else f"👋 <b>Ласкаво просимо, {name}!</b>"
        await safe_edit_text(callback, text, reply_markup=main_keyboard(user_id))
        
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        text = "🔍 Select length (5-12):" if lang == "en" else "🔍 Оберіть довжину (5-12):"
        await safe_edit_text(callback, text, reply_markup=length_keyboard(user_id))
        
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        text = "🔤 Send prefix or suffix:" if lang == "en" else "🔤 Введіть префікс або суфікс:"
        await safe_edit_text(callback, text, reply_markup=back_keyboard(user_id))
        
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        text = "🧠 Send base name:" if lang == "en" else "🧠 Введіть базове ім'я:"
        await safe_edit_text(callback, text, reply_markup=back_keyboard(user_id))
        
    elif action == "profile":
        saved_count = len(profile["saved"])
        history_count = len(profile["history"])
        
        if lang == "ua":
            text = (
                f"👤 <b>Профіль користувача</b>\n"
                f"─────────────────────\n"
                f"🆔 <b>Ваш Telegram ID:</b> <code>{user_id}</code>\n"
                f"🌍 <b>Мова:</b> Українська\n"
                f"📊 <b>Перевірок:</b> {profile['checks_count']}\n"
                f"⭐ <b>Збережених:</b> {saved_count}\n"
                f"📜 <b>Історія:</b> {history_count}"
            )
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐ Збережені", callback_data="menu:view_saved"),
                    InlineKeyboardButton(text="📜 Історія", callback_data="menu:view_history")
                ],
                [InlineKeyboardButton(text="« Назад", callback_data="menu:main")]
            ])
        else:
            text = (
                f"👤 <b>User Profile</b>\n"
                f"─────────────────────\n"
                f"🆔 <b>Your Telegram ID:</b> <code>{user_id}</code>\n"
                f"🌍 <b>Language:</b> English\n"
                f"📊 <b>Checks:</b> {profile['checks_count']}\n"
                f"⭐ <b>Saved:</b> {saved_count}\n"
                f"📜 <b>History:</b> {history_count}"
            )
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐ Saved", callback_data="menu:view_saved"),
                    InlineKeyboardButton(text="📜 History", callback_data="menu:view_history")
                ],
                [InlineKeyboardButton(text="« Back", callback_data="menu:main")]
            ])
        await safe_edit_text(callback, text, reply_markup=markup)
        
    elif action == "view_saved":
        saved = profile["saved"]
        if not saved:
            text = "⭐ No saved usernames yet." if lang == "en" else "⭐ Збережених юзернеймів немає."
        else:
            items = [f"⭐ <code>{u}</code> — <a href='https://t.me/{u.lstrip('@')}'>Link</a>" for u in saved]
            text = "⭐ <b>Saved Usernames:</b>\n\n" + "\n".join(items)
        await safe_edit_text(callback, text, reply_markup=back_keyboard(user_id))
        
    elif action == "view_history":
        history = profile["history"]
        if not history:
            text = "📜 History is empty." if lang == "en" else "📜 Історія порожня."
        else:
            items = [f"📜 <code>{u}</code> — <a href='https://t.me/{u.lstrip('@')}'>Link</a>" for u in history]
            text = "📜 <b>Recent Searches:</b>\n\n" + "\n".join(items)
        await safe_edit_text(callback, text, reply_markup=back_keyboard(user_id))
        
    elif action == "settings":
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en"),
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang:ua"),
            ],
            [InlineKeyboardButton(text="« Back", callback_data="menu:main")]
        ])
        await safe_edit_text(callback, "⚙️ Choose language / Оберіть мову:", reply_markup=markup)
        
    elif action == "help":
        text = "ℹ️ <b>Help:</b>\nUse Auto-Search, Prefix Search, or Smart Variations to find available Telegram usernames."
        await safe_edit_text(callback, text, reply_markup=back_keyboard(user_id))
        
    await callback.answer()

@dp.callback_query(F.data.startswith("setlang:"))
async def set_lang_callback(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    get_user_profile(user_id)["lang"] = lang
    
    name = html.escape(callback.from_user.first_name)
    text = f"👋 <b>Welcome, {name}!</b>" if lang == "en" else f"👋 <b>Ласкаво просимо, {name}!</b>"
    await safe_edit_text(callback, text, reply_markup=main_keyboard(user_id))
    await callback.answer("Saved / Збережено")

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    await safe_edit_text(callback, "🔍 Scanning Telegram... ⏳")
    results = await generate_and_find_free(length=length, count=2)
    
    profile["checks_count"] += len(results)
    add_to_history(user_id, results)
    
    if not results:
        await safe_edit_text(callback, "❌ No free usernames found.", reply_markup=main_keyboard(user_id))
        return

    formatted = [f"🔹 <code>{u}</code>" for u in results]
    buttons = []
    for u in results:
        clean_u = u.lstrip('@')
        buttons.append([
            InlineKeyboardButton(text=f"🔗 {u}", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="⭐ Save", callback_data=f"save:{clean_u}")
        ])
    buttons.append([InlineKeyboardButton(text="« Back", callback_data="menu:main")])

    text = "🎉 <b>Found Available Usernames:</b>\n\n" + "\n".join(formatted)
    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("save:"))
async def save_username_callback(callback: CallbackQuery):
    raw_uname = callback.data.split(":", 1)[1]
    uname = f"@{raw_uname.lstrip('@')}"
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    if uname not in profile["saved"]:
        profile["saved"].append(uname)
        await callback.answer(f"✅ Saved {uname}!", show_alert=True)
    else:
        await callback.answer("Already saved!", show_alert=True)

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    msg = await message.answer("🔍 Scanning Telegram... ⏳", parse_mode="HTML")
    results = await generate_and_find_free(prefix=prefix, length=len(prefix) + 3, count=2)
    
    profile = get_user_profile(user_id)
    profile["checks_count"] += len(results)
    add_to_history(user_id, results)
    
    if not results:
        await msg.edit_text("❌ No free usernames found.", reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    formatted = [f"🔹 <code>{u}</code>" for u in results]
    text = "🎉 <b>Found Available Usernames:</b>\n\n" + "\n".join(formatted)
    
    buttons = []
    for u in results:
        clean_u = u.lstrip('@')
        buttons.append([
            InlineKeyboardButton(text=f"🔗 {u}", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="⭐ Save", callback_data=f"save:{clean_u}")
        ])
    buttons.append([InlineKeyboardButton(text="« Back", callback_data="menu:main")])
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.message(BotStates.smart_variations)
async def process_smart_variations(message: Message, state: FSMContext):
    user_id = message.from_user.id
    base = message.text.strip().lstrip("@")
    await state.clear()
    
    msg = await message.answer("🔍 Scanning Telegram... ⏳", parse_mode="HTML")
    variations = [f"the_{base}", f"{base}x", f"real_{base}", f"{base}hq", f"{base}_dev"]
    
    free_found = []
    for var in variations:
        if await check_single_username(var):
            free_found.append(f"@{var}")
            
    profile = get_user_profile(user_id)
    profile["checks_count"] += len(free_found)
    add_to_history(user_id, free_found)
            
    if not free_found:
        await msg.edit_text("❌ No free variations found.", reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    formatted = [f"🔹 <code>{u}</code>" for u in free_found]
    text = "🧠 <b>Found Variations:</b>\n\n" + "\n".join(formatted)
    
    buttons = []
    for u in free_found:
        clean_u = u.lstrip('@')
        buttons.append([
            InlineKeyboardButton(text=f"🔗 {u}", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="⭐ Save", callback_data=f"save:{clean_u}")
        ])
    buttons.append([InlineKeyboardButton(text="« Back", callback_data="menu:main")])
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
